from django.db import models


class WebMessage(models.Model):
    """One chat bubble in the browser demo — sent by the person (in) or by AgriSense (out)."""

    IN, OUT, STK = "in", "out", "stk"
    KINDS = [(IN, "From user"), (OUT, "From AgriSense"), (STK, "M-Pesa prompt")]

    phone = models.CharField(max_length=15, db_index=True)
    direction = models.CharField(max_length=3, choices=KINDS)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
