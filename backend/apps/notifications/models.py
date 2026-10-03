from django.db import models

from apps.core.models import TimeStampedModel


class SmsMessage(TimeStampedModel):
    """Outbox row for one SMS. Created inside the business transaction, sent after commit."""

    class Purpose(models.TextChoices):
        AI_RESULT = "ai_result"  # provisional AI suggestion, or "received" when the AI failed
        RETAKE_PHOTOS = "retake_photos"
        REVIEW_ASSIGNED = "review_assigned"  # to the agrovet
        DIAGNOSIS_CONFIRMED = "diagnosis_confirmed"
        DIAGNOSIS_UNKNOWN = "diagnosis_unknown"
        PRESCRIPTION_ISSUED = "prescription_issued"

    class Status(models.TextChoices):
        QUEUED = "queued"
        SENDING = "sending"
        SENT = "sent"  # accepted by Africa's Talking
        DELIVERED = "delivered"  # delivery report: on the handset
        FAILED = "failed"

    to = models.CharField(max_length=16, help_text="+2547XXXXXXXX")
    body = models.TextField()
    purpose = models.CharField(max_length=32, choices=Purpose.choices)
    # What the message is about, e.g. "case:<uuid>". With purpose and recipient, makes sending idempotent.
    source_ref = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    provider_message_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    provider_status = models.CharField(max_length=32, blank=True)
    cost = models.CharField(max_length=32, blank=True)
    error = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = "SMS message"
        constraints = [
            models.UniqueConstraint(fields=["purpose", "source_ref", "to"], name="notifications_sms_once"),
        ]

    def __str__(self):
        return f"SMS {self.purpose} to {self.to} ({self.status})"
