"""Aggregate statistics over the case results of an experiment.

Routing definitions (per metric evaluation that was not skipped):

* ``jev_attempts`` — the primary System One evaluator judged it (route ``jev`` or ``jev_to_llm``)
* ``jev_accepted`` — Jev's judgment was final (route ``jev``, not escalated, status ok)
* ``escalated`` — escalation to the fallback judge was triggered
* ``jev_acceptance_rate`` = jev_accepted / jev_attempts
* ``escalation_rate`` = escalated / jev_attempts
* ``llm_rate`` = (escalated + llm_direct) / total
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

from pydantic import BaseModel, Field

from evalcascade.core.results import EvaluationResult, MetricCategory, MetricResult

HISTOGRAM_BINS = 10


class LatencyStats(BaseModel):
    mean: float | None = None
    p50: float | None = None
    p95: float | None = None
    max: float | None = None


class RouteCounts(BaseModel):
    deterministic: int = 0
    jev: int = 0
    llm: int = 0
    jev_to_llm: int = 0
    none: int = 0


class RoutingSummary(BaseModel):
    total: int = 0
    deterministic: int = 0
    jev_attempts: int = 0
    jev_accepted: int = 0
    escalated: int = 0
    llm_direct: int = 0
    skipped: int = 0
    errors: int = 0
    deterministic_rate: float | None = None
    jev_acceptance_rate: float | None = None
    escalation_rate: float | None = None
    llm_rate: float | None = None


class AgreementStats(BaseModel):
    """Verdict agreement between Jev and the LLM judge on escalated evaluations."""

    compared: int = 0
    agreement_rate: float | None = None


class MetricSummary(BaseModel):
    metric: str
    display_name: str
    category: MetricCategory
    mean: float | None = None
    std: float | None = None
    min: float | None = None
    max: float | None = None
    pass_rate: float | None = None
    count: int = 0
    skipped: int = 0
    errors: int = 0
    histogram: list[int] = Field(default_factory=lambda: [0] * HISTOGRAM_BINS)
    routes: RouteCounts = Field(default_factory=RouteCounts)
    escalation_rate: float | None = None
    mean_latency_ms: float | None = None
    cost_usd: float = 0.0


class ExperimentSummary(BaseModel):
    num_cases: int = 0
    num_evaluations: int = 0
    overall_score: float | None = None
    pass_rate: float | None = None
    metrics: dict[str, MetricSummary] = Field(default_factory=dict)
    cost_usd: float = 0.0
    cost_per_case_usd: float | None = None
    cost_complete: bool = True
    latency_ms: LatencyStats = Field(default_factory=LatencyStats)
    routing: RoutingSummary = Field(default_factory=RoutingSummary)
    agreement: AgreementStats = Field(default_factory=AgreementStats)
    errors: int = 0


def percentile(values: Sequence[float], q: float) -> float | None:
    """Linear-interpolation percentile (``q`` in [0, 100]), like numpy's default."""
    if not values:
        return None
    data = sorted(values)
    if len(data) == 1:
        return data[0]
    rank = (len(data) - 1) * q / 100.0
    lo, hi = math.floor(rank), math.ceil(rank)
    return data[lo] + (data[hi] - data[lo]) * (rank - lo)


def latency_stats(values: Sequence[float]) -> LatencyStats:
    if not values:
        return LatencyStats()
    return LatencyStats(
        mean=statistics.fmean(values), p50=percentile(values, 50), p95=percentile(values, 95), max=max(values)
    )


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def histogram(scores: Sequence[float], bins: int = HISTOGRAM_BINS) -> list[int]:
    counts = [0] * bins
    for s in scores:
        counts[min(bins - 1, max(0, int(s * bins)))] += 1
    return counts


def _route_bucket(result: MetricResult) -> str:
    if result.status == "skipped":
        return "none"
    return result.route


def summarize(results: Sequence[EvaluationResult]) -> ExperimentSummary:
    """Compute the :class:`ExperimentSummary` of a list of case results."""
    by_metric: dict[str, list[MetricResult]] = {}
    for case in results:
        for m in case.metrics:
            by_metric.setdefault(m.metric, []).append(m)

    routing = RoutingSummary()
    agree = compared = 0
    cost_complete = True
    metric_summaries: dict[str, MetricSummary] = {}
    for key, items in by_metric.items():
        first = items[0]
        ok = [m for m in items if m.status == "ok" and m.score is not None]
        scores = [m.score for m in ok if m.score is not None]
        routes = RouteCounts()
        m_attempts = m_escalated = 0
        for m in items:
            bucket = _route_bucket(m)
            setattr(routes, bucket, getattr(routes, bucket) + 1)
            cost_complete = cost_complete and m.cost_complete
            if m.status == "skipped":
                routing.skipped += 1
                continue
            routing.total += 1
            if m.status == "error":
                routing.errors += 1
            if m.route == "deterministic":
                routing.deterministic += 1
            elif m.route in ("jev", "jev_to_llm"):
                routing.jev_attempts += 1
                m_attempts += 1
                if m.escalated:
                    routing.escalated += 1
                    m_escalated += 1
                elif m.status == "ok":
                    routing.jev_accepted += 1
            elif m.route == "llm":
                routing.llm_direct += 1
            if m.route == "jev_to_llm" and len(m.judgments) >= 2:
                primary, final = m.judgments[0], m.judgments[-1]
                if primary.score is not None and final.score is not None:
                    compared += 1
                    agree += (primary.score >= m.threshold) == (final.score >= m.threshold)
        passed = [m.passed for m in ok if m.passed is not None]
        latencies = [m.latency_ms for m in items if m.status != "skipped"]
        metric_summaries[key] = MetricSummary(
            metric=key,
            display_name=first.display_name,
            category=first.category,
            mean=statistics.fmean(scores) if scores else None,
            std=statistics.pstdev(scores) if len(scores) > 1 else (0.0 if scores else None),
            min=min(scores) if scores else None,
            max=max(scores) if scores else None,
            pass_rate=_ratio(sum(passed), len(passed)),
            count=len(ok),
            skipped=sum(1 for m in items if m.status == "skipped"),
            errors=sum(1 for m in items if m.status == "error"),
            histogram=histogram(scores),
            routes=routes,
            escalation_rate=_ratio(m_escalated, m_attempts),
            mean_latency_ms=statistics.fmean(latencies) if latencies else None,
            cost_usd=sum(m.cost_usd for m in items),
        )

    routing.deterministic_rate = _ratio(routing.deterministic, routing.total)
    routing.jev_acceptance_rate = _ratio(routing.jev_accepted, routing.jev_attempts)
    routing.escalation_rate = _ratio(routing.escalated, routing.jev_attempts)
    routing.llm_rate = _ratio(routing.escalated + routing.llm_direct, routing.total)

    overall = [r.overall_score for r in results if r.overall_score is not None]
    passed_cases = [r.passed for r in results if r.passed is not None]
    cost = sum(r.cost_usd for r in results)
    return ExperimentSummary(
        num_cases=len(results),
        num_evaluations=routing.total,
        overall_score=statistics.fmean(overall) if overall else None,
        pass_rate=_ratio(sum(passed_cases), len(passed_cases)),
        metrics=metric_summaries,
        cost_usd=cost,
        cost_per_case_usd=cost / len(results) if results else None,
        cost_complete=cost_complete,
        latency_ms=latency_stats([r.latency_ms for r in results]),
        routing=routing,
        agreement=AgreementStats(compared=compared, agreement_rate=_ratio(agree, compared)),
        errors=routing.errors,
    )
