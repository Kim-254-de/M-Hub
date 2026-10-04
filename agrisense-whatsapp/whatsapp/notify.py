"""Messages the system sends on its own (payment results, agrovet reviews, follow-ups)."""
import logging

from django.conf import settings

from core.models import Agrovet, Diagnosis, Order

from . import client as wa
from .messages import t
from .models import ChatSession

log = logging.getLogger(__name__)


def first_name(farmer):
    return (farmer.full_name or farmer.whatsapp_name or "").split(" ")[0] or "farmer"


def media_url(diagnosis):
    if not diagnosis.image:
        return ""
    base = "" if settings.WA_TRANSPORT == "web" else settings.PUBLIC_BASE_URL
    return f"{base}/media/{diagnosis.image.name}"


def _set_step(phone, step, **data):
    session, _ = ChatSession.objects.get_or_create(phone=phone)
    session.step = step
    session.data = data
    session.save()


# --- payments --------------------------------------------------------------

def order_paid(order: Order):
    f, p = order.farmer, order.product
    a = p.agrovet
    wa.send_buttons(
        f.phone,
        t("paid", f.language, receipt=order.mpesa_receipt or "-", qty=order.quantity, name=p.name,
          agrovet=a.name, town=a.town or a.county, hint=a.location_hint, code=order.pickup_code),
        [("MENU", t("btn_menu", f.language))],
    )
    wa.send_buttons(
        a.phone,
        f"🛒 *New paid AgriSense order #{order.pk}*\n\n{order.quantity} × {p.name} {p.pack_size}\n"
        f"PCPB No: {p.pcpb_reg_no or '-'}\nFarmer: {f.full_name} ({f.phone})\nAmount: KES {order.amount}\n"
        f"M-Pesa: {order.mpesa_receipt}\nPickup code: *{order.pickup_code}*\n\n"
        "When the farmer shows this code, hand over the product and tap below.",
        [(f"HANDOVER:{order.pk}", "✅ Handed over")],
    )
    _set_step(f.phone, "MAIN_MENU")


def order_failed(order: Order, reason=""):
    f = order.farmer
    wa.send_buttons(
        f.phone,
        t("pay_failed", f.language, reason=reason or "cancelled"),
        [(f"RETRY_PAY:{order.pk}", t("btn_retry_pay", f.language)), ("MENU", t("btn_menu", f.language))],
    )
    _set_step(f.phone, "MAIN_MENU")


# --- pickup and label check ------------------------------------------------

def ask_label_photo(order: Order):
    """After hand-over, ask the farmer to photograph the label (Documentation §6.4, step 4)."""
    f, p = order.farmer, order.product
    wa.send_text(f.phone, t("label_prompt", f.language, agrovet=p.agrovet.name, name=p.name))
    _set_step(f.phone, "LABEL_PHOTO", order_id=order.pk)


def label_failed(order: Order):
    """Tell the store a label check failed, so staff can investigate (store rules, §6.4)."""
    p = order.product
    wa.send_text(
        p.agrovet.phone,
        f"⚠️ *Label check failed for order #{order.pk}*\n\n{p.name}: the farmer's label shows "
        f"{order.label_reg_no or 'no PCPB number'} ({order.get_label_result_display()}). "
        "AgriSense will contact you about this.",
    )


# --- human-in-the-loop review ----------------------------------------------

def request_review(diagnosis: Diagnosis):
    """Send the farmer's photo to verified agrovets in the same county. Returns how many were notified."""
    farmer = diagnosis.farmer
    agrovets = Agrovet.objects.filter(is_verified=True, county__iexact=farmer.county)
    caption = (
        f"🔎 *Review request #{diagnosis.pk}*\nCrop: {diagnosis.crop}\n"
        f"AI suggestion: {diagnosis.disease or 'unknown'} ({round(diagnosis.confidence * 100)}%)\n"
        f"Farmer: {farmer.full_name}, {farmer.ward or farmer.county}"
    )
    count = 0
    for agrovet in agrovets:
        link = media_url(diagnosis)
        if link:
            wa.send_image(agrovet.phone, link, caption)
        else:
            wa.send_text(agrovet.phone, caption)
        wa.send_buttons(
            agrovet.phone,
            "Is the AI suggestion correct?",
            [(f"REV_OK:{diagnosis.pk}", "✅ Correct"), (f"REV_FIX:{diagnosis.pk}", "📝 Correct it")],
        )
        count += 1
    return count


def diagnosis_reviewed(diagnosis: Diagnosis):
    f = diagnosis.farmer
    key = "agrovet_confirmed" if diagnosis.status == Diagnosis.STATUS_CONFIRMED else "agrovet_corrected"
    agrovet = diagnosis.reviewed_by.name if diagnosis.reviewed_by else "A verified agrovet"
    wa.send_buttons(
        f.phone,
        t(key, f.language, agrovet=agrovet, crop=diagnosis.crop, disease=diagnosis.disease,
          note=f"\n{diagnosis.agrovet_note}" if diagnosis.agrovet_note else ""),
        [(f"BUY:{diagnosis.pk}", t("btn_buy", f.language)), ("MENU", t("btn_menu", f.language))],
    )


# --- outcome follow-up -----------------------------------------------------

def send_followup(order: Order, use_template=True):
    """Ask whether the treatment worked. Templates are required after the 24-hour window."""
    d = order.diagnosis
    f = order.farmer
    if not d:
        return {}
    payloads = [f"OUT:{d.pk}:worked", f"OUT:{d.pk}:partly", f"OUT:{d.pk}:no_change"]
    if use_template:
        return wa.send_template(
            f.phone, settings.WA_FOLLOWUP_TEMPLATE, settings.WA_FOLLOWUP_TEMPLATE_LANG,
            body_params=[first_name(f), d.disease, d.crop], button_payloads=payloads,
        )
    return wa.send_buttons(
        f.phone,
        t("followup", f.language, first=first_name(f), disease=d.disease, crop=d.crop),
        list(zip(payloads, [t("btn_worked", f.language), t("btn_partly", f.language),
                            t("btn_no_change", f.language)])),
    )
