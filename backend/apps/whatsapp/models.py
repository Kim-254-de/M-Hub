"""WhatsApp channel (Documentation §5, process 1.0 Register and Route)."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class Conversation(TimeStampedModel):
    """Where one phone number is in the chat flow. Locked while a message is handled."""

    phone = models.CharField(max_length=16, unique=True, help_text="+2547XXXXXXXX")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_conversation",
    )
    profile_name = models.CharField(
        max_length=100, blank=True, help_text="Name shown on the WhatsApp profile"
    )
    step = models.CharField(max_length=40, default="START")
    data = models.JSONField(default=dict, blank=True)
    # Meta only allows free-form messages within 24 hours of the farmer's last message.
    last_inbound_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.phone} @ {self.step}"


class InboundMessage(TimeStampedModel):
    """One message received from a farmer, stored before it is handled so nothing is lost."""

    class Status(models.TextChoices):
        RECEIVED = "received"
        PROCESSING = "processing"
        DONE = "done"
        FAILED = "failed"

    wamid = models.CharField(
        max_length=200, unique=True, help_text="WhatsApp message id; de-duplicates retries"
    )
    phone = models.CharField(max_length=16, db_index=True)
    kind = models.CharField(max_length=16)  # text | reply | image | location | other
    text = models.TextField(blank=True)
    reply_id = models.CharField(max_length=200, blank=True)
    media_id = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=64, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    profile_name = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        indexes = [models.Index(fields=["phone", "-created_at"])]

    def __str__(self):
        return f"{self.kind} from {self.phone} ({self.status})"


class OutboundMessage(TimeStampedModel):
    """One message to send. With the web transport, these rows are what the simulator page shows."""

    class Status(models.TextChoices):
        QUEUED = "queued"
        SENDING = "sending"
        SENT = "sent"
        FAILED = "failed"

    phone = models.CharField(max_length=16, db_index=True)
    # The exact Cloud API "messages" body, so the simulator renders what WhatsApp would show.
    payload = models.JSONField()
    # Set for system notifications so each event is sent once; empty for chat replies.
    source_ref = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    provider_message_id = models.CharField(max_length=200, blank=True)
    error = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["phone", "source_ref"], condition=~Q(source_ref=""), name="whatsapp_notification_once"
            ),
        ]

    def __str__(self):
        return f"To {self.phone}: {self.payload.get('type')} ({self.status})"
