"""CI-friendly regression gates.

A :class:`RegressionGate` compares a candidate experiment against a baseline and fails when
quality drops more than allowed (overall and/or per metric), or when optional cost, latency,
escalation-rate or absolute-score limits are violated::

    gate = RegressionGate(max_quality_drop=0.03, metric_thresholds={"groundedness": 0.05})
    result = gate.evaluate(baseline, candidate)
    sys.exit(0 if result.passed else 1)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from evalcascade.experiments.compare import Comparison, Delta, compare_experiments
from evalcascade.experiments.experiment import Experiment


class GateCheck(BaseModel):
    name: str
    passed: bool
    actual: float | None = None
    limit: float
    message: str


class GateResult(BaseModel):
    passed: bool
    checks: list[GateCheck]
    violations: list[GateCheck]
    comparison: Comparison

    def to_text(self) -> str:
        lines = [f"Regression gate: {'PASSED' if self.passed else 'FAILED'}"]
        for c in self.checks:
            lines.append(f"  [{'ok' if c.passed else 'FAIL'}] {c.name}: {c.message}")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        cmp = self.comparison
        icon = "✅" if self.passed else "❌"
        lines = [
            f"## {icon} EvalCascade regression gate {'passed' if self.passed else 'failed'}",
            "",
            f"Baseline `{cmp.baseline.name}` ({cmp.baseline.id}) → candidate "
            f"`{cmp.candidate.name}` ({cmp.candidate.id})",
            "",
            "| Check | Result | Actual | Limit | Details |",
            "|---|---|---|---|---|",
        ]
        for c in self.checks:
            actual = "n/a" if c.actual is None else f"{c.actual:.4f}"
            lines.append(f"| `{c.name}` | {'✅' if c.passed else '❌'} | {actual} | {c.limit:g} | {c.message} |")
        lines += [
            "",
            "| Metric | Baseline | Candidate | Δ |",
            "|---|---|---|---|",
        ]
        rows: list[tuple[str, Delta]] = [("**overall**", cmp.overall_score)]
        rows += list(cmp.metrics.items())
        for name, d in rows:
            lines.append(f"| {name} | {_f(d.baseline)} | {_f(d.candidate)} | {_signed(d.delta)} |")
        if cmp.cases.top_regressions:
            lines += ["", "<details><summary>Top case regressions</summary>", ""]
            lines += [f"- `{r.case_id}`: {_f(r.baseline)} → {_f(r.candidate)} ({_signed(r.delta)})" for r in cmp.cases.top_regressions]
            lines += ["", "</details>"]
        return "\n".join(lines) + "\n"


class RegressionGate(BaseModel):
    """Thresholds for a regression gate. Drops are absolute on the 0-1 score scale."""

    max_quality_drop: float = Field(default=0.03, ge=0.0, description="Max overall score drop.")
    metric_thresholds: dict[str, float] = Field(
        default_factory=dict, description="Max score drop per metric."
    )
    max_metric_drop: float | None = Field(
        default=None, ge=0.0, description="Default max drop for every metric not listed above."
    )
    max_cost_increase: float | None = Field(
        default=None, ge=0.0, description="Max relative increase in total cost (0.2 = +20%)."
    )
    max_latency_increase: float | None = Field(
        default=None, ge=0.0, description="Max relative increase in p95 case latency."
    )
    min_score: float | None = Field(default=None, ge=0.0, le=1.0, description="Floor on candidate overall.")
    max_escalation_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    require_same_dataset: bool = False

    def evaluate(self, baseline: Experiment, candidate: Experiment) -> GateResult:
        comparison = compare_experiments(baseline, candidate)
        checks: list[GateCheck] = [self._drop_check("overall_score", comparison.overall_score, self.max_quality_drop)]

        limits = {name: self.max_metric_drop for name in comparison.metrics if self.max_metric_drop is not None}
        limits.update(self.metric_thresholds)
        for name, limit in limits.items():
            if limit is None:
                continue
            delta = comparison.metrics.get(name)
            if delta is None or delta.candidate is None and delta.baseline is not None:
                checks.append(GateCheck(name=f"metric:{name}", passed=False, limit=limit, message="metric missing from candidate"))
                continue
            if delta.baseline is None:
                checks.append(GateCheck(name=f"metric:{name}", passed=True, limit=limit, message="new metric (no baseline)"))
                continue
            checks.append(self._drop_check(f"metric:{name}", delta, limit))

        if self.max_cost_increase is not None:
            checks.append(self._increase_check("cost", comparison.cost_usd, self.max_cost_increase))
        if self.max_latency_increase is not None:
            checks.append(self._increase_check("latency_p95", comparison.latency_p95_ms, self.max_latency_increase))
        if self.min_score is not None:
            score = candidate.summary.overall_score
            checks.append(
                GateCheck(
                    name="min_score",
                    passed=score is not None and score >= self.min_score,
                    actual=score,
                    limit=self.min_score,
                    message=f"candidate overall {_f(score)} (floor {self.min_score:g})",
                )
            )
        if self.max_escalation_rate is not None:
            rate = candidate.summary.routing.escalation_rate
            checks.append(
                GateCheck(
                    name="escalation_rate",
                    passed=rate is None or rate <= self.max_escalation_rate,
                    actual=rate,
                    limit=self.max_escalation_rate,
                    message=f"candidate escalation rate {_f(rate)} (max {self.max_escalation_rate:g})",
                )
            )
        if self.require_same_dataset:
            checks.append(
                GateCheck(
                    name="dataset",
                    passed=comparison.dataset_match,
                    limit=1,
                    message="same dataset" if comparison.dataset_match else "baseline and candidate used different datasets",
                )
            )
        violations = [c for c in checks if not c.passed]
        return GateResult(passed=not violations, checks=checks, violations=violations, comparison=comparison)

    @staticmethod
    def _drop_check(name: str, delta: Delta, limit: float) -> GateCheck:
        if delta.baseline is None or delta.candidate is None:
            return GateCheck(name=name, passed=False, limit=limit, message="score unavailable in baseline or candidate")
        drop = delta.baseline - delta.candidate
        passed = drop <= limit + 1e-12
        return GateCheck(
            name=name,
            passed=passed,
            actual=drop,
            limit=limit,
            message=f"{_f(delta.baseline)} -> {_f(delta.candidate)} (drop {drop:+.4f}, max {limit:g})",
        )

    @staticmethod
    def _increase_check(name: str, delta: Delta, limit: float) -> GateCheck:
        if delta.baseline is None or delta.candidate is None:
            return GateCheck(name=name, passed=True, limit=limit, message="not measured")
        if delta.baseline == 0:
            passed = delta.candidate == 0
            rel = 0.0 if passed else None
        else:
            rel = (delta.candidate - delta.baseline) / abs(delta.baseline)
            passed = rel <= limit + 1e-12
        return GateCheck(
            name=name,
            passed=passed,
            actual=rel,
            limit=limit,
            message=f"{delta.baseline:.6g} -> {delta.candidate:.6g} ({'n/a' if rel is None else f'{rel:+.1%}'}, max +{limit:.0%})",
        )


def _f(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _signed(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.3f}"
