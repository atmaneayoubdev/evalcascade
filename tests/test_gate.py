"""Regression gates."""

from __future__ import annotations

import pytest

from evalcascade.core.results import CaseResult, MetricResult
from evalcascade.datasets.dataset import Case
from evalcascade.experiments import Experiment, summarize
from evalcascade.experiments.experiment import DatasetRef
from evalcascade.regression import RegressionGate


def make(
    scores: dict[str, float],
    *,
    cost: float = 0.01,
    latency: float = 100.0,
    escalated: int = 0,
    dataset_hash: str = "h1",
    name: str = "e",
) -> Experiment:
    metrics = [
        MetricResult(
            metric=k,
            display_name=k,
            category="general",
            status="ok",
            score=v,
            passed=v >= 0.5,
            threshold=0.5,
            route="jev_to_llm" if i < escalated else "jev",
            escalated=i < escalated,
        )
        for i, (k, v) in enumerate(scores.items())
    ]
    overall = sum(scores.values()) / len(scores)
    results = [
        CaseResult(
            case_id="c1",
            case=Case(id="c1"),
            overall_score=overall,
            passed=True,
            metrics=metrics,
            cost_usd=cost,
            latency_ms=latency,
        )
    ]
    return Experiment(
        name=name,
        dataset=DatasetRef(name="d", hash=dataset_hash, size=1),
        results=results,
        summary=summarize(results),
    )


def test_passes_within_threshold() -> None:
    result = RegressionGate(max_quality_drop=0.03).evaluate(
        make({"a": 0.80, "b": 0.80}), make({"a": 0.78, "b": 0.80})
    )
    assert result.passed and not result.violations
    assert result.checks[0].name == "overall_score" and result.checks[0].actual == pytest.approx(
        0.01
    )


def test_fails_on_overall_drop_and_reports_markdown() -> None:
    result = RegressionGate(max_quality_drop=0.03).evaluate(
        make({"a": 0.9}, name="base"), make({"a": 0.8}, name="cand")
    )
    assert not result.passed and [v.name for v in result.violations] == ["overall_score"]
    md = result.to_markdown()
    assert "regression gate failed" in md and "`base`" in md and "`cand`" in md and "| a |" in md
    assert "FAIL" in result.to_text()


def test_improvement_always_passes() -> None:
    assert RegressionGate(max_quality_drop=0.0).evaluate(make({"a": 0.5}), make({"a": 0.9})).passed


def test_per_metric_thresholds_and_default_metric_drop() -> None:
    base, cand = make({"a": 0.9, "b": 0.9}), make({"a": 0.84, "b": 0.93})  # overall -0.015
    assert RegressionGate().evaluate(base, cand).passed
    strict = RegressionGate(metric_thresholds={"a": 0.05}).evaluate(base, cand)
    assert [v.name for v in strict.violations] == ["metric:a"]
    default = RegressionGate(max_metric_drop=0.02, metric_thresholds={"b": 0.0}).evaluate(
        base, cand
    )
    assert {c.name for c in default.checks} == {"overall_score", "metric:a", "metric:b"}
    assert [v.name for v in default.violations] == ["metric:a"]


def test_missing_and_new_metrics() -> None:
    gone = RegressionGate(metric_thresholds={"b": 0.1}).evaluate(
        make({"a": 0.9, "b": 0.9}), make({"a": 0.9})
    )
    assert not gone.passed and "missing" in gone.violations[0].message
    new = RegressionGate(metric_thresholds={"c": 0.1}).evaluate(
        make({"a": 0.9}), make({"a": 0.9, "c": 0.9})
    )
    assert new.passed


def test_cost_latency_escalation_floor_and_dataset_checks() -> None:
    base = make({"a": 0.9}, cost=0.010, latency=100)
    cand = make({"a": 0.9}, cost=0.013, latency=150, escalated=1, dataset_hash="h2")
    result = RegressionGate(
        max_cost_increase=0.2,
        max_latency_increase=0.6,
        min_score=0.95,
        max_escalation_rate=0.5,
        require_same_dataset=True,
    ).evaluate(base, cand)
    by_name = {c.name: c for c in result.checks}
    assert not by_name["cost"].passed and by_name["cost"].actual == pytest.approx(0.3)
    assert by_name["latency_p95"].passed
    assert not by_name["min_score"].passed
    assert not by_name["escalation_rate"].passed
    assert not by_name["dataset"].passed
    zero = RegressionGate(max_cost_increase=0.1).evaluate(
        make({"a": 1}, cost=0.0), make({"a": 1}, cost=0.001)
    )
    assert not zero.passed


def test_missing_scores_fail_the_gate() -> None:
    empty = Experiment(name="empty", summary=summarize([]))
    result = RegressionGate().evaluate(make({"a": 0.9}), empty)
    assert not result.passed and "unavailable" in result.violations[0].message
