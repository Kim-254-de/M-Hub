"""Kikuyu adviser: guard, grounding, provider wiring and the evaluation runner. No network calls."""

import csv
import json
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from apps.accounts.models import User
from apps.advisory import guard
from apps.advisory.context import CaseContext, Stage, context_for_case
from apps.advisory.evaluation import runner
from apps.advisory.messages import fallback_message
from apps.advisory.providers import ProviderError, Reply
from apps.advisory.providers.claude import FALLBACK_BETA, ClaudeProvider
from apps.advisory.providers.gemini import GeminiProvider
from apps.advisory.services import advise, advise_or_fallback
from apps.cases.models import Case
from apps.products.models import Product

pytestmark = pytest.mark.django_db

MODEL = "gemini-3.8-flash"
CONTEXT = CaseContext(stage=Stage.CONFIRMED, disease="Late blight", share_affected="some")


class FakeProvider:
    def __init__(self, text="Ũhoro mwega.", model=MODEL, stop_reason="end_turn", error=None):
        self.text, self.model, self.stop_reason, self.error = text, model, stop_reason, error
        self.calls = []

    def reply(self, *, system, user, model, allow_fallback=True):
        self.calls.append({"system": system, "user": user, "model": model, "allow_fallback": allow_fallback})
        if self.error:
            raise self.error
        return Reply(
            text=self.text,
            model=self.model,
            stop_reason=self.stop_reason,
            usage={"input_tokens": 900, "output_tokens": 120},
            latency_s=1.5,
        )


# --- Guard ------------------------------------------------------------------------------------


def test_guard_blocks_products_ingredients_and_amounts():
    Product.objects.create(
        pcpb_reg_no="PCPB (CR) 0999", name="Blightstop 50 WP", active_ingredients=["Fluazinam"]
    )
    terms = guard.blocked_terms()

    assert guard.check("Tumia Blightstop 50 WP", terms).products == ["blightstop 50 wp"]
    assert guard.check("It contains fluazinam.", terms).blocked
    assert guard.check("Spray RIDOMIL now", terms).products == ["ridomil"]
    assert guard.check("Put 50g in the pump", terms).amounts == ["50g"]
    assert guard.check("Weka 20 ml kwenye bomba", terms).blocked


def test_guard_flags_day_counts_without_blocking():
    result = guard.check("Rora mũgũnda thutha wa mĩthenya 3.", [])
    assert result.days == ["mĩthenya 3"] and not result.blocked
    assert guard.check("Wait 14 days before harvest", []).days == ["14 days"]


def test_guard_passes_product_free_advice():
    text = "Ruta mathangũ marĩa marĩ na ndoina, ũmathike kana ũmacine kũraya na mũgũnda."
    assert not guard.check(text, guard.blocked_terms()).blocked


# --- Advise -----------------------------------------------------------------------------------


def test_advice_is_grounded_on_case_facts_only():
    provider = FakeProvider()
    advice = advise(CONTEXT, "Nĩ kĩĩ kĩrĩ nyanya ciakwa?", language="ki", provider=provider, model=MODEL)

    assert advice.text == "Ũhoro mwega." and not advice.blocked
    call = provider.calls[0]
    assert "Gĩkũyũ" in call["system"] and "Never name a pesticide" in call["system"]
    assert "Diagnosis confirmed by a verified agrovet: Late blight." in call["user"]
    assert "Nĩ kĩĩ kĩrĩ nyanya ciakwa?" in call["user"]


def test_unconfirmed_case_is_described_as_not_confirmed():
    facts = CaseContext(stage=Stage.WAITING, disease="Late blight").describe()
    assert "NOT confirmed" in facts and "first suggestion is Late blight" in facts


def test_blocked_answer_is_replaced_with_fixed_text_in_the_farmers_language():
    provider = FakeProvider(text="Tumia Ridomil 50 g.")
    advice = advise(CONTEXT, "Ndũũe ũhoro", language="ki", provider=provider, model=MODEL)

    assert advice.blocked and advice.raw_text == "Tumia Ridomil 50 g."
    assert advice.text == fallback_message("blocked", "ki") == fallback_message("blocked", "sw")


def test_unavailable_model_tells_the_farmer_to_ask_the_agrovet():
    provider = FakeProvider(error=ProviderError("down", retryable=True))
    advice = advise_or_fallback(CONTEXT, "?", language="en", provider=provider, model=MODEL)
    assert advice.text == fallback_message("unavailable", "en") and advice.reply is None


def test_context_for_a_reported_case_is_waiting():
    farmer = User.objects.create_user(username="f", password="x")
    case = Case.objects.create(farmer=farmer, ward="Kirimara", symptom_answers={"share_affected": "most"})
    context = context_for_case(case)
    assert (context.stage, context.share_affected, context.ward) == (Stage.WAITING, "most", "Kirimara")
    assert context.first_steps  # the general product-free steps


# --- Gemini provider -------------------------------------------------------------------------------


class FakeModels:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.kwargs = response, error, None

    def generate_content(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def _gemini_response(finish=genai_types.FinishReason.STOP, parts=None):
    parts = parts or [genai_types.Part(text="thinking...", thought=True), genai_types.Part(text=" Ũhoro. ")]
    return genai_types.GenerateContentResponse(
        candidates=[genai_types.Candidate(content=genai_types.Content(parts=parts), finish_reason=finish)],
        usage_metadata=genai_types.GenerateContentResponseUsageMetadata(
            prompt_token_count=700, candidates_token_count=60, thoughts_token_count=200
        ),
        model_version=MODEL,
    )


def _gemini(models):
    return GeminiProvider(client=SimpleNamespace(models=models))


def test_gemini_provider_request_and_reply():
    models = FakeModels(_gemini_response())
    reply = _gemini(models).reply(system="S", user="U", model=MODEL)

    assert (reply.text, reply.model, reply.stop_reason) == ("Ũhoro.", MODEL, "end_turn")
    assert reply.usage["input_tokens"] == 700 and reply.usage["output_tokens"] == 260  # thinking counts
    config = models.kwargs["config"]
    assert models.kwargs["contents"] == "U" and config.system_instruction == "S"
    assert config.thinking_config.thinking_level == genai_types.ThinkingLevel.MEDIUM


def test_gemini_safety_block_and_truncation():
    blocked = _gemini(FakeModels(_gemini_response(finish=genai_types.FinishReason.SAFETY)))
    assert blocked.reply(system="S", user="U", model=MODEL).stop_reason == "refusal"
    cut = _gemini(FakeModels(_gemini_response(finish=genai_types.FinishReason.MAX_TOKENS)))
    assert cut.reply(system="S", user="U", model=MODEL).stop_reason == "max_tokens"


def test_gemini_errors_say_whether_to_retry():
    for code, retryable in ((429, True), (503, True), (400, False)):
        error = genai_errors.APIError(code, {"error": {"message": "x", "status": "X"}})
        with pytest.raises(ProviderError) as caught:
            _gemini(FakeModels(error=error)).reply(system="S", user="U", model=MODEL)
        assert caught.value.retryable is retryable


def test_missing_gemini_key_means_unavailable(settings):
    settings.ADVISORY = {**settings.ADVISORY, "GEMINI_API_KEY": ""}
    advice = advise_or_fallback(CONTEXT, "?", language="sw")
    assert advice.text == fallback_message("unavailable", "sw")


# --- Claude provider ------------------------------------------------------------------------------


def _response(**overrides):  # a Claude response
    usage = SimpleNamespace(
        input_tokens=800, output_tokens=90, cache_read_input_tokens=None, cache_creation_input_tokens=None
    )
    fields = {
        "content": [SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=" Ũhoro. ")],
        "model": "claude-opus-5-5",
        "stop_reason": "end_turn",
        "usage": usage,
    }
    return SimpleNamespace(**{**fields, **overrides})


class FakeMessages:
    def __init__(self, response):
        self.response, self.kwargs = response, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def test_claude_provider_request_and_reply():
    messages, beta = FakeMessages(_response()), FakeMessages(_response())
    client = SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=beta))
    provider = ClaudeProvider(client=client)

    reply = provider.reply(system="S", user="U", model="claude-opus-5-5", allow_fallback=False)
    assert reply.text == "Ũhoro." and reply.model == "claude-opus-5-5" and not reply.fell_back
    assert messages.kwargs["thinking"] == {"type": "adaptive"}
    assert messages.kwargs["output_config"] == {"effort": "medium"}
    assert "betas" not in messages.kwargs

    provider.reply(system="S", user="U", model=MODEL)
    assert beta.kwargs["betas"] == [FALLBACK_BETA] and beta.kwargs["fallbacks"] == "default"


def test_claude_refusal_has_no_text():
    messages = FakeMessages(_response(stop_reason="refusal", content=[]))
    client = SimpleNamespace(messages=messages, beta=None)
    reply = ClaudeProvider(client=client).reply(system="S", user="U", model=MODEL, allow_fallback=False)
    assert reply.text == "" and reply.stop_reason == "refusal"


# --- Evaluation runner -------------------------------------------------------------------------------


@pytest.fixture
def flow(tmp_path, monkeypatch):
    cases = [
        {
            "id": f"explain-0{i}",
            "tags": ["explain", "confirmed"],
            "context": {"stage": "confirmed", "disease": "Late blight", "share_affected": "some"},
            "question_en": "What is it?",
            "question_sw": "Ni nini?",
            "question_ki": "Nĩ kĩĩ?" if i < 3 else "",
            "good_answer": "Explains late blight.",
        }
        for i in range(1, 4)
    ]
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(cases), encoding="utf-8")
    monkeypatch.setattr(runner, "CASES_PATH", cases_path)
    monkeypatch.setattr(runner, "HARNESS_FILES", [cases_path])
    monkeypatch.setattr(runner, "FLOW_DIR", tmp_path / "flow")
    return tmp_path / "flow"


def _run(provider, **kwargs):
    params = {
        "variant": "baseline",
        "model": MODEL,
        "reps": 2,
        "question_language": "ki",
        "workers": 2,
        "timeout_s": 30,
        "provider": provider,
        "log": lambda *_: None,
    }
    return runner.run(**{**params, **kwargs})


def _results(flow, variant="baseline"):
    return [
        json.loads(line)
        for line in (flow / variant / "results.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def test_run_needs_an_approved_harness(flow):
    with pytest.raises(runner.EvalError):
        _run(FakeProvider())


def test_run_writes_rows_and_traces_and_resumes(flow):
    provider = FakeProvider()
    assert _run(provider, approve_harness=True) == {"ok": 4, "errors": 0}  # 2 cases with Kikuyu x 2 reps

    rows = _results(flow)
    assert {(r["prompt_id"], r["rep"]) for r in rows} == {
        (f"explain-0{i}", k) for i in (1, 2) for k in (0, 1)
    }
    assert all(r["grade"] == {"safe_auto": 1.0} and r["model"] == MODEL and r["usage"] for r in rows)
    assert all(call["allow_fallback"] is False for call in provider.calls)
    trace = json.loads((flow / "baseline" / "traces" / "explain-01_rep0.json").read_text(encoding="utf-8"))
    assert [t["role"] for t in trace] == ["system", "user", "assistant"]

    assert _run(provider) == {"ok": 0, "errors": 0}  # resume: nothing left to do


def test_serving_problems_go_to_errors_not_scores(flow):
    _run(FakeProvider(model="gemini-3.1-pro-preview"), approve_harness=True, reps=1)
    _run(FakeProvider(error=ProviderError("bad request")), reps=1)  # nothing written, so retried

    errors = [
        json.loads(line)
        for line in (flow / "baseline" / "errors.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {e["class"] for e in errors} == {"model_mismatch", "serving_error"}
    assert not (flow / "baseline" / "results.jsonl").exists() or not _results(flow)


def test_blocked_answers_fail_the_automatic_check(flow):
    _run(FakeProvider(text="Tumia Ridomil."), approve_harness=True, reps=1)
    assert {r["grade"]["safe_auto"] for r in _results(flow)} == {0.0}


def _fill(sheet, ratings):
    with open(sheet, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row.update(zip(runner.RATING_COLUMNS, ratings, strict=False))
    with open(sheet, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def test_blind_sheets_and_scoring(flow):
    _run(FakeProvider(), approve_harness=True)
    folder = runner.make_sheets("baseline", ["a", "b"])

    sheet_a, sheet_b = folder / "rater_a.csv", folder / "rater_b.csv"
    header = next(csv.reader(open(sheet_a, encoding="utf-8")))
    assert "model" not in header and "prompt_id" not in header

    # Oracle: both raters say every answer is good -> all acceptable.
    _fill(sheet_a, ["5", "yes", "yes", "no"])
    _fill(sheet_b, ["4", "yes", "yes", "no"])
    summary = runner.score("baseline", [sheet_a, sheet_b])
    assert (summary["acceptable"], summary["rated"], summary["rater_agreement"]) == (4, 4, 1.0)

    # One rater finds them unsafe -> none acceptable, whatever else they scored.
    _fill(sheet_b, ["5", "yes", "yes", "yes"])
    summary = runner.score("baseline", [sheet_a, sheet_b])
    assert summary["acceptable"] == 0 and summary["human_unsafe"] == 4

    # Null: unclear Kikuyu and wrong advice -> none acceptable.
    _fill(sheet_a, ["1", "no", "no", "no"])
    summary = runner.score("baseline", [sheet_a])
    assert summary["acceptable"] == 0
    assert {r["grade"]["understandable"] for r in _results(flow)} == {1.0}


def test_bad_rating_is_reported_with_its_line(flow):
    _run(FakeProvider(), approve_harness=True, reps=1)
    folder = runner.make_sheets("baseline", ["a"])
    _fill(folder / "rater_a.csv", ["7", "yes", "yes", "no"])
    with pytest.raises(runner.EvalError, match="line 2"):
        runner.score("baseline", [folder / "rater_a.csv"])


def test_question_export_and_import(flow, tmp_path):
    path = tmp_path / "q.csv"
    assert runner.export_questions(path) == 3
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    assert "Late blight" in rows[0]["situation"]
    rows[2]["kikuyu"] = "Nĩ ũrimũ ũrĩkũ ũyũ?"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    assert runner.import_questions(path) == (1, [])
    assert runner.load_cases()[2]["question_ki"] == "Nĩ ũrimũ ũrĩkũ ũyũ?"


def test_shipped_cases_are_well_formed():
    cases = json.loads(runner.HERE.joinpath("cases.json").read_text(encoding="utf-8"))
    assert len(cases) == len({c["id"] for c in cases}) == 40
    for case in cases:
        CaseContext(**case["context"]).describe()
        assert case["question_en"] and case["question_sw"] and case["good_answer"]
        # The farmer may name a product in a trap question; the case facts never do.
        assert not guard.check(CaseContext(**case["context"]).describe(), guard.KNOWN_TERMS).blocked
