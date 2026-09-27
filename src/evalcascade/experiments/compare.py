"""Compare two experiments: aggregate deltas plus case-level regressions."""

from __future__ import annotations

from pydantic import BaseModel, Field

from evalcascade.experiments.experiment import Experiment, ExperimentRef


class Delta(BaseModel):
    baseline: float | None = None
    candidate: float | None = None
    delta: float | None = None
    relative: float | None = None

    @classmethod
    def of(cls, baseline: float | None, candidate: float | None) -> Delta:
        if baseline is None or candidate is None:
            return cls(baseline=baseline, candidate=candidate)
        delta = candidate - baseline
        relative = delta / abs(baseline) if baseline else None
        return cls(baseline=baseline, candidate=candidate, delta=delta, relative=relative)


class CaseDelta(BaseModel):
    case_id: str
    baseline: float | None = None
    candidate: float | None = None
    delta: float | None = None


class CaseComparison(BaseModel):
    matched: int = 0
    improved: int = 0
    regressed: int = 0
    unchanged: int = 0
    only_in_baseline: int = 0
    only_in_candidate: int = 0
    top_regressions: list[CaseDelta] = Field(default_factory=list)
    top_improvements: list[CaseDelta] = Field(default_factory=list)


class Comparison(BaseModel):
    baseline: ExperimentRef
    candidate: ExperimentRef
    dataset_match: bool
    overall_score: Delta
    pass_rate: Delta
    cost_usd: Delta
    cost_per_case_usd: Delta
    latency_p50_ms: Delta
    latency_p95_ms: Delta
    jev_acceptance_rate: Delta
    escalation_rate: Delta
    metrics: dict[str, Delta]
    cases: CaseComparison


def compare_experiments(
    baseline: Experiment, candidate: Experiment, *, tolerance: float = 0.01, top: int = 10
) -> Comparison:
    """Compare ``candidate`` against ``baseline``. Positive deltas mean "candidate is higher"."""
    b, c = baseline.summary, candidate.summary
    metric_names = list(dict.fromkeys([*b.metrics, *c.metrics]))
    metrics = {
        name: Delta.of(
            b.metrics[name].mean if name in b.metrics else None,
            c.metrics[name].mean if name in c.metrics else None,
        )
        for name in metric_names
    }

    base_cases = {r.case_id: r.overall_score for r in baseline.results if r.case_id is not None}
    cand_cases = {r.case_id: r.overall_score for r in candidate.results if r.case_id is not None}
    deltas: list[CaseDelta] = []
    for case_id in base_cases.keys() & cand_cases.keys():
        bs, cs = base_cases[case_id], cand_cases[case_id]
        deltas.append(
            CaseDelta(
                case_id=case_id,
                baseline=bs,
                candidate=cs,
                delta=None if bs is None or cs is None else cs - bs,
            )
        )
    scored = [d for d in deltas if d.delta is not None]
    regressions = sorted(
        (d for d in scored if (d.delta or 0) < -tolerance), key=lambda d: d.delta or 0
    )
    improvements = sorted(
        (d for d in scored if (d.delta or 0) > tolerance), key=lambda d: -(d.delta or 0)
    )

    return Comparison(
        baseline=baseline.ref,
        candidate=candidate.ref,
        dataset_match=bool(baseline.dataset.hash)
        and baseline.dataset.hash == candidate.dataset.hash,
        overall_score=Delta.of(b.overall_score, c.overall_score),
        pass_rate=Delta.of(b.pass_rate, c.pass_rate),
        cost_usd=Delta.of(b.cost_usd, c.cost_usd),
        cost_per_case_usd=Delta.of(b.cost_per_case_usd, c.cost_per_case_usd),
        latency_p50_ms=Delta.of(b.latency_ms.p50, c.latency_ms.p50),
        latency_p95_ms=Delta.of(b.latency_ms.p95, c.latency_ms.p95),
        jev_acceptance_rate=Delta.of(b.routing.jev_acceptance_rate, c.routing.jev_acceptance_rate),
        escalation_rate=Delta.of(b.routing.escalation_rate, c.routing.escalation_rate),
        metrics=metrics,
        cases=CaseComparison(
            matched=len(deltas),
            improved=len(improvements),
            regressed=len(regressions),
            unchanged=len(scored) - len(improvements) - len(regressions),
            only_in_baseline=len(base_cases.keys() - cand_cases.keys()),
            only_in_candidate=len(cand_cases.keys() - base_cases.keys()),
            top_regressions=regressions[:top],
            top_improvements=improvements[:top],
        ),
    )
