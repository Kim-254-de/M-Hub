from celery import shared_task

from .services import SendOutcome, retry_delay_seconds, send_sms


@shared_task(bind=True, max_retries=None, acks_late=True, ignore_result=True)
def send_sms_task(self, message_id: str) -> None:
    """Send one SMS. Retry policy and attempt limits live in services."""
    if send_sms(message_id) is SendOutcome.RETRY:
        from .models import SmsMessage

        attempts = SmsMessage.objects.filter(pk=message_id).values_list("attempts", flat=True).first() or 1
        raise self.retry(countdown=retry_delay_seconds(attempts))
