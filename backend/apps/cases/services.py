from django.utils import timezone

from .models import Case


def transition(case_id, *, from_statuses, to) -> bool:
    """Move a case to ``to`` only if it is currently in one of ``from_statuses``.

    A single conditional UPDATE, so concurrent actors cannot move a case
    backwards or skip a state. Returns True if the case was moved.
    """
    updated = Case.objects.filter(pk=case_id, status__in=list(from_statuses)).update(
        status=to, updated_at=timezone.now()
    )
    return bool(updated)
