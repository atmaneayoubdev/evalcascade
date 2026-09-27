"""Every branch of the System One -> System Two cascade."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from evalcascade import EvalSuite, EvaluationPolicy, MetricPolicy
from evalcascade.config import Settings
from evalcascade.core.evaluator import EvalItem
from evalcascade.core.metric import Metric
from evalcascade.core.results import Judgment
from evalcascade.core.types import EvaluationRequest
from evalcascade.metrics import AnswerRelevance, CitationPresence, Correctness, Groundedness
from tests.conftest import ScriptedEvaluator


def make_suite(
    metrics: Sequence[Metric],
    settings: Settings,
    *,
    jev: ScriptedEvaluator | None = None,
    llm: ScriptedEvaluator | None = None,
    policy: EvaluationPolicy | None = None,
) -> tuple[EvalSuite, ScriptedEvaluator, ScriptedEvaluator]:
    jev = jev or ScriptedEvaluator("jev", confidence=0.95)
    llm = llm or ScriptedEvaluator(
        "llm",
        route_label="llm",
        kind="llm_judge",
        level=1,
        confidence=0.9,
        cost=0.01,
        latency_ms=100,
    )
    suite = EvalSuite(
        metrics,
        evaluators={"jev": jev, "llm": llm},
        settings=settings,
        policy=policy or EvaluationPolicy(),
    )
    return suite, jev, llm


async def test_deterministic_result_is_final(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    suite, jev, llm = make_suite([Correctness()], settings)
    result = await suite.evaluate(request=qa_request.model_copy(update={"output": "Paris"}))
    m = result["correctness"]
    assert m.route == "deterministic"
    assert m.score == 1.0 and m.confidence == 1.0 and m.cost_usd == 0.0
    assert m.escalate_below is None
    assert not jev.calls and not llm.calls


async def test_jev_judgment_accepted_when_confident(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    suite, jev, llm = make_suite([AnswerRelevance()], settings)
    m = (await suite.evaluate(request=qa_request))["answer_relevance"]
    assert m.status == "ok" and m.route == "jev"
    assert not m.escalated and m.escalation_reason is None
    assert m.escalate_below == pytest.approx(0.82)
    assert [j.evaluator for j in m.judgments] == ["jev"]
    assert m.score == pytest.approx(1.0) and m.passed is True
    assert len(jev.calls) == 1 and not llm.calls


async def test_confidence_equal_to_threshold_is_accepted(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    suite, _, llm = make_suite(
        [AnswerRelevance()], settings, jev=ScriptedEvaluator("jev", confidence=0.82)
    )
    m = (await suite.evaluate(request=qa_request))["answer_relevance"]
    assert m.route == "jev" and not llm.calls


async def test_low_confidence_escalates_and_keeps_both_judgments(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    suite, jev, llm = make_suite(
        [AnswerRelevance()],
        settings,
        jev=ScriptedEvaluator("jev", confidence=0.5, latency_ms=20, cost=0.002),
    )
    result = await suite.evaluate(request=qa_request)
    m = result["answer_relevance"]
    assert m.route == "jev_to_llm"
    assert m.escalated and m.escalation_reason == "low_confidence"
    assert [j.evaluator for j in m.judgments] == ["jev", "llm"]
    assert m.final_evaluator == "llm"
    assert m.judgments[0].confidence == pytest.approx(0.5)
    # Final score comes from the LLM judge (level 1 of 0..3).
    assert m.score == pytest.approx(1 / 3)
    assert m.passed is False
    assert m.latency_ms == pytest.approx(120.0)
    assert m.cost_usd == pytest.approx(0.012)
    assert result.escalations == 1
    assert result.cost_usd == pytest.approx(0.012)
    assert jev.calls[0] is llm.calls[0]  # the same rubric is escalated unchanged


async def test_primary_error_escalates(settings: Settings, qa_request: EvaluationRequest) -> None:
    suite, _, llm = make_suite(
        [AnswerRelevance()], settings, jev=ScriptedEvaluator("jev", error="upstream exploded")
    )
    m = (await suite.evaluate(request=qa_request))["answer_relevance"]
    assert m.status == "ok" and m.route == "jev_to_llm"
    assert m.escalation_reason == "primary_error"
    assert m.judgments[0].error and "upstream exploded" in m.judgments[0].error
    assert len(llm.calls) == 1


async def test_primary_error_without_escalate_on_error_is_an_error(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    policy = EvaluationPolicy(escalate_on_error=False)
    suite, _, llm = make_suite(
        [AnswerRelevance()], settings, jev=ScriptedEvaluator("jev", error="boom"), policy=policy
    )
    m = (await suite.evaluate(request=qa_request))["answer_relevance"]
    assert m.status == "error" and "boom" in (m.message or "")
    assert m.score is None and m.passed is None
    assert not llm.calls


async def test_fallback_failure_keeps_primary_judgment(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    suite, _, _ = make_suite(
        [AnswerRelevance()],
        settings,
        jev=ScriptedEvaluator("jev", confidence=0.4),
        llm=ScriptedEvaluator("llm", route_label="llm", error="judge down"),
    )
    m = (await suite.evaluate(request=qa_request))["answer_relevance"]
    assert m.status == "ok" and m.route == "jev"
    assert m.escalated and m.final_evaluator == "jev"
    assert "judge down" in (m.message or "")
    assert len(m.judgments) == 2


async def test_both_evaluators_failing_is_an_error(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    suite, _, _ = make_suite(
        [AnswerRelevance()],
        settings,
        jev=ScriptedEvaluator("jev", error="a"),
        llm=ScriptedEvaluator("llm", route_label="llm", error="b"),
    )
    m = (await suite.evaluate(request=qa_request))["answer_relevance"]
    assert m.status == "error" and "b" in (m.message or "")


async def test_missing_confidence_escalates(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    suite, _, llm = make_suite(
        [AnswerRelevance()], settings, jev=ScriptedEvaluator("jev", confidence=None)
    )
    m = (await suite.evaluate(request=qa_request))["answer_relevance"]
    assert m.escalation_reason == "low_confidence" and llm.calls


async def test_requires_reasoning_routes_straight_to_fallback(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    suite, jev, llm = make_suite([Correctness()], settings)
    request = qa_request.model_copy(update={"expected": None})
    m = (await suite.evaluate(request=request))["correctness"]
    assert m.route == "llm" and m.final_evaluator == "llm"
    assert m.escalation_reason == "requires_reasoning" and not m.escalated
    assert m.escalate_below is None
    assert not jev.calls and len(llm.calls) == 1


async def test_requires_reasoning_without_fallback_uses_primary(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    suite, jev, _ = make_suite([Correctness()], settings, policy=EvaluationPolicy.jev_only())
    m = (await suite.evaluate(request=qa_request.model_copy(update={"expected": None})))[
        "correctness"
    ]
    assert m.route == "jev" and len(jev.calls) == 1


async def test_per_metric_instance_threshold(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    suite, _, _ = make_suite(
        [AnswerRelevance(escalate_below=0.99), Groundedness()],
        settings,
        jev=ScriptedEvaluator("jev", confidence=0.95),
    )
    result = await suite.evaluate(request=qa_request)
    assert result["answer_relevance"].route == "jev_to_llm"
    assert result["answer_relevance"].escalate_below == pytest.approx(0.99)
    assert result["groundedness"].route == "jev"


async def test_policy_override_beats_instance_threshold(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    policy = EvaluationPolicy(overrides={"answer_relevance": MetricPolicy(escalate_below=0.5)})
    suite, _, _ = make_suite(
        [AnswerRelevance(escalate_below=0.99)],
        settings,
        jev=ScriptedEvaluator("jev", confidence=0.7),
        policy=policy,
    )
    m = (await suite.evaluate(request=qa_request))["answer_relevance"]
    assert m.route == "jev" and m.escalate_below == pytest.approx(0.5)


async def test_global_threshold(settings: Settings, qa_request: EvaluationRequest) -> None:
    suite, _, _ = make_suite(
        [AnswerRelevance()],
        settings,
        jev=ScriptedEvaluator("jev", confidence=0.9),
        policy=EvaluationPolicy(escalate_below=0.95),
    )
    assert (await suite.evaluate(request=qa_request))["answer_relevance"].route == "jev_to_llm"


async def test_override_can_disable_escalation(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    policy = EvaluationPolicy(overrides={"answer_relevance": MetricPolicy(escalate=False)})
    suite, _, llm = make_suite(
        [AnswerRelevance()], settings, jev=ScriptedEvaluator("jev", confidence=0.1), policy=policy
    )
    m = (await suite.evaluate(request=qa_request))["answer_relevance"]
    assert m.route == "jev" and not m.escalated and not llm.calls


async def test_override_can_route_metric_to_llm(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    policy = EvaluationPolicy(overrides={"answer_relevance": MetricPolicy(primary="llm")})
    suite, jev, _ = make_suite([AnswerRelevance()], settings, policy=policy)
    m = (await suite.evaluate(request=qa_request))["answer_relevance"]
    assert m.route == "llm" and not jev.calls and not m.escalated


async def test_missing_required_fields_are_skipped(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    suite, jev, _ = make_suite([Groundedness()], settings)
    m = (await suite.evaluate(request=qa_request.model_copy(update={"context": []})))[
        "groundedness"
    ]
    assert m.status == "skipped" and "context" in (m.message or "")
    assert m.route == "none" and not jev.calls


async def test_deterministic_only_policy(settings: Settings, qa_request: EvaluationRequest) -> None:
    suite, jev, llm = make_suite(
        [AnswerRelevance(), CitationPresence()],
        settings,
        policy=EvaluationPolicy.deterministic_only(),
    )
    result = await suite.evaluate(request=qa_request)
    assert result["answer_relevance"].status == "skipped"
    assert "deterministic-only" in (result["answer_relevance"].message or "")
    assert result["citation_presence"].route == "deterministic"
    assert result["citation_presence"].score == 1.0
    assert result.overall_score == 1.0  # skipped metrics do not count
    assert not jev.calls and not llm.calls


async def test_deterministic_first_false_forces_semantic(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    suite, jev, _ = make_suite(
        [Correctness(), CitationPresence()],
        settings,
        policy=EvaluationPolicy(deterministic_first=False),
    )
    result = await suite.evaluate(request=qa_request.model_copy(update={"output": "Paris"}))
    assert result["correctness"].route == "jev" and len(jev.calls) == 1
    # Fully deterministic metrics have no rubric, so they are always evaluated deterministically.
    assert result["citation_presence"].route == "deterministic"


async def test_llm_only_policy(settings: Settings, qa_request: EvaluationRequest) -> None:
    suite, jev, llm = make_suite([AnswerRelevance()], settings, policy=EvaluationPolicy.llm_only())
    m = (await suite.evaluate(request=qa_request))["answer_relevance"]
    assert m.route == "llm" and m.escalate_below is None and not jev.calls and llm.calls


async def test_overall_score_is_weighted_and_passed_requires_all(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    suite, _, _ = make_suite(
        [AnswerRelevance(weight=3.0), CitationPresence(weight=1.0)],
        settings,
        jev=ScriptedEvaluator("jev", level=0, confidence=0.99),
    )
    result = await suite.evaluate(request=qa_request)
    assert result["answer_relevance"].score == 0.0
    assert result["citation_presence"].score == 1.0
    assert result.overall_score == pytest.approx(0.25)
    assert result.passed is False


async def test_unknown_evaluator_is_reported_per_metric(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    suite = EvalSuite(
        [CitationPresence(), AnswerRelevance()],
        settings=settings,
        policy=EvaluationPolicy(primary="nope", fallback=None),
    )
    suite._preflight_done = True  # bypass fail-fast to exercise the runtime path
    result = await suite.evaluate(request=qa_request)
    assert result["answer_relevance"].status == "error"
    assert "unknown evaluator" in (result["answer_relevance"].message or "")
    assert result["citation_presence"].status == "ok"


async def test_misbehaving_custom_evaluator_is_contained(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    class Exploding(ScriptedEvaluator):
        async def evaluate_batch(self, items: Sequence[EvalItem]) -> list[Judgment]:
            raise RuntimeError("bug in custom evaluator")

    suite, _, llm = make_suite([AnswerRelevance()], settings, jev=Exploding("jev"))
    m = (await suite.evaluate(request=qa_request))["answer_relevance"]
    assert m.escalation_reason == "primary_error" and "bug in custom evaluator" in (
        m.judgments[0].error or ""
    )
    assert llm.calls


async def test_rubric_exception_becomes_metric_error(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    class Broken(AnswerRelevance):
        name = "broken"

        def rubric(self, request: EvaluationRequest):  # type: ignore[no-untyped-def]
            raise ValueError("bad rubric")

    suite, _, _ = make_suite([Broken(), CitationPresence()], settings)
    result = await suite.evaluate(request=qa_request)
    assert result["broken"].status == "error" and "bad rubric" in (result["broken"].message or "")
    assert result["citation_presence"].status == "ok"


async def test_all_primary_metrics_are_submitted_as_one_batch(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    batches: list[int] = []

    class Spy(ScriptedEvaluator):
        async def evaluate_batch(self, items: Sequence[EvalItem]) -> list[Judgment]:
            batches.append(len(items))
            return await super().evaluate_batch(items)

    suite, _, _ = make_suite(
        [AnswerRelevance(), Groundedness(), Correctness(match="none")], settings, jev=Spy("jev")
    )
    await suite.evaluate(request=qa_request)
    assert batches == [3]


async def test_escalations_are_batched_per_fallback(
    settings: Settings, qa_request: EvaluationRequest
) -> None:
    batches: list[int] = []

    class Spy(ScriptedEvaluator):
        async def evaluate_batch(self, items: Sequence[EvalItem]) -> list[Judgment]:
            batches.append(len(items))
            return await super().evaluate_batch(items)

    suite, _, _ = make_suite(
        [AnswerRelevance(), Groundedness()],
        settings,
        jev=ScriptedEvaluator("jev", confidence=0.3),
        llm=Spy("llm", route_label="llm"),
    )
    result = await suite.evaluate(request=qa_request)
    assert batches == [2] and result.escalations == 2
