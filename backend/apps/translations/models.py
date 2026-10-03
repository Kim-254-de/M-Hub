"""Human translations of farmer-facing text into languages not written in code (Kikuyu first)."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.core.models import TimeStampedModel

from . import catalog


class Translation(TimeStampedModel):
    """One message in one language. Shown to farmers only when approved and still current."""

    class Status(models.TextChoices):
        DRAFT = "draft"
        APPROVED = "approved"

    key = models.CharField(max_length=128, help_text='Catalog key, e.g. "followups.advice.stopped"')
    language = models.CharField(max_length=8, help_text='Language code, e.g. "ki"')
    text = models.TextField()
    source_text = models.TextField(help_text="The English this was translated from")
    source_checksum = models.CharField(max_length=16, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    translated_by = models.CharField(max_length=128, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ("language", "key")
        constraints = [
            models.UniqueConstraint(fields=["key", "language"], name="translations_one_per_key_and_language"),
        ]
        permissions = [("approve_translation", "Can approve translations shown to farmers")]

    def __str__(self):
        return f"{self.key} [{self.language}]"

    @property
    def source(self) -> catalog.Source | None:
        return catalog.get_source(self.key)

    @property
    def is_current(self) -> bool:
        """False once the English changes: the translation must be redone and reviewed again."""
        source = self.source
        return source is not None and self.source_checksum == source.checksum

    def problems(self) -> list[str]:
        source = self.source
        if source is None:
            return [f'"{self.key}" is not a message in the catalog.']
        if self.language in source.texts:
            return [f'"{self.language}" text for this message is written in code, not translated here.']
        return source.problems(self.text)

    def clean(self):
        errors = self.problems()
        if errors:
            raise ValidationError({"text": errors})

    def save(self, *args, **kwargs):
        self.source_checksum = catalog.checksum(self.source_text)
        if self.pk and self.status == self.Status.APPROVED:
            before = type(self).objects.filter(pk=self.pk).values_list("text", "source_text").first()
            if before is not None and before != (self.text, self.source_text):
                # Any edit needs a fresh review.
                self.status, self.reviewed_by, self.reviewed_at = self.Status.DRAFT, None, None
        super().save(*args, **kwargs)

    def approve(self, reviewer) -> None:
        errors = self.problems()
        if not errors and not self.is_current:
            errors = ["The English has changed since this was translated. Translate it again."]
        if errors:
            raise ValidationError(errors)
        with transaction.atomic():
            # Not save(): approving must not count as an edit.
            now = timezone.now()
            type(self).objects.filter(pk=self.pk).update(
                status=self.Status.APPROVED, reviewed_by=reviewer, reviewed_at=now, updated_at=now
            )
        self.status, self.reviewed_by, self.reviewed_at = self.Status.APPROVED, reviewer, now
