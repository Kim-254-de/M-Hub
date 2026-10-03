from celery import shared_task

from . import services


@shared_task(ignore_result=True)
def review_prescribing_patterns_task() -> None:
    """Daily (Celery beat): lower trust for agrovets who favour price over local evidence."""
    services.review_prescribing_patterns()
