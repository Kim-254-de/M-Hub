"""python manage.py send_followups --days 7

Asks farmers whether the treatment they bought worked. Run it daily (Render cron job).
Uses the approved WhatsApp template WA_FOLLOWUP_TEMPLATE because the 24-hour window has closed.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Order
from whatsapp import notify


class Command(BaseCommand):
    help = "Send 'did the treatment work?' follow-ups for paid orders."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7, help="Days after payment to ask.")
        parser.add_argument("--no-template", action="store_true",
                            help="Send normal buttons instead of a template (only works inside 24 h — for demos).")

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(days=opts["days"])
        orders = Order.objects.filter(
            status__in=[Order.STATUS_PAID, Order.STATUS_COLLECTED], followup_sent=False,
            paid_at__lte=cutoff, diagnosis__isnull=False, diagnosis__outcome="",
        ).select_related("farmer", "diagnosis")
        sent = 0
        for order in orders:
            if notify.send_followup(order, use_template=not opts["no_template"]):
                order.followup_sent = True
                order.save(update_fields=["followup_sent"])
                sent += 1
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} follow-up(s)."))
