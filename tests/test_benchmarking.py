"""Benchmark harness: classification, calibration, sweep and an offline end-to-end run."""

from __future__ import annotations

import pytest

from evalcascade.benchmarking import (
    ItemResult,
    calibration,
    classification,
    run_benchmark,
    score_mode,
    sweep,
    to_markdown,
)
from evalcascade.config import Settings
from evalcascade.datasets import Dataset
from evalcascade.errors import DatasetError
from tests.conftest import ScriptedEvaluator


def test_classification_counts() -> None:
    c = classification([True, True, False, False, True], [True, False, True, False, True])
    assert (c.tp, c.fn, c.fp, c.tn) == (2, 1, 1, 1)
    assert c.accuracy == pytest.approx(0.6)
    assert c.precision == pytest.approx(2 / 3) and c.recall == pytest.approx(2 / 3)
    assert c.f1 == pytest.approx(2 / 3) and c.balanced_accuracy == pytest.approx((2 / 3 + 0.5) / 2)
    empty = classification([], [])
    assert empty.accuracy is None and empty.f1 is None
    assert classification([False], [False]).precision is None
    with pytest.raises(ValueError, match="same length"):
        classification([True], [])


def test_brier_ece_and_reliability() -> None:
    perfect = calibration([True, False], [1.0, 0.0])
    assert perfect.brier == 0.0 and perfect.ece == 0.0
    cal = calibration([True, False, True, True], [0.9, 0.9, 0.2, 0.25])
    assert cal.brier == pytest.approx((0.01 + 0.81 + 0.64 + 0.5625) / 4)
    # bin [0.9,1.0): mean 0.9 vs freq 0.5 -> 0.4 * 2/4 ; bin [0.2,0.3): mean 0.225 vs 1.0 -> 0.775 * 2/4
    assert cal.ece == pytest.approx(0.4 * 0.5 + 0.775 * 0.5)
    populated = [b for b in cal.bins if b.count]
    assert [(b.lower, b.count) for b in populated] == [(0.2, 2), (0.9, 2)]
    assert calibration([], []).brier is None
    assert calibration([True], [1.5]).brier == 0.0  # clamped


def item(
    i: str,
    label: bool,
    pred: bool | None,
    conf: float | None,
    *,
    latency: float = 10,
    cost: float = 0.001,
    route: str = "jev",
    escalated: bool = False,
) -> ItemResult:
    return ItemResult(
        id=i,
        label=label,
        predicted=pred,
        confidence=conf,
        latency_ms=latency,
        cost_usd=cost,
        route=route,
        escalated=escalated,
        pass_probability=0.9 if pred else 0.1,
    )


def test_sweep_replays_recorded_judgments() -> None:
    jev = [item("1", True, True, 0.95), item("2", False, True, 0.6), item("3", True, None, None)]
    llm = [
        item(i, lab, lab, 0.9, latency=100, cost=0.01, route="llm")
        for i, lab in (("1", True), ("2", False), ("3", True))
    ]
    points = {p.escalate_below: p for p in sweep(jev, llm, thresholds=(0.5, 0.9))}
    low, high = points[0.5], points[0.9]
    assert low.escalation_rate == pytest.approx(1 / 3) and low.accuracy == pytest.approx(2 / 3)
    assert high.escalation_rate == pytest.approx(2 / 3) and high.accuracy == 1.0
    assert high.cost_usd == pytest.approx(0.003 + 0.02)
    assert high.latency_p95_ms is not None and high.latency_p95_ms > 100


def test_score_mode_rates() -> None:
    items = [
        item("1", True, True, 0.9),
        item("2", False, False, 0.4, route="jev_to_llm", escalated=True),
        item("3", True, None, None),
    ]
    report = score_mode("cascade", items)
    assert report.n == 3 and report.errors == 1
    assert report.escalation_rate == pytest.approx(
        0.5
    ) and report.jev_acceptance_rate == pytest.approx(0.5)
    assert report.classification.accuracy == 1.0 and report.cost_usd == pytest.approx(0.003)


def labeled() -> Dataset:
    rows = [
        {
            "id": f"c{i}",
            "input": "q",
            "output": "a",
            "context": ["ctx"],
            "expected": {"label": i % 2 == 0},
        }
        for i in range(6)
    ]
    return Dataset.from_records(rows, name="toy")


async def test_run_benchmark_offline(settings: Settings) -> None:
    evaluators = {
        "jev": ScriptedEvaluator("jev", level=3, confidence=0.7, cost=0.00002, latency_ms=50),
        "llm": ScriptedEvaluator(
            "llm",
            route_label="llm",
            kind="llm_judge",
            level=0,
            confidence=0.9,
            cost=0.001,
            latency_ms=900,
        ),
    }
    report = await run_benchmark(
        labeled(),
        metric="groundedness",
        settings=settings,
        evaluators=evaluators,
        escalate_below=0.8,
        concurrency=2,
    )
    assert set(report.modes) == {"jev", "llm", "cascade"}
    jev, llm, cascade = report.modes["jev"], report.modes["llm"], report.modes["cascade"]
    assert jev.classification.recall == 1.0 and jev.classification.precision == pytest.approx(0.5)
    assert llm.classification.recall == 0.0
    assert cascade.escalation_rate == 1.0  # every Jev confidence (0.7) < 0.8
    assert cascade.cost_usd == pytest.approx(6 * (0.00002 + 0.001))
    assert report.sweep and report.pass_threshold == 0.6
    assert report.evaluators["jev"]["name"] == "jev"
    md = to_markdown(report)
    assert "| Jev only |" in md and "Escalation-threshold sweep" in md and "Reliability" in md


async def test_run_benchmark_requires_labels(settings: Settings) -> None:
    ds = Dataset.from_records([{"id": "x", "output": "a", "context": ["c"]}], name="nolabel")
    with pytest.raises(DatasetError, match=r"expected\.label"):
        await run_benchmark(ds, metric="groundedness", settings=settings)
