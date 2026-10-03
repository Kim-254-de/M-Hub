"""Kikuyu advisory evaluation.

python manage.py advisory_eval export-questions questions.csv   # for Kikuyu speakers to rewrite
python manage.py advisory_eval import-questions questions.csv
python manage.py advisory_eval run --reps 2 [--approve-harness]   # calls the model (costs money)
python manage.py advisory_eval sheets --raters wanjiku,kamau,njeri  # blind rating sheets
python manage.py advisory_eval score rater_wanjiku.csv rater_kamau.csv ...
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.advisory.evaluation import runner


class Command(BaseCommand):
    help = "Evaluate the Kikuyu crop adviser with blind human ratings."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)
        p = sub.add_parser("export-questions")
        p.add_argument("path")
        p = sub.add_parser("import-questions")
        p.add_argument("path")
        p = sub.add_parser("run")
        p.add_argument("--variant", default="baseline")
        p.add_argument("--model", default=settings.ADVISORY["MODEL"])
        p.add_argument("--reps", type=int, default=2)
        p.add_argument("--question-language", default="ki", choices=["ki", "sw", "en"])
        p.add_argument("--workers", type=int, default=4)
        p.add_argument("--timeout-s", type=float, default=180)
        p.add_argument("--limit", type=int, help="Only the first N cases (pilot)")
        p.add_argument("--approve-harness", action="store_true", help="Accept the current prompt/guard/cases")
        p = sub.add_parser("sheets")
        p.add_argument("--variant", default="baseline")
        p.add_argument("--raters", required=True, help="Comma-separated rater names")
        p = sub.add_parser("score")
        p.add_argument("paths", nargs="+")
        p.add_argument("--variant", default="baseline")

    def handle(self, *args, action, **options):
        try:
            getattr(self, "do_" + action.replace("-", "_"))(**options)
        except runner.EvalError as exc:
            raise CommandError(str(exc)) from exc

    def do_export_questions(self, path, **_):
        n = runner.export_questions(Path(path))
        self.stdout.write(f"Wrote {n} questions to {path}. Kikuyu speakers fill the 'kikuyu' column.")

    def do_import_questions(self, path, **_):
        updated, unknown = runner.import_questions(Path(path))
        for case_id in unknown:
            self.stderr.write(f"Unknown case id: {case_id}")
        self.stdout.write(f"Updated {updated} Kikuyu question(s) in {runner.CASES_PATH.name}.")

    def do_run(
        self, variant, model, reps, question_language, workers, timeout_s, limit, approve_harness, **_
    ):
        counts = runner.run(
            variant=variant,
            model=model,
            reps=reps,
            question_language=question_language,
            workers=workers,
            timeout_s=timeout_s,
            limit=limit,
            approve_harness=approve_harness,
            log=self.stdout.write,
        )
        self.stdout.write(
            f"Done: {counts['ok']} answered, {counts['errors']} error(s). Output in {runner.FLOW_DIR}"
        )

    def do_sheets(self, variant, raters, **_):
        folder = runner.make_sheets(variant, [r.strip() for r in raters.split(",") if r.strip()])
        self.stdout.write(f"Rating sheets in {folder}. Give each rater only their own rater_<name>.csv.")

    def do_score(self, paths, variant, **_):
        s = runner.score(variant, [Path(p) for p in paths])
        low, high = s["acceptable_ci"]
        self.stdout.write(
            f"Rated {s['rated']} of {s['rows']} answers. Acceptable: {s['acceptable']}/{s['rated']} "
            f"(95% CI {low:.0%}-{high:.0%}). Blocked by the automatic check: {s['auto_blocked']}. "
            f"Judged unsafe by a rater: {s['human_unsafe']}."
        )
        if s["rater_agreement"] is not None:
            self.stdout.write(f"Raters agreed on acceptable/not for {s['rater_agreement']:.0%} of answers.")
        for category, (ok, n) in s["by_category"].items():
            self.stdout.write(f"  {category}: {ok}/{n} acceptable")
