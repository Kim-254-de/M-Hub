"""The AgriSense conversation — a menu-driven state machine, Britam style.

Every incoming WhatsApp message lands in `handle()`. We look up the farmer and
their ChatSession (which step they are on), then decide the reply. Button and
list taps carry ids such as "DIAG", "BUY:12" or "QTY:2"; typed text is used for
free-form answers (name, ward, phone number...).
"""
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models import F
from django.utils import timezone

from core.models import Agrovet, Diagnosis, Farmer, Order, Product
from core.services import crop_health, label_check
from core.utils import normalize_phone
from payments import mpesa

from . import client as wa
from . import notify
from .messages import t
from .models import ChatSession

log = logging.getLogger(__name__)

COUNTIES = ["Tharaka-Nithi", "Meru", "Embu", "Kirinyaga", "Murang'a", "Nyeri", "Kiambu", "Nakuru", "Machakos"]
MENU_WORDS = {"hi", "hello", "hey", "menu", "start", "home", "0", "habari", "niaje", "mambo", "jambo"}
CANCEL_WORDS = {"cancel", "stop", "exit", "back"}
LANG_NAMES = dict(Farmer.LANGUAGES)
LANG_BUTTONS = [("LANG:en", "English"), ("LANG:sw", "Kiswahili")]
# The pilot is tomato only (Documentation: initial focus on tomato farmers in Tharaka Nithi).
CROP = "tomato"


@dataclass
class Incoming:
    phone: str
    wamid: str = ""
    name: str = ""
    kind: str = "text"      # text | reply | image | location | other
    text: str = ""
    reply_id: str = ""      # id of a tapped button / list row / template quick-reply payload
    media_id: str = ""
    mime: str = ""
    latitude: float = None
    longitude: float = None

    @property
    def word(self):
        return self.text.strip().lower()


class Ctx:
    def __init__(self, msg, farmer, session, agrovet):
        self.msg, self.farmer, self.session, self.agrovet = msg, farmer, session, agrovet

    @property
    def lang(self):
        return self.farmer.language

    @property
    def phone(self):
        return self.msg.phone

    def t(self, key, **kw):
        return t(key, self.lang, **kw)

    def first(self):
        return notify.first_name(self.farmer)


def local(phone):
    return "0" + phone[3:] if phone.startswith("254") else phone


# ===========================================================================
# Entry point
# ===========================================================================

def handle(msg: Incoming):
    farmer, created = Farmer.objects.get_or_create(phone=msg.phone, defaults={"whatsapp_name": msg.name})
    if msg.name and farmer.whatsapp_name != msg.name:
        farmer.whatsapp_name = msg.name
        farmer.save(update_fields=["whatsapp_name"])
    session, _ = ChatSession.objects.get_or_create(phone=msg.phone)
    _expire_stale(session, farmer)
    agrovet = Agrovet.objects.filter(phone=msg.phone).first()
    ctx = Ctx(msg, farmer, session, agrovet)

    rid = msg.reply_id
    # Agrovets reviewing farmer photos (human in the loop)
    if agrovet and (rid.startswith(("REV_", "REVIEW:", "HANDOVER:")) or session.step.startswith("AGRO_")
                    or msg.word == "reviews"):
        return agrovet_flow(ctx)
    # "Did it work?" answers can arrive any time (template quick replies)
    if rid.startswith("OUT:"):
        return on_outcome(ctx)

    # Not registered yet, or editing profile → registration flow
    if not farmer.is_registered or session.step.startswith("REG_"):
        if farmer.is_registered and (msg.word in MENU_WORDS | CANCEL_WORDS or rid == "MENU"):
            return show_menu(ctx)
        return registration(ctx)

    if msg.word in MENU_WORDS | CANCEL_WORDS or rid == "MENU":
        return show_menu(ctx)

    # Taps that work from anywhere
    routes = {
        "DIAG": start_diagnosis, "HIST": show_history, "AGROVETS": show_agrovets,
        "PROFILE": show_profile, "HELP": show_help, "EDIT_PROFILE": edit_profile, "LANG_MENU": ask_language,
    }
    if rid in routes:
        return routes[rid](ctx)
    prefix = rid.split(":", 1)[0] if ":" in rid else ""
    prefix_routes = {
        "BUY": show_products, "ASK": ask_agrovet, "PROD": choose_product, "QTY": choose_qty,
        "RETRY_PAY": retry_payment, "LANG": set_language, "LABEL": ask_label,
    }
    if prefix in prefix_routes:
        return prefix_routes[prefix](ctx)
    if rid in ("PAY_ME", "PAY_OTHER"):
        return choose_pay_phone(ctx)

    # Photo sent without going through the menu → diagnose it straight away (tomato pilot)
    if msg.kind == "image" and session.step not in ("DIAG_PHOTO", "LABEL_PHOTO"):
        session.go("DIAG_PHOTO", crop=CROP)
        return run_diagnosis(ctx, msg.media_id, msg.mime or "image/jpeg")

    # Step-specific free input
    step_handlers = {
        "DIAG_PHOTO": photo_received, "LABEL_PHOTO": label_received,
        "SHOP_PAY_PHONE": pay_phone_typed, "ORDER_WAIT": order_waiting,
    }
    handler = step_handlers.get(session.step)
    if handler:
        return handler(ctx)

    if session.step == "MAIN_MENU" and msg.kind == "text":
        return show_menu(ctx)
    wa.send_buttons(ctx.phone, ctx.t("didnt_understand"), [("MENU", ctx.t("btn_menu"))])


def _expire_stale(session, farmer):
    if session.step in ("START", "WELCOME", "MAIN_MENU"):
        return
    limit = timezone.now() - timedelta(minutes=settings.WA_SESSION_TIMEOUT_MIN)
    if session.updated_at and session.updated_at < limit:
        session.reset("MAIN_MENU" if farmer.is_registered else "START")


# ===========================================================================
# Registration (like Britam's sign-up chat)
# ===========================================================================

def send_welcome(ctx):
    name = ctx.farmer.whatsapp_name.split(" ")[0] if ctx.farmer.whatsapp_name else ""
    wa.send_buttons(
        ctx.phone, ctx.t("welcome", name=name).replace("Karibu !", "Karibu!"),
        [("REG_START", ctx.t("btn_register")), ("HOW", ctx.t("btn_how"))],
        header="🌱 AgriSense Hub", footer="Healthy crops, genuine products",
    )
    ctx.session.go("WELCOME")


def registration(ctx):
    s, m, f = ctx.session, ctx.msg, ctx.farmer
    rid, text = m.reply_id, m.text.strip()

    if rid == "REG_START":
        s.data = {}
        s.go("REG_NAME")
        return wa.send_text(ctx.phone, ctx.t("ask_name"))
    if rid == "HOW":
        wa.send_buttons(ctx.phone, ctx.t("how_it_works"), [("REG_START", ctx.t("btn_register"))])
        return s.go("WELCOME")

    if s.step == "REG_NAME":
        if len(text) < 2 or not any(c.isalpha() for c in text):
            return wa.send_text(ctx.phone, ctx.t("bad_name"))
        s.go("REG_COUNTY", name=text.title())
        return ask_county(ctx, text.split(" ")[0].title())

    if s.step == "REG_COUNTY":
        if rid == "COUNTY:other":
            s.go("REG_COUNTY_TEXT")
            return wa.send_text(ctx.phone, ctx.t("ask_county_text"))
        county = rid.split(":", 1)[1] if rid.startswith("COUNTY:") else text.title()
        if not county:
            return ask_county(ctx, s.data.get("name", "").split(" ")[0])
        s.go("REG_WARD", county=county)
        return wa.send_text(ctx.phone, ctx.t("ask_ward"))

    if s.step == "REG_COUNTY_TEXT" and text:
        s.go("REG_WARD", county=text.title())
        return wa.send_text(ctx.phone, ctx.t("ask_ward"))

    if s.step == "REG_WARD" and text:
        s.go("REG_LANG", ward=text.title())
        return wa.send_buttons(ctx.phone, ctx.t("ask_language"), LANG_BUTTONS)

    if s.step == "REG_LANG" and rid.startswith("LANG:"):
        s.go("REG_CONFIRM", language=rid.split(":", 1)[1])
        return confirm_registration(ctx)

    if s.step == "REG_CONFIRM":
        if rid == "REG_OK":
            d = s.data
            f.full_name, f.county, f.ward = d.get("name", ""), d.get("county", ""), d.get("ward", "")
            f.main_crops, f.language = CROP, d.get("language", "en")
            f.is_registered = True
            f.consent_at = f.consent_at or timezone.now()
            f.save()
            s.reset()
            wa.send_text(ctx.phone, ctx.t("registered", first=ctx.first()))
            return show_menu(ctx)
        if rid == "REG_EDIT":
            s.go("REG_NAME")
            return wa.send_text(ctx.phone, ctx.t("ask_name"))
        return confirm_registration(ctx)

    # Anything else from an unregistered farmer → welcome screen (re-asks current question if mid-way)
    reask = {
        "REG_NAME": lambda: wa.send_text(ctx.phone, ctx.t("ask_name")),
        "REG_COUNTY": lambda: ask_county(ctx, s.data.get("name", "").split(" ")[0]),
        "REG_COUNTY_TEXT": lambda: wa.send_text(ctx.phone, ctx.t("ask_county_text")),
        "REG_WARD": lambda: wa.send_text(ctx.phone, ctx.t("ask_ward")),
        "REG_LANG": lambda: wa.send_buttons(ctx.phone, ctx.t("ask_language"),
                                            LANG_BUTTONS),
    }
    if s.step in reask and m.word not in MENU_WORDS:
        return reask[s.step]()
    return send_welcome(ctx)


def ask_county(ctx, first):
    rows = [(f"COUNTY:{c}", c, "") for c in COUNTIES] + [("COUNTY:other", "➕ Other county", "")]
    wa.send_list(ctx.phone, ctx.t("ask_county", first=first), ctx.t("btn_choose_county"), [("Counties", rows)])


def confirm_registration(ctx):
    d = ctx.session.data
    wa.send_buttons(
        ctx.phone,
        ctx.t("confirm_reg", name=d.get("name"), county=d.get("county"), ward=d.get("ward"),
              language=LANG_NAMES.get(d.get("language", "en"))),
        [("REG_OK", ctx.t("btn_confirm")), ("REG_EDIT", ctx.t("btn_edit"))],
    )


# ===========================================================================
# Main menu & simple screens
# ===========================================================================

def show_menu(ctx):
    if not ctx.farmer.is_registered:
        return send_welcome(ctx)
    ctx.session.reset("MAIN_MENU")
    wa.send_list(
        ctx.phone,
        ctx.t("menu_body", first=ctx.first()),
        ctx.t("menu_button"),
        [
            (ctx.t("sec_crop"), [("DIAG", ctx.t("row_diag"), ctx.t("row_diag_d")),
                                 ("HIST", ctx.t("row_hist"), ctx.t("row_hist_d"))]),
            (ctx.t("sec_shop"), [("AGROVETS", ctx.t("row_agrovets"),
                                  ctx.t("row_agrovets_d", county=ctx.farmer.county))]),
            (ctx.t("sec_account"), [("PROFILE", ctx.t("row_profile"), ctx.t("row_profile_d")),
                                    ("HELP", ctx.t("row_help"), ctx.t("row_help_d"))]),
        ],
        header="🌱 AgriSense Hub",
        footer=ctx.t("menu_footer"),
    )


def menu_button(ctx):
    return ("MENU", ctx.t("btn_menu"))


def show_history(ctx):
    f = ctx.farmer
    diags = list(f.diagnoses.all()[:3])
    orders = list(f.orders.select_related("product").all()[:3])
    if not diags and not orders:
        body = ctx.t("history_empty")
    else:
        lines = [ctx.t("history_title"), ""]
        for d in diags:
            lines.append(f"🩺 {timezone.localtime(d.created_at):%d %b} — {d.crop}: {d.disease or '…'} ({d.get_status_display()})")
        for o in orders:
            lines.append(f"🧾 {timezone.localtime(o.created_at):%d %b} — {o.quantity}× {o.product.name}, KES {o.amount} "
                         f"({o.get_status_display()}){' · code ' + o.pickup_code if o.status == Order.STATUS_PAID else ''}")
        body = "\n".join(lines)
    wa.send_buttons(ctx.phone, body, [("DIAG", ctx.t("row_diag")[2:].strip()), menu_button(ctx)])


def show_agrovets(ctx):
    county = ctx.farmer.county
    shops = Agrovet.objects.filter(is_verified=True, county__iexact=county)[:8]
    if not shops:
        body = ctx.t("agrovets_none", county=county)
    else:
        lines = [ctx.t("agrovets_title", county=county), ""]
        for a in shops:
            lines.append(f"✅ *{a.name}* — {a.town}\n   {a.location_hint}\n   📞 {local(a.phone)}")
        body = "\n".join(lines)
    wa.send_buttons(ctx.phone, body, [menu_button(ctx)])


def show_profile(ctx):
    f = ctx.farmer
    wa.send_buttons(
        ctx.phone,
        ctx.t("profile", name=f.full_name, phone=local(f.phone), county=f.county, ward=f.ward,
              language=LANG_NAMES.get(f.language), points=f.points),
        [("EDIT_PROFILE", ctx.t("btn_edit")), ("LANG_MENU", ctx.t("btn_language")), menu_button(ctx)],
    )


def edit_profile(ctx):
    f = ctx.farmer
    ctx.session.data = {"name": f.full_name, "county": f.county, "ward": f.ward, "language": f.language}
    ctx.session.go("REG_NAME")
    wa.send_text(ctx.phone, ctx.t("ask_name"))


def ask_language(ctx):
    wa.send_buttons(ctx.phone, ctx.t("ask_language"), LANG_BUTTONS)


def set_language(ctx):
    ctx.farmer.language = ctx.msg.reply_id.split(":", 1)[1]
    ctx.farmer.save(update_fields=["language"])
    wa.send_text(ctx.phone, ctx.t("language_set"))
    show_menu(ctx)


def show_help(ctx):
    wa.send_buttons(ctx.phone, ctx.t("help"), [menu_button(ctx)])


# ===========================================================================
# Detect → diagnose
# ===========================================================================

def start_diagnosis(ctx):
    ctx.session.reset("DIAG_PHOTO")
    ctx.session.go("DIAG_PHOTO", crop=CROP)
    wa.send_text(ctx.phone, ctx.t("ask_photo"))


def photo_received(ctx):
    if ctx.msg.kind != "image":
        return wa.send_text(ctx.phone, ctx.t("need_photo"))
    return run_diagnosis(ctx, ctx.msg.media_id, ctx.msg.mime or "image/jpeg")


def run_diagnosis(ctx, media_id, mime):
    s, f = ctx.session, ctx.farmer
    crop = s.data.get("crop", "crop")
    retry = [("DIAG", ctx.t("btn_try_again")), menu_button(ctx)]
    wa.send_text(ctx.phone, ctx.t("checking", crop=crop))

    content, mime = wa.download_media(media_id)
    if not content:
        return wa.send_buttons(ctx.phone, ctx.t("diag_failed"), retry)

    diagnosis = Diagnosis(farmer=f, crop=crop, wa_media_id=media_id)
    ext = {"image/png": "png", "image/webp": "webp"}.get(mime, "jpg")
    diagnosis.image.save(f"{f.phone}_{uuid.uuid4().hex[:8]}.{ext}", ContentFile(content), save=False)

    result = crop_health.identify(content, mime, crop, ctx.msg.latitude, ctx.msg.longitude)
    diagnosis.raw_response = result.raw or {"error": result.error}
    if not result.ok:
        diagnosis.save()
        return wa.send_buttons(ctx.phone, ctx.t("diag_failed"), retry)
    if not result.is_plant or not result.disease:
        diagnosis.save()
        return wa.send_buttons(ctx.phone, ctx.t("not_clear"), retry)  # stays on DIAG_PHOTO

    diagnosis.disease = result.disease.capitalize()
    diagnosis.confidence = result.confidence
    diagnosis.description = result.description
    diagnosis.treatment = crop_health.format_treatment(result.treatment)
    # Humans decide, AI assists: every diagnosis is confirmed by a verified agrovet before
    # the farmer can buy anything (Documentation §3, principle 2).
    diagnosis.status = Diagnosis.STATUS_REVIEW
    diagnosis.save()
    notified = notify.request_review(diagnosis)

    body = ctx.t("diag_ai_pending", disease=diagnosis.disease, pct=round(result.confidence * 100))
    if not notified:
        body += "\n\n" + ctx.t("no_agrovet", county=f.county)
    wa.send_text(ctx.phone, body)
    if diagnosis.treatment:
        wa.send_buttons(ctx.phone, ctx.t("diag_prevention", prevention=diagnosis.treatment)[:1024],
                        [menu_button(ctx)])
    s.reset("MAIN_MENU")


def ask_agrovet(ctx):
    """Kept for old ASK:<id> buttons still in farmers' chats; review is now automatic."""
    return show_menu(ctx)


def _id(reply_id, index=1):
    try:
        return int(reply_id.split(":")[index])
    except (IndexError, ValueError):
        return 0


# ===========================================================================
# Prescribe → buy genuine product → M-Pesa
# ===========================================================================

def show_products(ctx):
    diagnosis = Diagnosis.objects.filter(pk=_id(ctx.msg.reply_id), farmer=ctx.farmer).first()
    if not diagnosis:
        return show_menu(ctx)
    # Products are only offered once an agrovet has confirmed or corrected the diagnosis.
    if diagnosis.status not in (Diagnosis.STATUS_CONFIRMED, Diagnosis.STATUS_REJECTED):
        return wa.send_buttons(ctx.phone, ctx.t("diag_ai_pending", disease=diagnosis.disease,
                                                pct=round(diagnosis.confidence * 100)), [menu_button(ctx)])
    county = ctx.farmer.county.lower()
    products = [
        p for p in Product.objects.filter(in_stock=True, agrovet__is_verified=True)
        .exclude(pcpb_reg_no="").select_related("agrovet")
        if p.matches(diagnosis.disease, diagnosis.crop)
    ]
    products.sort(key=lambda p: (p.agrovet.county.lower() != county, p.farmer_price))
    if not products:
        return wa.send_buttons(ctx.phone, ctx.t("no_products"), [menu_button(ctx)])
    rows = []
    for p in products[:10]:
        off = f" -{p.farmer_discount_pct}%" if p.farmer_discount_pct else ""
        rows.append((f"PROD:{p.pk}", p.name, f"KES {p.farmer_price}{off} · {p.pcpb_reg_no} · {p.agrovet.name}"))
    ctx.session.go("SHOP_PRODUCT", diag_id=diagnosis.pk)
    wa.send_list(ctx.phone, ctx.t("products_body", disease=diagnosis.disease), ctx.t("btn_products"),
                 [("Products", rows)], footer="✅ PCPB-registered · verified agrovets")


def choose_product(ctx):
    product = Product.objects.select_related("agrovet").filter(pk=_id(ctx.msg.reply_id), in_stock=True).first()
    if not product:
        return show_menu(ctx)
    a = product.agrovet
    discount = (ctx.t("discount", pct=product.farmer_discount_pct, old=product.price)
                if product.farmer_discount_pct else "")
    ctx.session.go("SHOP_QTY", product_id=product.pk)
    wa.send_buttons(
        ctx.phone,
        ctx.t("product_detail", name=product.name, pack=product.pack_size, pcpb=product.pcpb_reg_no,
              ingredient=product.active_ingredient,
              agrovet=a.name, town=a.town or a.county, price=product.farmer_price, discount=discount,
              usage=product.usage_note),
        [("QTY:1", "1"), ("QTY:2", "2"), ("QTY:3", "3")],
    )


def choose_qty(ctx):
    s = ctx.session
    product = Product.objects.select_related("agrovet").filter(pk=s.data.get("product_id")).first()
    if not product:
        return show_menu(ctx)
    qty = max(1, min(_id(ctx.msg.reply_id), 10))
    s.go("SHOP_PAY", qty=qty)
    wa.send_buttons(
        ctx.phone,
        ctx.t("order_summary", qty=qty, name=product.name, pack=product.pack_size, agrovet=product.agrovet.name,
              town=product.agrovet.town, amount=product.farmer_price * qty, phone=local(ctx.phone)),
        [("PAY_ME", ctx.t("btn_pay_me")), ("PAY_OTHER", ctx.t("btn_pay_other")), ("MENU", ctx.t("btn_cancel"))],
    )


def choose_pay_phone(ctx):
    if ctx.msg.reply_id == "PAY_OTHER":
        ctx.session.go("SHOP_PAY_PHONE")
        return wa.send_text(ctx.phone, ctx.t("ask_pay_phone"))
    return create_order(ctx, ctx.phone)


def pay_phone_typed(ctx):
    phone = normalize_phone(ctx.msg.text)
    if not phone:
        return wa.send_text(ctx.phone, ctx.t("bad_phone"))
    return create_order(ctx, phone)


def create_order(ctx, pay_phone):
    s = ctx.session
    product = Product.objects.filter(pk=s.data.get("product_id")).first()
    if not product:
        return show_menu(ctx)
    qty = int(s.data.get("qty", 1))
    order = Order.objects.create(
        farmer=ctx.farmer, product=product, quantity=qty, amount=product.farmer_price * qty,
        pay_phone=pay_phone, diagnosis_id=s.data.get("diag_id"),
    )
    return start_payment(ctx, order)


def start_payment(ctx, order):
    checkout_id, error = mpesa.stk_push(order.pay_phone, order.amount, f"AGS{order.pk}", "AgriSense")
    if error:
        order.status = Order.STATUS_FAILED
        order.save(update_fields=["status"])
        ctx.session.reset("MAIN_MENU")
        return wa.send_buttons(ctx.phone, ctx.t("stk_failed", error=error),
                               [(f"RETRY_PAY:{order.pk}", ctx.t("btn_retry_pay")), menu_button(ctx)])
    order.checkout_request_id = checkout_id
    order.status = Order.STATUS_PENDING
    order.save(update_fields=["checkout_request_id", "status"])
    ctx.session.go("ORDER_WAIT", order_id=order.pk)
    wa.send_text(ctx.phone, ctx.t("stk_sent", phone=local(order.pay_phone), amount=order.amount))
    if mpesa.is_simulated():
        from webchat.outbox import push_stk
        push_stk(ctx.phone, order)


def retry_payment(ctx):
    order = Order.objects.filter(pk=_id(ctx.msg.reply_id), farmer=ctx.farmer).first()
    if not order or order.status == Order.STATUS_PAID:
        return show_menu(ctx)
    return start_payment(ctx, order)


def order_waiting(ctx):
    wa.send_text(ctx.phone, ctx.t("order_wait"))


# ===========================================================================
# Label check after pickup (Documentation §6.4, step 4)
# ===========================================================================

def ask_label(ctx):
    """LABEL:<order_id> — the farmer taps 'Check label' (also sent automatically at hand-over)."""
    order = Order.objects.select_related("product__agrovet").filter(
        pk=_id(ctx.msg.reply_id), farmer=ctx.farmer, status=Order.STATUS_COLLECTED, label_result=""
    ).first()
    if not order:
        return show_menu(ctx)
    notify.ask_label_photo(order)


def label_received(ctx):
    s = ctx.session
    order = Order.objects.select_related("product__agrovet").filter(
        pk=s.data.get("order_id"), farmer=ctx.farmer, status=Order.STATUS_COLLECTED, label_result=""
    ).first()
    if not order:
        return show_menu(ctx)

    if ctx.msg.kind == "image":
        wa.send_text(ctx.phone, ctx.t("label_checking"))
        content, _ = wa.download_media(ctx.msg.media_id)
        text = label_check.read_label_text(content) if content else None
    else:
        text = ctx.msg.text
    result = label_check.check(order, text or "")

    if result.result == "unreadable":
        return wa.send_text(ctx.phone, ctx.t("label_unreadable"))  # stays on LABEL_PHOTO

    order.label_result, order.label_reg_no = result.result, result.reg_no[:40]
    order.save(update_fields=["label_result", "label_reg_no"])
    s.reset("MAIN_MENU")

    if result.result == Order.LABEL_VERIFIED:
        points = settings.REWARD_POINTS_VERIFIED_PURCHASE
        Farmer.objects.filter(pk=ctx.farmer.pk).update(points=F("points") + points)
        ctx.farmer.refresh_from_db(fields=["points"])
        body = ctx.t("label_verified", name=order.product.name, reg=order.product.pcpb_reg_no,
                     points=points, total=ctx.farmer.points)
    elif result.result == Order.LABEL_NOT_PRESCRIBED:
        body = ctx.t("label_not_prescribed", other=result.product.name, reg=result.reg_no, name=order.product.name)
        notify.label_failed(order)
    else:
        body = ctx.t("label_not_registered", reg=result.reg_no)
        notify.label_failed(order)
    wa.send_buttons(ctx.phone, body, [menu_button(ctx)])


# ===========================================================================
# Outcome follow-up ("did it work?")
# ===========================================================================

def on_outcome(ctx):
    parts = ctx.msg.reply_id.split(":")
    diagnosis = Diagnosis.objects.filter(pk=_id(ctx.msg.reply_id), farmer=ctx.farmer).first()
    outcome = parts[2] if len(parts) > 2 else ""
    if not diagnosis or outcome not in dict(Diagnosis.OUTCOMES):
        return show_menu(ctx)
    diagnosis.outcome = outcome
    diagnosis.save(update_fields=["outcome"])
    if outcome == "no_change":
        return wa.send_buttons(ctx.phone, ctx.t("outcome_no_change"), [("DIAG", ctx.t("btn_try_again")),
                                                                        menu_button(ctx)])
    wa.send_buttons(ctx.phone, ctx.t("outcome_thanks"), [menu_button(ctx)])


# ===========================================================================
# Agrovet side — confirm or correct AI diagnoses from WhatsApp
# ===========================================================================

def agrovet_flow(ctx):
    a, s, m = ctx.agrovet, ctx.session, ctx.msg
    rid = m.reply_id

    if rid.startswith("HANDOVER:"):
        # The agrovet checked the pickup code and handed over the product (Documentation §6.4, step 3).
        order = Order.objects.select_related("farmer", "product__agrovet").filter(
            pk=_id(rid), product__agrovet=a
        ).first()
        if not order:
            return wa.send_text(ctx.phone, "That order is not at your store.")
        if order.status == Order.STATUS_COLLECTED:
            return wa.send_text(ctx.phone, f"Order #{order.pk} was already handed over. Thank you!")
        if order.status != Order.STATUS_PAID:
            return wa.send_text(ctx.phone, f"Order #{order.pk} is not paid yet — do not hand it over.")
        order.status, order.collected_at = Order.STATUS_COLLECTED, timezone.now()
        order.save(update_fields=["status", "collected_at"])
        notify.ask_label_photo(order)
        return wa.send_text(
            ctx.phone, f"✅ Order #{order.pk} handed over. The farmer will now check the label is genuine."
        )

    if rid.startswith("REVIEW:"):
        d = Diagnosis.objects.filter(pk=_id(rid)).first()
        if d:
            link = notify.media_url(d)
            caption = f"🔎 Review #{d.pk} — {d.crop}: {d.disease or 'unknown'} ({round(d.confidence * 100)}%)"
            if link:
                wa.send_image(ctx.phone, link, caption)
            return wa.send_buttons(ctx.phone, "Is the AI suggestion correct?",
                                   [(f"REV_OK:{d.pk}", "✅ Correct"), (f"REV_FIX:{d.pk}", "📝 Correct it")])

    if rid.startswith(("REV_OK:", "REV_FIX:")):
        d = Diagnosis.objects.select_related("farmer", "reviewed_by").filter(pk=_id(rid)).first()
        if not d:
            return wa.send_text(ctx.phone, "That review no longer exists.")
        if d.status != Diagnosis.STATUS_REVIEW:
            who = d.reviewed_by.name if d.reviewed_by else "another agrovet"
            return wa.send_text(ctx.phone, f"Review #{d.pk} was already handled by {who}. Thank you!")
        if rid.startswith("REV_OK:"):
            d.status, d.reviewed_by = Diagnosis.STATUS_CONFIRMED, a
            d.save(update_fields=["status", "reviewed_by"])
            notify.diagnosis_reviewed(d)
            s.reset("MAIN_MENU")
            return wa.send_text(ctx.phone, f"✅ Thanks! The farmer has been told review #{d.pk} is confirmed.")
        s.go("AGRO_FIX", diag_id=d.pk)
        return wa.send_text(
            ctx.phone,
            "Type the correct problem and your advice like this:\n\n"
            "*Early blight - spray mancozeb every 7 days, remove lower leaves*",
        )

    if s.step == "AGRO_FIX" and m.text.strip():
        d = Diagnosis.objects.select_related("farmer").filter(pk=s.data.get("diag_id")).first()
        if not d or d.status != Diagnosis.STATUS_REVIEW:
            s.reset("MAIN_MENU")
            return wa.send_text(ctx.phone, "That review was already handled. Thank you!")
        disease, _, note = m.text.strip().partition(" - ")
        d.disease, d.agrovet_note = disease.strip().capitalize(), note.strip()
        d.status, d.reviewed_by = Diagnosis.STATUS_REJECTED, a
        d.save(update_fields=["disease", "agrovet_note", "status", "reviewed_by"])
        notify.diagnosis_reviewed(d)
        s.reset("MAIN_MENU")
        return wa.send_text(ctx.phone, f"✅ Thanks! The farmer has received your correction for review #{d.pk}.")

    # "reviews" → list pending reviews in the agrovet's county
    pending = Diagnosis.objects.filter(status=Diagnosis.STATUS_REVIEW, farmer__county__iexact=a.county)[:10]
    if not pending:
        return wa.send_text(ctx.phone, f"🎉 No pending reviews in {a.county}. Thank you, {a.name}!")
    rows = [(f"REVIEW:{d.pk}", f"#{d.pk} {d.crop}", f"AI: {d.disease or '?'} · {timezone.localtime(d.created_at):%d %b %H:%M}")
            for d in pending]
    wa.send_list(ctx.phone, f"🔎 {len(rows)} farmer photo(s) waiting for your review in {a.county}.",
                 "Open reviews", [("Pending", rows)])
