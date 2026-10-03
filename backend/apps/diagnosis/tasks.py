import logging

from celery import shared_task

from .services import RunOutcome, retry_delay_seconds, run_ai_diagnosis

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=None, acks_late=True, ignore_result=True)
def run_ai_diagnosis_task(self, ai_diagnosis_id: str) -> None:
    """Run one AI identification. Retry policy and attempt limits live in services."""
    outcome = run_ai_diagnosis(ai_diagnosis_id)
    if outcome is RunOutcome.RETRY:
        from .models import AIDiagnosis

        attempts = (
            AIDiagnosis.objects.filter(pk=ai_diagnosis_id).values_list("attempts", flat=True).first() or 1
        )
        raise self.retry(countdown=retry_delay_seconds(attempts))


@shared_task(ignore_result=True)
def assign_reviews_task() -> None:
    """Every 10 minutes (Celery beat): reassign unanswered reviews and assign waiting cases."""
    from .review import assign_pending_reviews

    assign_pending_reviews()
