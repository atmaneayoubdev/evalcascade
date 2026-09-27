"""Result models produced by evaluators and the cascade runtime."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from evalcascade.core.rubric import Answer
from evalcascade.core.types import EvaluationRequest, Usage

MetricStatus = Literal["ok", "skipped", "error"]
Route = Literal["deterministic", "jev", "llm", "jev_to_llm", "none"]
EscalationReason = Literal["low_confidence", "primary_error", "requires_reasoning"]
EvaluatorKind = Literal["deterministic", "system_one", "llm_judge", "simulated"]
CostSource = Literal["provider", "estimated", "unknown", "none"]
MetricCategory = Literal["general", "rag", "agent"]


class Judgment(BaseModel):
    """One evaluator's verdict on one metric for one request."""

    evaluator: str
    evaluator_kind: EvaluatorKind
    model: str | None = None
    score: float | None = None
    confidence: float | None = None
    pass_probability: float | None = None
    answers: dict[str, Answer] = Field(default_factory=dict)
    explanation: str | None = None
    latency_ms: float = 0.0
    usage: Usage = Field(default_factory=Usage)
    cost_usd: float = 0.0
    cost_source: CostSource = "none"
    request_id: str | None = None
    error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None and self.score is not None


class MetricResult(BaseModel):
    """The final outcome of one metric, including the full judgment chain."""

    metric: str
    display_name: str
    category: MetricCategory
    status: MetricStatus
    score: float | None = None
    passed: bool | None = None
    threshold: float
    route: Route = "none"
    final_evaluator: str | None = None
    escalated: bool = False
    escalation_reason: EscalationReason | None = None
    confidence: float | None = None
    escalate_below: float | None = None
    judgments: list[Judgment] = Field(default_factory=list)
    explanation: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    message: str | None = None

    @property
    def primary_judgment(self) -> Judgment | None:
        return self.judgments[0] if self.judgments else None

    @property
    def final_judgment(self) -> Judgment | None:
        return self.judgments[-1] if self.judgments else None

    @property
    def cost_complete(self) -> bool:
        return all(j.cost_source != "unknown" for j in self.judgments)


class EvaluationResult(BaseModel):
    """All metric results for a single request."""

    case_id: str | None = None
    overall_score: float | None = None
    passed: bool | None = None
    metrics: list[MetricResult] = Field(default_factory=list)
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    escalations: int = 0
    error: str | None = None

    def __getitem__(self, name: str) -> MetricResult:
        for m in self.metrics:
            if m.metric == name:
                return m
        raise KeyError(name)

    def get(self, name: str) -> MetricResult | None:
        return next((m for m in self.metrics if m.metric == name), None)

    @property
    def scores(self) -> dict[str, float | None]:
        return {m.metric: m.score for m in self.metrics}

    def summary(self) -> str:
        """A compact human-readable summary (one line per metric)."""
        lines = [
            f"overall={_fmt(self.overall_score)} passed={self.passed} cost=${self.cost_usd:.6f}"
        ]
        for m in self.metrics:
            route = m.route + (f" ({m.escalation_reason})" if m.escalated else "")
            lines.append(f"  {m.metric:<24} {m.status:<7} score={_fmt(m.score)} via {route}")
        return "\n".join(lines)


class CaseResult(EvaluationResult):
    """An evaluation result together with the case it was computed for."""

    case: EvaluationRequest


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"
