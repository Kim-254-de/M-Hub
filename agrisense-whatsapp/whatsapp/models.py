from django.db import models


class ChatSession(models.Model):
    """Where each phone number is in the conversation (the bot's 'state machine' memory)."""

    phone = models.CharField(max_length=15, unique=True)
    step = models.CharField(max_length=40, default="START")
    data = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def go(self, step, **data):
        self.step = step
        if data:
            self.data.update(data)
        self.save()

    def reset(self, step="MAIN_MENU"):
        self.step = step
        self.data = {}
        self.save()

    def __str__(self):
        return f"{self.phone} @ {self.step}"


class ProcessedMessage(models.Model):
    """Meta can deliver the same webhook more than once; we handle each message id once."""

    wamid = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
