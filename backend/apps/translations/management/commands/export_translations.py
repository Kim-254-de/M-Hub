"""Write the farmer-facing messages to a CSV for a translator.

    python manage.py export_translations --language ki --output kikuyu.csv

The translator fills the ``translation`` column only; import it with ``import_translations``.
"""

import csv
import sys

from django.core.management.base import BaseCommand

from apps.translations import catalog
from apps.translations.models import Translation

COLUMNS = (
    "key",
    "english",
    "kiswahili",
    "translation",
    "status",
    "placeholders",
    "safety",
    "sms_max_length",
)


def status_of(translation: Translation | None) -> str:
    if translation is None:
        return "missing"
    if not translation.is_current:
        return "english_changed"
    return translation.status


class Command(BaseCommand):
    help = "Export farmer-facing messages to CSV for translation."

    def add_arguments(self, parser):
        parser.add_argument("--language", required=True, help='Language code, e.g. "ki"')
        parser.add_argument("--output", help="CSV path (default: standard output)")

    def handle(self, *args, language, output=None, **options):
        existing = {t.key: t for t in Translation.objects.filter(language=language)}
        rows, counts = [], {}
        for source in catalog.sources():
            if language in source.texts:
                continue  # written in code
            translation = existing.get(source.key)
            status = status_of(translation)
            counts[status] = counts.get(status, 0) + 1
            rows.append(
                {
                    "key": source.key,
                    "english": source.english,
                    "kiswahili": source.texts.get("sw", ""),
                    "translation": translation.text if translation else "",
                    "status": status,
                    "placeholders": " ".join(
                        sorted(f"{{{p}}}" for p in catalog.placeholders(source.english))
                    ),
                    "safety": "yes" if source.safety else "",
                    "sms_max_length": source.max_length if source.sms else "",
                }
            )

        handle = open(output, "w", newline="", encoding="utf-8") if output else sys.stdout
        try:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        finally:
            if output:
                handle.close()
        summary = ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))
        self.stderr.write(f"{len(rows)} messages for '{language}': {summary or 'none'}")
