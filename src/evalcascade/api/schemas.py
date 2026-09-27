"""Request / response models of the local API (see docs/api-contract.ts)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from evalcascade.core.types import AgentTrace, Expected
from evalcascade.experiments.experiment import DatasetRef, Experiment
from evalcascade.experiments.summary import ExperimentSummary, RouteCounts
from evalcascade.storage.store import DatasetInfo, ExperimentListItem


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: Literal["ok", "error"]


class MetricSpec(BaseModel):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class EvaluateRequest(BaseModel):
    input: str | None = None
    output: str | None = None
    context: list[str] = Field(default_factory=list)
    expected: Expected | str | None = None
    trace: AgentTrace | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    metrics: list[str | MetricSpec] = Field(
        default_factory=lambda: ["answer_relevance"],
        description="Metric names, suite names (general/rag/agent) or {name, params}.",
    )
    policy: Literal["cascade", "jev", "llm", "deterministic"] | None = Field(
        default=None, description="Policy preset; defaults to the server configuration."
    )
    escalate_below: float | None = Field(default=None, ge=0.0, le=1.0)


class ExperimentDetail(BaseModel):
    id: str
    name: str
    created_at: datetime
    dataset_name: str | None
    is_demo: bool
    tags: list[str]
    summary: ExperimentSummary
    dataset: DatasetRef
    metrics: list[dict[str, Any]]
    policy: dict[str, Any]
    evaluators: dict[str, dict[str, Any]]
    notes: str | None
    version: str

    @classmethod
    def of(cls, experiment: Experiment) -> ExperimentDetail:
        return cls(
            **experiment.model_dump(exclude={"results"}),
            dataset_name=experiment.dataset.name,
        )


class DatasetDetail(BaseModel):
    dataset: DatasetInfo
    cases: Page


class Page(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[Any]


class DatasetUpload(BaseModel):
    name: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    description: str | None = None
    cases: list[dict[str, Any]] = Field(min_length=1)
    overwrite: bool = False


class GateRequest(BaseModel):
    baseline: str
    candidate: str
    max_quality_drop: float = Field(default=0.03, ge=0.0)
    metric_thresholds: dict[str, float] = Field(default_factory=dict)
    max_metric_drop: float | None = Field(default=None, ge=0.0)
    max_cost_increase: float | None = Field(default=None, ge=0.0)
    max_latency_increase: float | None = Field(default=None, ge=0.0)
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    max_escalation_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    require_same_dataset: bool = False


class TrendPoint(BaseModel):
    id: str
    name: str
    created_at: datetime
    overall_score: float | None
    pass_rate: float | None
    cost_usd: float
    escalation_rate: float | None
    jev_acceptance_rate: float | None
    is_demo: bool


class RegressionIndicator(BaseModel):
    name: str
    baseline_id: str
    candidate_id: str
    delta_overall: float | None
    regressed: bool
    is_demo: bool


class OverviewTotals(BaseModel):
    experiments: int
    cases: int
    evaluations: int
    cost_usd: float


class OverviewAverages(BaseModel):
    overall_score: float | None
    pass_rate: float | None
    jev_acceptance_rate: float | None
    escalation_rate: float | None
    latency_p50_ms: float | None


class Overview(BaseModel):
    has_real_data: bool
    has_demo_data: bool
    totals: OverviewTotals
    averages: OverviewAverages
    routing: RouteCounts
    recent: list[ExperimentListItem]
    trend: list[TrendPoint]
    regressions: list[RegressionIndicator]


DatasetDetail.model_rebuild()
