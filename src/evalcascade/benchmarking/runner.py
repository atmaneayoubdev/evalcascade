"""Benchmark harness: Jev-only vs LLM-judge-only vs adaptive cascade on labeled data.

A benchmark dataset is a regular EvalCascade dataset whose cases carry a gold label in
``expected.label`` (``true`` = the output *should pass* the metric, e.g. it is grounded).
Each mode evaluates every case with the same metric; predictions (score >= the metric's pass
threshold) and pass probabilities are scored against the labels.

The threshold **sweep** is counterfactual: it replays the recorded Jev-only and LLM-only
judgments to show what a cascade *would* have produced at other ``escalate_below`` values
(exact when both backends are deterministic for identical inputs). It is reported separately
from the measured cascade run.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from evalcascade._version import __version__
from evalcascade.benchmarking.metrics import (
    Calibration,
    Classification,
    calibration,
    classification,
)
from evalcascade.config import Settings
from evalcascade.core.evaluator import Evaluator
from evalcascade.core.policy import EvaluationPolicy
from evalcascade.core.results import MetricResult
from evalcascade.core.suite import EvaluationSuite
from evalcascade.datasets.dataset import Dataset
from evalcascade.errors import DatasetError
from evalcascade.experiments.summary import percentile
from evalcascade.metrics import get_metric

Mode = Literal["jev", "llm", "cascade"]
MODES: tuple[Mode, ...] = ("jev", "llm", "cascade")
DEFAULT_SWEEP = (0.5, 0.6, 0.7, 0.75, 0.8, 0.82, 0.85, 0.9, 0.95, 0.99, 1.0)


class ItemResult(BaseModel):
    id: str
    label: bool
    predicted: bool | None = None
    score: float | None = None
    pass_probability: float | None = None
    confidence: float | None = None
    primary_confidence: float | None = None
    route: str = "none"
    escalated: bool = False
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    cost_complete: bool = True
    error: str | None = None


class ModeReport(BaseModel):
    mode: Mode
    n: int
    errors: int
    classification: Classification
    calibration: Calibration
    latency_ms: dict[str, float | None]
    cost_usd: float
    cost_per_item_usd: float | None
    cost_complete: bool
    escalation_rate: float | None
    jev_acceptance_rate: float | None
    items: list[ItemResult]


class SweepPoint(BaseModel):
    escalate_below: float
    accuracy: float | None
    f1: float | None
    escalation_rate: float
    cost_usd: float
    latency_p50_ms: float | None
    latency_p95_ms: float | None


class BenchmarkReport(BaseModel):
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: str = __version__
    dataset: dict[str, Any]
    metric: str
    metric_params: dict[str, Any] = Field(default_factory=dict)
    pass_threshold: float
    escalate_below: float
    concurrency: int
    evaluators: dict[str, dict[str, Any]]
    modes: dict[str, ModeReport]
    sweep: list[SweepPoint] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def labels_of(dataset: Dataset) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for case in dataset.cases:
        label = case.expected.label if case.expected else None
        if not isinstance(label, bool):
            raise DatasetError(f"case {case.id} has no boolean expected.label")
        out[case.id] = label
    return out


def _item(case_id: str, label: bool, m: MetricResult) -> ItemResult:
    used = next((j for j in reversed(m.judgments) if j.evaluator == m.final_evaluator), None)
    return ItemResult(
        id=case_id,
        label=label,
        predicted=m.passed if m.status == "ok" else None,
        score=m.score,
        pass_probability=used.pass_probability if used else None,
        confidence=m.confidence,
        primary_confidence=m.judgments[0].confidence if m.judgments else None,
        route=m.route,
        escalated=m.escalated,
        latency_ms=m.latency_ms,
        cost_usd=m.cost_usd,
        cost_complete=m.cost_complete,
        error=m.message if m.status != "ok" else None,
    )


def score_mode(mode: Mode, items: list[ItemResult]) -> ModeReport:
    ok = [i for i in items if i.predicted is not None]
    probs = [i for i in ok if i.pass_probability is not None]
    latencies = [i.latency_ms for i in ok]
    cost = sum(i.cost_usd for i in items)
    attempts = [i for i in ok if i.route in ("jev", "jev_to_llm")]
    escalated = [i for i in attempts if i.escalated]
    return ModeReport(
        mode=mode,
        n=len(items),
        errors=len(items) - len(ok),
        classification=classification([i.label for i in ok], [bool(i.predicted) for i in ok]),
        calibration=calibration(
            [i.label for i in probs], [float(i.pass_probability or 0.0) for i in probs]
        ),
        latency_ms={
            "mean": statistics.fmean(latencies) if latencies else None,
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
        },
        cost_usd=cost,
        cost_per_item_usd=cost / len(items) if items else None,
        cost_complete=all(i.cost_complete for i in items),
        escalation_rate=len(escalated) / len(attempts) if attempts else None,
        jev_acceptance_rate=(len(attempts) - len(escalated)) / len(attempts) if attempts else None,
        items=items,
    )


def sweep(
    jev: list[ItemResult], llm: list[ItemResult], thresholds: Sequence[float] = DEFAULT_SWEEP
) -> list[SweepPoint]:
    """Counterfactual cascade outcomes replayed from recorded Jev-only and LLM-only judgments."""
    llm_by_id = {i.id: i for i in llm}
    points = []
    for tau in thresholds:
        labels, preds, latencies = [], [], []
        cost = 0.0
        escalations = 0
        for j in jev:
            fallback = llm_by_id.get(j.id)
            escalate = j.predicted is None or j.confidence is None or j.confidence < tau
            final = fallback if escalate else j
            latency = j.latency_ms + (fallback.latency_ms if escalate and fallback else 0.0)
            cost += j.cost_usd + (fallback.cost_usd if escalate and fallback else 0.0)
            escalations += escalate
            if final is None or final.predicted is None:
                continue
            labels.append(j.label)
            preds.append(final.predicted)
            latencies.append(latency)
        c = classification(labels, preds)
        points.append(
            SweepPoint(
                escalate_below=tau,
                accuracy=c.accuracy,
                f1=c.f1,
                escalation_rate=escalations / len(jev) if jev else 0.0,
                cost_usd=cost,
                latency_p50_ms=percentile(latencies, 50),
                latency_p95_ms=percentile(latencies, 95),
            )
        )
    return points


def _policy(mode: Mode, escalate_below: float) -> EvaluationPolicy:
    if mode == "jev":
        return EvaluationPolicy.jev_only()
    if mode == "llm":
        return EvaluationPolicy.llm_only()
    # Benchmark the cascade decision itself: no reasoning shortcut to the judge.
    return EvaluationPolicy(escalate_below=escalate_below, route_reasoning_to_fallback=False)


async def run_benchmark(
    dataset: Dataset,
    *,
    metric: str,
    metric_params: dict[str, Any] | None = None,
    modes: Sequence[Mode] = MODES,
    escalate_below: float = 0.82,
    concurrency: int = 8,
    settings: Settings | None = None,
    evaluators: dict[str, Evaluator] | None = None,
    name: str | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> BenchmarkReport:
    """Evaluate ``dataset`` in each mode and score the results against ``expected.label``."""
    labels = labels_of(dataset)
    settings = settings or Settings.load()
    reports: dict[str, ModeReport] = {}
    described: dict[str, dict[str, Any]] = {}
    pass_threshold = get_metric(metric, **(metric_params or {})).pass_threshold
    for mode in modes:
        suite = EvaluationSuite(
            [get_metric(metric, **(metric_params or {}))],
            policy=_policy(mode, escalate_below),
            settings=settings,
            evaluators=evaluators,
            concurrency=concurrency,
        )
        done = 0

        def progress(_: object, *, _mode: Mode = mode) -> None:
            nonlocal done
            done += 1
            if on_progress:
                on_progress(_mode, done, len(dataset))

        try:
            results = await suite.evaluate_many(
                dataset.cases, concurrency=concurrency, on_result=progress
            )
            described.update(suite.config()["evaluators"])
        finally:
            await suite.aclose()
        items = [
            _item(case.id, labels[case.id], r.metrics[0])
            for case, r in zip(dataset.cases, results, strict=True)
        ]
        reports[mode] = score_mode(mode, items)

    points = (
        sweep(reports["jev"].items, reports["llm"].items) if {"jev", "llm"} <= set(reports) else []
    )
    return BenchmarkReport(
        name=name or f"{dataset.name}-{metric}",
        dataset={
            "name": dataset.name,
            "hash": dataset.hash,
            "size": len(dataset),
            "path": str(dataset.path) if dataset.path else None,
        },
        metric=metric,
        metric_params=metric_params or {},
        pass_threshold=pass_threshold,
        escalate_below=escalate_below,
        concurrency=concurrency,
        evaluators={k: v for k, v in described.items() if k != "deterministic"},
        modes=reports,
        sweep=points,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _f(v: float | None, digits: int = 3) -> str:
    return "—" if v is None else f"{v:.{digits}f}"


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.0%}"


def _usd(v: float | None, complete: bool = True) -> str:
    if v is None:
        return "—"
    return f"${v:.6f}" + ("" if complete else " (partial)")


MODE_LABEL = {"jev": "Jev only", "llm": "LLM judge only", "cascade": "Adaptive cascade"}


def _row(cells: Sequence[object]) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


SUMMARY_HEADER = (
    "Mode", "n", "Errors", "Accuracy", "Precision", "Recall", "F1", "Brier ↓", "ECE ↓",
    "p50 latency", "p95 latency", "Total cost", "Cost / item", "Escalated",
)  # fmt: skip
SWEEP_HEADER = (
    "escalate_below", "Escalated", "Accuracy", "F1", "Total cost", "p50 latency", "p95 latency",
)  # fmt: skip
SWEEP_NOTE = (
    "Replays the recorded Jev-only and LLM-only judgments: a case uses Jev's verdict when its "
    "confidence is at least the threshold, otherwise the LLM judge's. Latency and cost add the "
    "LLM call for escalated cases."
)


def to_markdown(report: BenchmarkReport) -> str:
    ds = report.dataset
    params = report.metric_params or "{}"
    lines = [
        f"# Benchmark: {report.name}",
        "",
        f"- Date (UTC): {report.created_at:%Y-%m-%d %H:%M}",
        f"- EvalCascade: {report.version}",
        f"- Dataset: `{ds['name']}` ({ds['size']} labeled cases, hash `{ds['hash']}`)",
        f"- Metric: `{report.metric}` (pass threshold {report.pass_threshold:g}; params {params})",
        f"- Cascade escalation threshold: {report.escalate_below:g} · "
        f"concurrency {report.concurrency}",
    ]
    for name, cfg in report.evaluators.items():
        keys = ("kind", "model", "surface", "provider", "structured_output")
        details = ", ".join(f"{k}={v}" for k, v in cfg.items() if k in keys)
        lines.append(f"- Evaluator `{name}`: {details}")
    lines += ["", _row(SUMMARY_HEADER), _row(["---"] * len(SUMMARY_HEADER))]
    for mode, r in report.modes.items():
        c = r.classification
        lines.append(
            _row(
                [
                    MODE_LABEL.get(mode, mode),
                    r.n,
                    r.errors,
                    _f(c.accuracy),
                    _f(c.precision),
                    _f(c.recall),
                    _f(c.f1),
                    _f(r.calibration.brier),
                    _f(r.calibration.ece),
                    f"{_f(r.latency_ms['p50'], 0)} ms",
                    f"{_f(r.latency_ms['p95'], 0)} ms",
                    _usd(r.cost_usd, r.cost_complete),
                    _usd(r.cost_per_item_usd, r.cost_complete),
                    _pct(r.escalation_rate) if mode == "cascade" else "—",
                ]
            )
        )
    if report.sweep:
        lines += ["", "## Escalation-threshold sweep (counterfactual)", "", SWEEP_NOTE, ""]
        lines += [_row(SWEEP_HEADER), _row(["---"] * len(SWEEP_HEADER))]
        for p in report.sweep:
            lines.append(
                _row(
                    [
                        f"{p.escalate_below:g}",
                        _pct(p.escalation_rate),
                        _f(p.accuracy),
                        _f(p.f1),
                        _usd(p.cost_usd),
                        f"{_f(p.latency_p50_ms, 0)} ms",
                        f"{_f(p.latency_p95_ms, 0)} ms",
                    ]
                )
            )
    lines += ["", "## Reliability (P(pass) calibration)", ""]
    for mode, r in report.modes.items():
        cells = [
            f"[{b.lower:.1f}-{b.upper:.1f}): n={b.count}, p̄={_f(b.mean_probability, 2)}, "
            f"obs={_f(b.observed_frequency, 2)}"
            for b in r.calibration.bins
            if b.count
        ]
        lines += [f"**{MODE_LABEL.get(mode, mode)}** — " + ", ".join(cells), ""]
    if report.notes:
        lines += ["## Notes", "", *[f"- {n}" for n in report.notes], ""]
    return "\n".join(lines)
