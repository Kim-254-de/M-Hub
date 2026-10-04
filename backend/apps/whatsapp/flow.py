"""The farmer's WhatsApp conversation: a menu-driven state machine over the existing services.

Registration -> accounts (with data-use consent); Report a problem -> cases (Detect) and
diagnosis; prescriptions arrive through notification events; buying -> purchases (Module 4).
``handle`` runs inside a transaction with the Conversation row locked, so two quick messages
from one farmer are handled one after the other. Replies are queued and sent after commit.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts import locations
from apps.accounts.models import FarmerProfile, User
from apps.cases import services as detect
from apps.cases.messages import retake_message
from apps.cases.models import Case, CasePhoto
from apps.cases.quality import PhotoQualityError
from apps.purchases import services as purchases
from apps.purchases.models import Order, Verification
from apps.rewards.services import balance

from . import transport as wa
from .messages import text
from .models import Conversation, InboundMessage

logger = logging.getLogger(__name__)

# A list message holds at most 10 rows; longer choices show 9 per page plus a 'More' row.
PAGE_SIZE = 9
LANGUAGES = [("en", "English"), ("sw", "Kiswahili"), ("ki", "Gĩkũyũ")]
MENU_WORDS = {"hi", "hello", "hey", "menu", "start", "home", "habari", "mambo", "jambo", "niaje"}
CANCEL_WORDS = {"cancel", "stop", "exit", "ghairi"}
SKIP_WORDS = {"skip", "ruka"}
PHOTO_ORDER = [CasePhoto.Type.LEAF, CasePhoto.Type.PLANT, CasePhoto.Type.STEM_FRUIT]
STARTED = ["less_than_3_days", "3_to_7_days", "1_to_2_weeks", "over_2_weeks"]
SHARE = ["few", "some", "most"]
WEATHER = ["rainy", "humid", "hot_dry", "cold", "normal"]


@dataclass
class Ctx:
    conversation: Conversation
    message: InboundMessage

    @property
    def phone(self) -> str:
        return self.conversation.phone

    @property
    def user(self) -> User | None:
        return self.conversation.user

    @property
    def lang(self) -> str:
        if self.user is not None:
            profile = FarmerProfile.objects.filter(user=self.user).only("language").first()
            if profile:
                return profile.language
        return self.conversation.data.get("language", "en")

    @property
    def word(self) -> str:
        return (self.message.text or "").strip().lower()

    @property
    def rid(self) -> str:
        return self.message.reply_id or ""

    def t(self, key, **values) -> str:
        return text(key, self.lang, **values)

    def go(self, step: str, **data) -> None:
        self.conversation.step = step
        self.conversation.data.update(data)
        self.conversation.save(update_fields=["step", "data", "updated_at"])

    def reset(self, step: str = "MENU") -> None:
        keep = {k: v for k, v in self.conversation.data.items() if k == "language"}
        self.conversation.step, self.conversation.data = step, keep
        self.conversation.save(update_fields=["step", "data", "updated_at"])

    def first(self) -> str:
        name = (self.user.first_name if self.user else "") or self.conversation.profile_name or ""
        return name.split(" ")[0] or "farmer"

    def menu_button(self):
        return ("MENU", self.t("btn_menu"))


# =============================================================================
# Entry point
# =============================================================================


def handle(ctx: Ctx) -> None:
    conv, msg = ctx.conversation, ctx.message
    _expire_stale(ctx)
    conv.last_inbound_at = timezone.now()
    if msg.profile_name:
        conv.profile_name = msg.profile_name
    conv.save(update_fields=["last_inbound_at", "profile_name", "updated_at"])

    if conv.user is None:
        _link_existing_account(ctx)
    if conv.user is not None and conv.user.role != User.Role.FARMER:
        return wa.send_text(
            ctx.phone, "AgriSense agrovet tools are in the AgriSense app. This WhatsApp line is for farmers."
        )

    if conv.user is None or conv.step.startswith("REG_"):
        return registration(ctx)

    if ctx.word in MENU_WORDS | CANCEL_WORDS or ctx.rid == "MENU":
        return show_menu(ctx)

    routes = {
        "REPORT": start_report,
        "CASES": show_cases,
        "ORDERS": show_orders,
        "REWARDS": show_rewards,
        "LOCATION": start_location,
        "LANGUAGE": ask_language,
        "HELP": show_help,
    }
    if ctx.rid in routes:
        return routes[ctx.rid](ctx)
    prefix, _, value = ctx.rid.partition(":")
    prefix_routes = {
        "LANG": set_language,
        "RETAKE": retake_photos,
        "BUYRX": show_stores,
        "STORE": choose_store,
        "PAY": choose_payment,
        "RETRYPAY": retry_payment,
        "LABEL": ask_label,
        "STARTED": answer_started,
        "SHARE": answer_share,
        "WEATHER": answer_weather,
        "SPRAYED": answer_sprayed,
        "LOC_R": choose_region,
        "LOC_C": choose_county,
        "LOC_S": choose_sub_county,
        "LOC_W": choose_ward,
        "LOC_MORE": more_locations,
    }
    if value and prefix in prefix_routes:
        return prefix_routes[prefix](ctx, value)

    step_handlers = {
        "R_LOCATION": location_received,
        "R_PHOTO": photo_received,
        "R_SPRAYED_PRODUCT": sprayed_product_typed,
        "LABEL": label_received,
        **dict.fromkeys(LOCATION_STEPS, ask_location_again),
    }
    handler = step_handlers.get(conv.step)
    if handler:
        return handler(ctx)
    if msg.kind == "image":
        return start_report(ctx)
    return wa.send_buttons(ctx.phone, ctx.t("didnt_understand"), [ctx.menu_button()])


def _expire_stale(ctx: Ctx) -> None:
    """A half-finished flow resets after a period of silence. Reports keep their draft case."""
    conv = ctx.conversation
    if conv.step in ("START", "MENU") or conv.step.startswith("REG_"):
        return
    limit = timezone.now() - timedelta(minutes=settings.WHATSAPP["SESSION_TIMEOUT_MINUTES"])
    if conv.last_inbound_at and conv.last_inbound_at < limit:
        ctx.reset()


def _link_existing_account(ctx: Ctx) -> None:
    """A farmer who registered in the app is recognised by phone number."""
    user = User.objects.filter(phone=ctx.phone, is_active=True).first()
    if user is None:
        return
    try:
        with transaction.atomic():
            ctx.conversation.user = user
            ctx.conversation.save(update_fields=["user", "updated_at"])
    except IntegrityError:  # already linked to another conversation row
        ctx.conversation.user = None
        logger.warning("User %s is linked to another WhatsApp conversation", user.pk)
        return
    if user.role == User.Role.FARMER:
        wa.send_text(ctx.phone, ctx.t("linked", first=ctx.first()))
        if not ctx.conversation.step.startswith("REG_"):
            ctx.reset()


# =============================================================================
# Registration (accounts + consent)
# =============================================================================


def registration(ctx: Ctx) -> None:
    """Registration needs only the WhatsApp number and data-use consent; the farm location is
    asked the first time the farmer uploads photos."""
    conv, rid = ctx.conversation, ctx.rid

    if rid == "REG_START":
        ctx.go("REG_CONSENT")
        return _ask_consent(ctx)
    if rid == "HOW":
        return wa.send_buttons(ctx.phone, ctx.t("how_it_works"), [("REG_START", ctx.t("btn_register"))])

    if conv.step == "REG_CONSENT":
        if rid == "REG_AGREE":
            return _create_farmer(ctx)
        if rid == "REG_DECLINE":
            ctx.reset("START")
            return wa.send_text(ctx.phone, ctx.t("declined"))
        if ctx.word not in MENU_WORDS:
            return _ask_consent(ctx)
    return _welcome(ctx)


def _welcome(ctx: Ctx) -> None:
    ctx.go("START")
    name = (ctx.conversation.profile_name or "").split(" ")[0]
    wa.send_buttons(
        ctx.phone,
        ctx.t("welcome", first=name).replace("Karibu !", "Karibu!"),
        [("REG_START", ctx.t("btn_register")), ("HOW", ctx.t("btn_how"))],
        header="🌱 AgriSense Hub",
    )


def local_phone(phone: str) -> str:
    """+254712345678 -> 0712 345 678"""
    digits = "0" + phone.removeprefix("+254")
    return f"{digits[:4]} {digits[4:7]} {digits[7:]}"


def _ask_consent(ctx: Ctx) -> None:
    wa.send_buttons(
        ctx.phone,
        ctx.t("consent", phone=local_phone(ctx.phone)),
        [("REG_AGREE", ctx.t("btn_agree")), ("REG_DECLINE", ctx.t("btn_decline"))],
    )


def _create_farmer(ctx: Ctx) -> None:
    try:
        with transaction.atomic():
            user = User(username=ctx.phone, phone=ctx.phone, role=User.Role.FARMER)
            # WhatsApp farmers have no PIN yet; they can set one to use the app later.
            user.set_unusable_password()
            user.save()
            FarmerProfile.objects.create(
                user=user,
                language=ctx.conversation.data.get("language", FarmerProfile.Language.ENGLISH),
                consent_at=timezone.now(),
            )
    except IntegrityError:
        # Registered in the app meanwhile: link instead.
        _link_existing_account(ctx)
        return show_menu(ctx)
    ctx.conversation.user = user
    ctx.conversation.save(update_fields=["user", "updated_at"])
    logger.info("Farmer %s registered on WhatsApp", user.pk)
    wa.send_text(ctx.phone, ctx.t("registered", first=ctx.first()))
    show_menu(ctx)


# =============================================================================
# Farm location: region -> county -> sub-county -> ward
# =============================================================================

LOCATION_STEPS = ("L_REGION", "L_COUNTY", "L_SUB_COUNTY", "L_WARD")


def start_location(ctx: Ctx, then: str = "") -> None:
    """``then="report"`` continues to the photo upload once the ward is chosen."""
    regions = list(locations.REGIONS)
    ctx.reset("L_REGION")
    ctx.go("L_REGION", then=then, loc={})
    if len(regions) == 1:  # one service region: go straight to its counties
        return choose_region(ctx, regions[0])
    _location_list(ctx, "L_REGION", 0)


def _location_options(ctx: Ctx, step: str) -> list[str]:
    loc = ctx.conversation.data.get("loc", {})
    region, county = loc.get("region", ""), loc.get("county", "")
    return {
        "L_REGION": lambda: list(locations.REGIONS),
        "L_COUNTY": lambda: locations.counties(region),
        "L_SUB_COUNTY": lambda: locations.sub_counties(region, county),
        "L_WARD": lambda: locations.wards(region, county, loc.get("sub_county", "")),
    }[step]()


def _location_list(ctx: Ctx, step: str, page: int) -> None:
    loc = ctx.conversation.data.get("loc", {})
    prefix, body, button = {
        "L_REGION": ("LOC_R", ctx.t("loc_region"), ctx.t("btn_region")),
        "L_COUNTY": ("LOC_C", ctx.t("loc_county", region=loc.get("region", "")), ctx.t("btn_county")),
        "L_SUB_COUNTY": (
            "LOC_S",
            ctx.t("loc_sub_county", county=loc.get("county", "")),
            ctx.t("btn_sub_county"),
        ),
        "L_WARD": (
            "LOC_W",
            ctx.t("loc_ward", county=loc.get("county", ""), sub_county=loc.get("sub_county", "")),
            ctx.t("btn_ward"),
        ),
    }[step]
    options = _location_options(ctx, step)
    if len(options) > 10:
        pages = (len(options) + PAGE_SIZE - 1) // PAGE_SIZE
        page %= pages
        shown = options[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
        rows = [(f"{prefix}:{o}", o, "") for o in shown]
        rows.append((f"LOC_MORE:{step}:{(page + 1) % pages}", ctx.t("row_more"), f"{page + 1}/{pages}"))
    else:
        rows = [(f"{prefix}:{o}", o, "") for o in options]
    ctx.go(step)
    wa.send_list(ctx.phone, body, button, rows)


def _pick(ctx: Ctx, step: str, value: str) -> bool:
    """Whether ``value`` is a valid choice for the step the farmer is on."""
    if ctx.conversation.step != step:
        return False
    return value in _location_options(ctx, step)


def ask_location_again(ctx: Ctx) -> None:
    _location_list(ctx, ctx.conversation.step, 0)


def more_locations(ctx: Ctx, value: str) -> None:
    step, _, page = value.partition(":")
    if step not in LOCATION_STEPS or ctx.conversation.step != step or not page.isdigit():
        return show_menu(ctx)
    _location_list(ctx, step, int(page))


def _set_loc(ctx: Ctx, **values) -> None:
    ctx.go(ctx.conversation.step, loc={**ctx.conversation.data.get("loc", {}), **values})


def choose_region(ctx: Ctx, value: str) -> None:
    if not _pick(ctx, "L_REGION", value):
        return show_menu(ctx)
    _set_loc(ctx, region=value)
    _location_list(ctx, "L_COUNTY", 0)


def choose_county(ctx: Ctx, value: str) -> None:
    if not _pick(ctx, "L_COUNTY", value):
        return show_menu(ctx)
    _set_loc(ctx, county=value)
    _location_list(ctx, "L_SUB_COUNTY", 0)


def choose_sub_county(ctx: Ctx, value: str) -> None:
    if not _pick(ctx, "L_SUB_COUNTY", value):
        return show_menu(ctx)
    _set_loc(ctx, sub_county=value)
    _location_list(ctx, "L_WARD", 0)


def choose_ward(ctx: Ctx, value: str) -> None:
    if not _pick(ctx, "L_WARD", value):
        return show_menu(ctx)
    loc = ctx.conversation.data["loc"]
    FarmerProfile.objects.filter(user=ctx.user).update(
        county=loc["county"], sub_county=loc["sub_county"], ward=value, updated_at=timezone.now()
    )
    wa.send_text(
        ctx.phone, ctx.t("loc_saved", county=loc["county"], sub_county=loc["sub_county"], ward=value)
    )
    if ctx.conversation.data.get("then") == "report":
        return start_report(ctx)
    show_menu(ctx)


# =============================================================================
# Menu and simple screens
# =============================================================================


def show_menu(ctx: Ctx) -> None:
    if ctx.user is None:
        return _welcome(ctx)
    ctx.reset()
    rows = [
        ("REPORT", ctx.t("row_report"), ctx.t("row_report_d")),
        ("CASES", ctx.t("row_cases"), ctx.t("row_cases_d")),
        ("ORDERS", ctx.t("row_orders"), ctx.t("row_orders_d")),
        ("REWARDS", ctx.t("row_rewards"), ctx.t("row_rewards_d")),
        ("LOCATION", ctx.t("row_location"), ctx.t("row_location_d")),
        ("LANGUAGE", ctx.t("row_language"), ctx.t("row_language_d")),
        ("HELP", ctx.t("row_help"), ctx.t("row_help_d")),
    ]
    wa.send_list(
        ctx.phone,
        ctx.t("menu_body", first=ctx.first()),
        ctx.t("menu_button"),
        rows,
        header="🌱 AgriSense Hub",
    )


def ask_language(ctx: Ctx) -> None:
    wa.send_buttons(ctx.phone, ctx.t("ask_language"), [(f"LANG:{c}", n) for c, n in LANGUAGES])


def set_language(ctx: Ctx, code: str) -> None:
    if code not in dict(LANGUAGES):
        return ask_language(ctx)
    FarmerProfile.objects.filter(user=ctx.user).update(language=code, updated_at=timezone.now())
    wa.send_text(ctx.phone, ctx.t("language_set"))
    show_menu(ctx)


def show_help(ctx: Ctx) -> None:
    wa.send_buttons(ctx.phone, ctx.t("help"), [ctx.menu_button()])


def show_rewards(ctx: Ctx) -> None:
    wa.send_buttons(ctx.phone, ctx.t("rewards", balance=balance(ctx.user)), [ctx.menu_button()])


def show_cases(ctx: Ctx) -> None:
    cases = list(
        Case.objects.filter(farmer=ctx.user)
        .exclude(status=Case.Status.DRAFT)
        .select_related("final_diagnosis__disease")
        .order_by("-created_at")[:5]
    )
    if not cases:
        return wa.send_buttons(
            ctx.phone, ctx.t("cases_empty"), [("REPORT", ctx.t("row_report")), ctx.menu_button()]
        )
    lines = [ctx.t("cases_title"), ""]
    buttons = []
    for case in cases:
        final = getattr(case, "final_diagnosis", None)
        disease = final.disease.display_name(ctx.lang) if final else "…"
        lines.append(
            f"• {timezone.localtime(case.created_at):%d %b}: {disease} ({case.get_status_display()})"
        )
        prescription = case.prescriptions.order_by("-created_at").first()
        if (
            prescription
            and not prescription.is_expired
            and not buttons
            and case.status in purchases.PURCHASABLE_CASE_STATUSES
        ):
            lines.append(f"  💊 {prescription.code}")
            buttons.append((f"BUYRX:{prescription.code}", ctx.t("btn_find_stores")))
    wa.send_buttons(ctx.phone, "\n".join(lines), [*buttons, ctx.menu_button()])


def show_orders(ctx: Ctx) -> None:
    orders = list(
        Order.objects.filter(farmer=ctx.user)
        .select_related("product", "agrovet", "prescription")
        .order_by("-created_at")[:5]
    )
    if not orders:
        return wa.send_buttons(ctx.phone, ctx.t("orders_empty"), [ctx.menu_button()])
    lines = [ctx.t("orders_title"), ""]
    for o in orders:
        label = o.verifications.filter(type=Verification.Type.LABEL_CHECK).order_by("-created_at").first()
        extra = f" · {label.get_result_display()}" if label else ""
        lines.append(
            f"• {o.product.name}, KES {o.total_kes} @ {o.agrovet.name}: "
            f"{o.get_status_display()}{extra} ({o.prescription.code})"
        )
    wa.send_buttons(ctx.phone, "\n".join(lines), [ctx.menu_button()])


# =============================================================================
# Report a problem (Detect, process 2.0)
# =============================================================================


def _current_case(ctx: Ctx) -> Case | None:
    case_id = ctx.conversation.data.get("case_id")
    return Case.objects.filter(pk=case_id, farmer=ctx.user).first() if case_id else None


def start_report(ctx: Ctx) -> None:
    profile = FarmerProfile.objects.filter(user=ctx.user).only("ward").first()
    if profile is None or not profile.ward:  # the ward routes the case to nearby agrovets
        return start_location(ctx, then="report")
    case = (
        Case.objects.filter(farmer=ctx.user, status=Case.Status.DRAFT, channel=Case.Channel.WHATSAPP)
        .order_by("-created_at")
        .first()
    )
    farm = ctx.user.farms.order_by("created_at").first()
    if case is None:
        case = detect.start_case(ctx.user, farm=farm, channel=Case.Channel.WHATSAPP)
    ctx.reset("R_PHOTO")
    ctx.go("R_PHOTO", case_id=str(case.pk), resubmit=False)
    if farm is None and case.latitude is None:
        ctx.go("R_LOCATION")
        return wa.queue(ctx.phone, wa.location_request_payload(ctx.t("ask_location")))
    _ask_next_photo(ctx, case)


def location_received(ctx: Ctx) -> None:
    case = _current_case(ctx)
    if case is None:
        return show_menu(ctx)
    if ctx.message.kind == "location" and ctx.message.latitude is not None:
        Case.objects.filter(pk=case.pk).update(
            latitude=ctx.message.latitude, longitude=ctx.message.longitude, updated_at=timezone.now()
        )
    elif ctx.word not in SKIP_WORDS:
        return wa.queue(ctx.phone, wa.location_request_payload(ctx.t("ask_location")))
    ctx.go("R_PHOTO")
    _ask_next_photo(ctx, case)


def _missing_photos(case: Case, resubmit: bool, received: list[str]) -> list[str]:
    if resubmit:  # after a retake request, all three photos are taken again
        return [t for t in PHOTO_ORDER if t not in received]
    present = set(case.photos.values_list("type", flat=True))
    return [t for t in PHOTO_ORDER if t not in present]


def _ask_next_photo(ctx: Ctx, case: Case) -> None:
    data = ctx.conversation.data
    missing = _missing_photos(case, data.get("resubmit", False), data.get("received", []))
    if missing:
        ctx.go("R_PHOTO", photo_type=missing[0])
        return wa.send_text(ctx.phone, ctx.t(f"photo_{missing[0]}"))
    if data.get("resubmit") and case.symptom_answers:
        return _submit(ctx, case)
    _ask_started(ctx)


def photo_received(ctx: Ctx) -> None:
    case = _current_case(ctx)
    if case is None:
        return show_menu(ctx)
    if ctx.message.kind != "image":
        return wa.send_text(ctx.phone, ctx.t("need_photo"))
    photo_type = ctx.conversation.data.get("photo_type") or PHOTO_ORDER[0]
    content, _mime = wa.download_media(ctx.message.media_id)
    if len(content) > settings.DETECT["MAX_PHOTO_BYTES"]:
        return wa.send_text(ctx.phone, retake_message("too_small", ctx.lang))
    image = ContentFile(content, name=f"{photo_type}_{uuid.uuid4().hex[:8]}.jpg")
    try:
        detect.add_photo(case, photo_type, image)
    except PhotoQualityError as exc:
        return wa.send_text(ctx.phone, retake_message(exc.reason, ctx.lang))
    except detect.CaseNotEditableError:
        return show_menu(ctx)
    received = [*ctx.conversation.data.get("received", []), photo_type]
    ctx.go("R_PHOTO", received=received)
    _ask_next_photo(ctx, case)


def _ask_started(ctx: Ctx) -> None:
    ctx.go("R_QUESTIONS", answers={})
    rows = [(f"STARTED:{v}", ctx.t(f"started_{v}"), "") for v in STARTED]
    wa.send_list(ctx.phone, ctx.t("q_started"), ctx.t("btn_choose"), rows)


def _answer(ctx: Ctx, field: str, value) -> dict:
    answers = {**ctx.conversation.data.get("answers", {}), field: value}
    ctx.go("R_QUESTIONS", answers=answers)
    return answers


def answer_started(ctx: Ctx, value: str) -> None:
    if ctx.conversation.step != "R_QUESTIONS" or value not in STARTED:
        return _ask_started(ctx) if ctx.conversation.step == "R_QUESTIONS" else show_menu(ctx)
    _answer(ctx, "started", value)
    wa.send_buttons(ctx.phone, ctx.t("q_share"), [(f"SHARE:{v}", ctx.t(f"share_{v}")) for v in SHARE])


def answer_share(ctx: Ctx, value: str) -> None:
    if ctx.conversation.step != "R_QUESTIONS" or value not in SHARE:
        return show_menu(ctx)
    _answer(ctx, "share_affected", value)
    rows = [(f"WEATHER:{v}", ctx.t(f"weather_{v}"), "") for v in WEATHER]
    wa.send_list(ctx.phone, ctx.t("q_weather"), ctx.t("btn_choose"), rows)


def answer_weather(ctx: Ctx, value: str) -> None:
    if ctx.conversation.step != "R_QUESTIONS" or value not in WEATHER:
        return show_menu(ctx)
    # WhatsApp lists allow one choice; the app's question allows several.
    _answer(ctx, "recent_weather", [value])
    wa.send_buttons(
        ctx.phone, ctx.t("q_sprayed"), [("SPRAYED:yes", ctx.t("btn_yes")), ("SPRAYED:no", ctx.t("btn_no"))]
    )


def answer_sprayed(ctx: Ctx, value: str) -> None:
    if ctx.conversation.step != "R_QUESTIONS" or value not in ("yes", "no"):
        return show_menu(ctx)
    answers = _answer(ctx, "already_sprayed", value == "yes")
    if value == "yes":
        ctx.go("R_SPRAYED_PRODUCT")
        return wa.send_text(ctx.phone, ctx.t("ask_sprayed_product"))
    _save_and_submit(ctx, answers)


def sprayed_product_typed(ctx: Ctx) -> None:
    typed = (ctx.message.text or "").strip()
    answers = dict(ctx.conversation.data.get("answers", {}))
    answers["sprayed_product"] = "" if typed.lower() in SKIP_WORDS else typed[:200]
    _save_and_submit(ctx, answers)


def _save_and_submit(ctx: Ctx, answers: dict) -> None:
    from apps.cases.serializers import SymptomAnswersSerializer

    case = _current_case(ctx)
    if case is None:
        return show_menu(ctx)
    serializer = SymptomAnswersSerializer(data=answers)
    if not serializer.is_valid():
        logger.warning("Invalid WhatsApp answers for case %s: %s", case.pk, serializer.errors)
        return _ask_started(ctx)
    detect.save_answers(case, dict(serializer.validated_data))
    _submit(ctx, case)


def _submit(ctx: Ctx, case: Case) -> None:
    try:
        detect.submit_case(case)
    except detect.IncompleteCaseError:
        ctx.go("R_PHOTO", resubmit=False)
        return _ask_next_photo(ctx, case)
    except detect.CaseNotEditableError:
        return show_menu(ctx)
    except Exception:
        logger.exception("Submitting WhatsApp case %s failed", case.pk)
        raise
    ctx.reset()
    wa.send_buttons(ctx.phone, ctx.t("submitted"), [ctx.menu_button()])


def retake_photos(ctx: Ctx, case_id: str) -> None:
    """RETAKE:<case_id>, sent with the 'retake photos' notification after the AI check."""
    case = Case.objects.filter(pk=_uuid(case_id), farmer=ctx.user).first()
    if case is None or not detect.is_editable(case):
        return show_menu(ctx)
    ctx.reset("R_PHOTO")
    ctx.go("R_PHOTO", case_id=str(case.pk), resubmit=True, received=[])
    _ask_next_photo(ctx, case)


def _uuid(value):
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


# =============================================================================
# Buying the prescribed product (Module 4)
# =============================================================================


def _purchase_error(ctx: Ctx, exc: purchases.PurchaseError, buttons=None) -> None:
    logger.info("Purchase step refused for %s: %s (%s)", ctx.phone, exc.code, exc)
    wa.send_buttons(ctx.phone, f"⚠️ {exc}", buttons or [ctx.menu_button()])


def show_stores(ctx: Ctx, code: str) -> None:
    try:
        prescription = purchases.get_prescription_for_farmer(ctx.user, code)
        offers = purchases.find_stores(prescription)
    except purchases.PurchaseError as exc:
        return _purchase_error(ctx, exc)
    if not offers:
        return wa.send_buttons(ctx.phone, ctx.t("no_stores"), [ctx.menu_button()])
    rows = []
    for offer in offers:
        item = offer.store_item
        distance = f" · {offer.distance_km:g} km" if offer.distance_km is not None else ""
        rows.append(
            (
                f"STORE:{item.pk}",
                item.agrovet.name,
                f"KES {item.price_kes}{distance} · {item.product.name} · {item.product.pcpb_reg_no}",
            )
        )
    ctx.reset("B_STORE")
    ctx.go("B_STORE", code=prescription.code)
    wa.send_list(ctx.phone, ctx.t("stores_body", code=prescription.code), ctx.t("stores_button"), rows)


def choose_store(ctx: Ctx, store_item_id: str) -> None:
    from apps.agrovets.models import StoreItem

    code = ctx.conversation.data.get("code")
    item = StoreItem.objects.select_related("agrovet", "product").filter(pk=_uuid(store_item_id)).first()
    if not code or item is None:
        return show_menu(ctx)
    ctx.go("B_PAY", store_item_id=str(item.pk))
    wa.send_buttons(
        ctx.phone,
        ctx.t(
            "store_detail",
            product=item.product.name,
            pcpb=item.product.pcpb_reg_no,
            agrovet=item.agrovet.name,
            distance="",
            price=item.price_kes,
        ),
        [("PAY:mpesa", ctx.t("btn_pay_mpesa")), ("PAY:shop", ctx.t("btn_pay_shop")), ctx.menu_button()],
    )


def choose_payment(ctx: Ctx, method: str) -> None:
    data = ctx.conversation.data
    if ctx.conversation.step != "B_PAY" or method not in ("mpesa", "shop"):
        return show_menu(ctx)
    try:
        prescription = purchases.get_prescription_for_farmer(ctx.user, data.get("code", ""))
        order = purchases.create_order(
            farmer=ctx.user,
            prescription=prescription,
            store_item_id=data.get("store_item_id"),
            quantity=1,
            payment_method=Order.PaymentMethod.MPESA
            if method == "mpesa"
            else Order.PaymentMethod.PAY_AT_SHOP,
        )
    except purchases.PurchaseError as exc:
        return _purchase_error(ctx, exc)
    if method == "shop":
        ctx.reset()
        return wa.send_buttons(
            ctx.phone,
            ctx.t("reserved", agrovet=order.agrovet.name, code=prescription.code),
            [ctx.menu_button()],
        )
    _pay(ctx, order)


def retry_payment(ctx: Ctx, order_id: str) -> None:
    order = Order.objects.filter(pk=_uuid(order_id), farmer=ctx.user).first()
    if order is None:
        return show_menu(ctx)
    _pay(ctx, order)


def _pay(ctx: Ctx, order: Order) -> None:
    try:
        purchases.initiate_payment(farmer=ctx.user, order=order, phone=ctx.phone)
    except purchases.PurchaseError as exc:
        return _purchase_error(
            ctx, exc, [(f"RETRYPAY:{order.pk}", ctx.t("btn_try_again")), ctx.menu_button()]
        )
    ctx.reset("B_WAIT")
    wa.send_text(ctx.phone, ctx.t("stk_sent", amount=order.total_kes))


def ask_label(ctx: Ctx, order_id: str) -> None:
    order = (
        Order.objects.select_related("agrovet", "product")
        .filter(pk=_uuid(order_id), farmer=ctx.user, status=Order.Status.COLLECTED)
        .first()
    )
    if order is None:
        return show_menu(ctx)
    ctx.reset("LABEL")
    ctx.go("LABEL", order_id=str(order.pk))
    wa.send_text(ctx.phone, ctx.t("label_prompt", agrovet=order.agrovet.name, product=order.product.name))


LABEL_KEYS = {
    Verification.Result.VERIFIED: "label_verified",
    Verification.Result.NOT_REGISTERED: "label_not_registered",
    Verification.Result.NOT_PRESCRIBED: "label_not_prescribed",
    Verification.Result.UNREADABLE: "label_unreadable",
}


def label_received(ctx: Ctx) -> None:
    order = (
        Order.objects.select_related("product", "prescription")
        .filter(pk=_uuid(ctx.conversation.data.get("order_id")), farmer=ctx.user)
        .first()
    )
    if order is None:
        return show_menu(ctx)
    if ctx.message.kind != "image":
        return wa.send_text(ctx.phone, ctx.t("need_photo"))
    wa.send_text(ctx.phone, ctx.t("label_checking"))
    content, _mime = wa.download_media(ctx.message.media_id)
    try:
        verification = purchases.label_check(farmer=ctx.user, order=order, photo=content)
    except purchases.PurchaseError as exc:
        return _purchase_error(ctx, exc)

    result = verification.result
    if result == Verification.Result.UNREADABLE:
        return wa.send_text(ctx.phone, ctx.t("label_unreadable"))  # stay on LABEL for a retake
    ctx.reset()
    buttons = [ctx.menu_button()]
    values = {}
    if result == Verification.Result.VERIFIED:
        values = {
            "product": order.product.name,
            "points": settings.PURCHASES["REWARD_POINTS_VERIFIED_PURCHASE"],
            "balance": balance(ctx.user),
        }
    elif result == Verification.Result.NOT_REGISTERED:
        buttons = [(f"BUYRX:{order.prescription.code}", ctx.t("btn_find_stores")), ctx.menu_button()]
    wa.send_buttons(ctx.phone, ctx.t(LABEL_KEYS[result], **values), buttons)
