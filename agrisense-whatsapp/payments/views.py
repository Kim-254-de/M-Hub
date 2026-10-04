import json
import logging

from django.conf import settings
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.models import Order
from whatsapp import notify

from .mpesa import parse_callback

log = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def mpesa_callback(request, token):
    if token != settings.MPESA_CALLBACK_TOKEN:
        raise Http404
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"ResultCode": 1, "ResultDesc": "Bad JSON"})

    apply_result(parse_callback(body))
    return JsonResponse({"ResultCode": 0, "ResultDesc": "Accepted"})


def apply_result(result):
    """Mark the order paid/failed and message the farmer + agrovet. Shared by Daraja and the web demo."""
    order = Order.objects.filter(checkout_request_id=result["checkout_id"]).select_related(
        "farmer", "product__agrovet"
    ).first()
    if not order:
        log.warning("Callback for unknown checkout %s", result["checkout_id"])
        return None

    if order.status == Order.STATUS_PENDING:
        if result["ok"]:
            order.status = Order.STATUS_PAID
            order.mpesa_receipt = result["receipt"]
            order.paid_at = timezone.now()
            order.save(update_fields=["status", "mpesa_receipt", "paid_at"])
            notify.order_paid(order)
        else:
            order.status = Order.STATUS_FAILED
            order.save(update_fields=["status"])
            notify.order_failed(order, result["result_desc"])
    return order
