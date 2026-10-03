"""Load a translator's CSV (from ``export_translations``) as draft translations.

    python manage.py import_translations kikuyu.csv --language ki --translator "Jane W."

Rows are checked (placeholders, SMS characters and length) and saved as drafts. Nothing is shown
to farmers until a reviewer approves it in the admin.
"""

import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.translations import catalog
from apps.translations.models import Translation


class Command(BaseCommand):
    help = "Import translated messages from CSV as drafts for review."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--language", required=True, help='Language code, e.g. "ki"')
        parser.add_argument("--translator", required=True, help="Who translated the file")

    def handle(self, *args, path, language, translator, **options):
        try:
            with open(path, newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
        except OSError as exc:
            raise CommandError(f"Cannot read {path}: {exc}") from exc
        if rows and not {"key", "english", "translation"} <= set(rows[0]):
            raise CommandError("The CSV needs the columns key, english and translation.")

        saved = unchanged = 0
        problems = []
        with transaction.atomic():
            for line, row in enumerate(rows, start=2):
                text = (row.get("translation") or "").strip()
                if not text:
                    continue
                key = row["key"].strip()
                source = catalog.get_source(key)
                if source is None:
                    problems.append(f"line {line}: {key}: not a message in the catalog")
                    continue
                if row["english"] != source.english:
                    problems.append(f"line {line}: {key}: the English has changed since export; export again")
                    continue
                translation = Translation.objects.filter(key=key, language=language).first() or Translation(
                    key=key, language=language
                )
                if translation.pk and translation.text == text and translation.is_current:
                    unchanged += 1
                    continue
                translation.text, translation.source_text = text, source.english
                translation.translated_by = translator
                errors = translation.problems()
                if errors:
                    problems.append(f"line {line}: {key}: {' '.join(errors)}")
                    continue
                translation.save()
                saved += 1

        for problem in problems:
            self.stderr.write(problem)
        self.stdout.write(
            f"Saved {saved} draft(s), {unchanged} unchanged, {len(problems)} problem(s). "
            "Drafts are shown to farmers only after a reviewer approves them in the admin."
        )
