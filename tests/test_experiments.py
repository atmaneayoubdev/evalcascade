"""Experiment summaries, comparisons and JSON export."""

from __future__ import annotations

from pathlib import Path

import pytest

from evalcascade import EvalSuite
from evalcascade.config import Settings
from evalcascade.core.results import EvaluationResult, Judgment, MetricResult
from evalcascade.datasets import load_sample
from evalcascade.errors import NotFoundError
from evalcascade.evaluators import SimulatedEvaluator
from evalcascade.experiments import Experiment, compare_experiments, summarize
from evalcascade.experiments.summary import histogram, latency_stats, percentile
from evalcascade.metrics import build_metrics
from tests.conftest import ScriptedEvaluator


def mr(
    metric: str,
    score: float | None,
    route: str,
    *,
    status: str = "ok",
    escalated: bool = False,
    threshold: float = 0.5,
    judgments: list[Judgment] | None = None,
    cost: float = 0.0,
    latency: float = 10.0,
) -> MetricResult:
    return MetricResult(
        metric=metric,
        display_name=metric.title(),
        category="general",
        status=status,  # type: ignore[arg-type]
        score=score,
        passed=None if score is None else score >= threshold,
        threshold=threshold,
        route=route,
        escalated=escalated,
        judgments=judgments or [],
        cost_usd=cost,
        latency_ms=latency,  # type: ignore[arg-type]
    )


def j(score: float | None, evaluator: str = "jev") -> Judgment:
    return Judgment(evaluator=evaluator, evaluator_kind="system_one", score=score)


def test_percentiles_and_histogram() -> None:
    assert percentile([], 50) is None
    assert percentile([5.0], 95) == 5.0
    assert percentile([1, 2, 3, 4], 50) == pytest.approx(2.5)
    assert percentile(list(range(1, 101)), 95) == pytest.approx(95.05)
    stats = latency_stats([10, 20, 30])
    assert (stats.mean, stats.p50, stats.max) == (20, 20, 30)
    assert histogram([0.0, 0.05, 0.5, 0.99, 1.0]) == [2, 0, 0, 0, 0, 1, 0, 0, 0, 2]


def test_routing_statistics_and_agreement() -> None:
    cases = [
        EvaluationResult(
            case_id="1",
            overall_score=0.8,
            passed=True,
            latency_ms=100,
            cost_usd=0.01,
            metrics=[
                mr("a", 1.0, "deterministic"),
                mr("b", 0.9, "jev", cost=0.001),
                mr(
                    "c",
                    0.2,
                    "jev_to_llm",
                    escalated=True,
                    judgments=[j(0.3), j(0.2, "llm")],
                    cost=0.01,
                ),
            ],
        ),
        EvaluationResult(
            case_id="2",
            overall_score=0.4,
            passed=False,
            latency_ms=300,
            cost_usd=0.02,
            metrics=[
                mr("a", None, "none", status="skipped"),
                mr("b", 0.7, "jev_to_llm", escalated=True, judgments=[j(0.2), j(0.7, "llm")]),
                mr("c", 0.6, "llm"),
                mr("d", None, "jev", status="error"),
            ],
        ),
    ]
    s = summarize(cases)
    r = s.routing
    assert (
        r.total,
        r.deterministic,
        r.jev_attempts,
        r.jev_accepted,
        r.escalated,
        r.llm_direct,
        r.skipped,
        r.errors,
    ) == (6, 1, 4, 1, 2, 1, 1, 1)
    assert r.jev_acceptance_rate == pytest.approx(0.25) and r.escalation_rate == pytest.approx(0.5)
    assert r.deterministic_rate == pytest.approx(1 / 6) and r.llm_rate == pytest.approx(0.5)
    assert s.agreement.compared == 2 and s.agreement.agreement_rate == pytest.approx(0.5)
    assert s.overall_score == pytest.approx(0.6) and s.pass_rate == pytest.approx(0.5)
    assert s.cost_usd == pytest.approx(0.03) and s.cost_per_case_usd == pytest.approx(0.015)
    assert s.latency_ms.p50 == pytest.approx(200) and s.num_evaluations == 6 and s.errors == 1
    b = s.metrics["b"]
    assert (
        b.mean == pytest.approx(0.8)
        and b.escalation_rate == pytest.approx(0.5)
        and b.routes.jev == 1
        and b.routes.jev_to_llm == 1
    )
    assert s.metrics["a"].skipped == 1 and s.metrics["a"].routes.none == 1
    assert s.metrics["d"].errors == 1 and s.metrics["d"].mean is None


def test_cost_completeness_flag() -> None:
    unknown = Judgment(
        evaluator="llm", evaluator_kind="llm_judge", score=1.0, cost_source="unknown"
    )
    s = summarize([EvaluationResult(metrics=[mr("a", 1.0, "llm", judgments=[unknown])])])
    assert s.cost_complete is False
    assert summarize([]).overall_score is None


def run(
    settings: Settings, confidence: float, level: float | None = None, name: str = "exp"
) -> Experiment:
    suite = EvalSuite(
        build_metrics(["answer_relevance", "groundedness"]),
        evaluators={
            "jev": ScriptedEvaluator("jev", confidence=confidence, level=level),
            "llm": ScriptedEvaluator("llm", route_label="llm", level=level),
        },
        settings=settings,
    )
    return suite.run_sync(load_sample("rag_qa"), name=name)


def test_compare_experiments(settings: Settings) -> None:
    base = run(settings, confidence=0.95, name="base")
    cand = run(settings, confidence=0.5, level=2, name="cand")
    cmp = compare_experiments(base, cand)
    assert cmp.dataset_match
    assert cmp.overall_score.baseline == pytest.approx(1.0)
    assert cmp.overall_score.delta == pytest.approx(-1 / 3)
    assert cmp.overall_score.relative == pytest.approx(-1 / 3)
    assert cmp.jev_acceptance_rate.delta == pytest.approx(-1.0)
    assert cmp.escalation_rate.delta == pytest.approx(1.0)
    assert set(cmp.metrics) == {"answer_relevance", "groundedness"}
    assert cmp.cases.matched == 12 and cmp.cases.regressed == 12 and cmp.cases.improved == 0
    assert len(cmp.cases.top_regressions) == 10
    assert cmp.cost_usd.delta is not None and cmp.cost_usd.delta > 0


def test_compare_different_datasets(settings: Settings) -> None:
    a = run(settings, confidence=0.95)
    evaluators = {
        "jev": ScriptedEvaluator("jev"),
        "llm": ScriptedEvaluator("llm", route_label="llm"),
    }
    other = EvalSuite(build_metrics(["safety"]), evaluators=evaluators, settings=settings).run_sync(
        load_sample("support_bot")
    )
    cmp = compare_experiments(a, other)
    assert not cmp.dataset_match
    assert cmp.cases.only_in_baseline == 12 and cmp.cases.only_in_candidate == 10
    assert cmp.metrics["safety"].baseline is None and cmp.metrics["safety"].delta is None


def test_experiment_json_roundtrip(tmp_path: Path, settings: Settings) -> None:
    exp = EvalSuite(
        build_metrics(["rag"]),
        evaluators={"jev": SimulatedEvaluator("jev"), "llm": SimulatedEvaluator("llm", role="llm")},
        settings=settings,
    ).run_sync(load_sample("rag_qa"), name="rt", tags=["x"], notes="hello", is_demo=True)
    path = tmp_path / "exports" / "rt.json"
    exp.to_json(path)
    back = Experiment.from_json(path)
    assert back.id == exp.id and back.is_demo and back.tags == ["x"] and back.notes == "hello"
    assert back.summary == exp.summary and len(back.results) == 12
    assert back.case("rag-001").case.input == exp.case("rag-001").case.input
    with pytest.raises(NotFoundError):
        back.case("missing")
    with pytest.raises(NotFoundError):
        Experiment.from_json(tmp_path / "nope.json")
    (tmp_path / "bad.json").write_text("{}", encoding="utf-8")
    with pytest.raises(NotFoundError, match="not a valid"):
        Experiment.from_json(tmp_path / "bad.json")
