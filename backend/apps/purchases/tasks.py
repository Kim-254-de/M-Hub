from celery import shared_task

from . import services


@shared_task(ignore_result=True)
def reconcile_pending_payments_task() -> None:
    """Every 2 minutes (Celery beat): resolve STK payments whose callback never arrived."""
    services.reconcile_pending_payments()


@shared_task(ignore_result=True)
def expire_prescriptions_task() -> None:
    """Every 15 minutes (Celery beat): PRESCRIBED -> EXPIRED for unused prescriptions."""
    services.expire_prescriptions()
