"""The :class:`Metric` abstraction.

A metric describes *what* should be evaluated — never *who* evaluates it:

* :meth:`Metric.check` — an optional deterministic check. Return a
  :class:`DeterministicOutcome` when the answer can be decided without a model (e.g. an exact
  match against the reference), or ``None`` to defer to semantic judgment.
* :meth:`Metric.rubric` — a provider-independent :class:`~evalcascade.core.rubric.Rubric` of
  typed questions for semantic judgment, or ``None`` if the metric is purely deterministic.
* :meth:`Metric.aggregate` — combine the answers to the rubric's questions into one score.

The runtime chooses the evaluator (deterministic, Jev, LLM judge, ...) according to the
:class:`~evalcascade.core.policy.EvaluationPolicy`.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from evalcascade.core.results import MetricCategory
from evalcascade.core.rubric import Answer, QuestionKind, Rubric
from evalcascade.core.types import EvaluationRequest

DeterministicSupport = Literal["full", "partial", "none"]


class DeterministicOutcome(BaseModel):
    """Result of a deterministic check."""

    score: float = Field(ge=0.0, le=1.0)
    explanation: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class Aggregation(BaseModel):
    """A metric's combined score over the answers to its rubric."""

    score: float = Field(ge=0.0, le=1.0)
    explanation: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class MetricInfo(BaseModel):
    """Static metadata describing a metric (served by ``GET /api/metrics``)."""

    name: str
    display_name: str
    category: MetricCategory
    description: str
    primitives: list[QuestionKind]
    deterministic: DeterministicSupport
    required_fields: list[str]
    optional_fields: list[str]
    default_threshold: float
    requires_reasoning: bool


class Metric(BaseModel):
    """Base class for all metrics.

    Subclasses set the class-level metadata and implement :meth:`check` and/or
    :meth:`rubric`. Instance fields are configuration and are recorded with every experiment.
    """

    model_config = ConfigDict(extra="forbid")

    # -- class-level metadata (override in subclasses) --------------------------
    name: ClassVar[str] = "metric"
    display_name: ClassVar[str] = "Metric"
    category: ClassVar[MetricCategory] = "general"
    description: ClassVar[str] = ""
    primitives: ClassVar[tuple[QuestionKind, ...]] = ()
    deterministic_support: ClassVar[DeterministicSupport] = "none"
    required_fields: ClassVar[tuple[str, ...]] = ()
    optional_fields: ClassVar[tuple[str, ...]] = ()
    default_threshold: ClassVar[float] = 0.5
    requires_reasoning: ClassVar[bool] = False

    # -- instance configuration -------------------------------------------------
    threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Pass threshold on the normalized score."
    )
    weight: float = Field(default=1.0, ge=0.0, description="Weight in the overall score.")
    escalate_below: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Per-metric escalation threshold."
    )
    alias: str | None = Field(
        default=None, description="Report under this key (to use a metric twice in a suite)."
    )

    # -- identity -----------------------------------------------------------------

    @property
    def key(self) -> str:
        return self.alias or self.name

    @property
    def pass_threshold(self) -> float:
        return self.default_threshold if self.threshold is None else self.threshold

    # -- evaluation hooks ---------------------------------------------------------

    def missing_fields(self, request: EvaluationRequest) -> list[str]:
        return [f for f in self.required_fields if not request.has(f)]

    def check(self, request: EvaluationRequest) -> DeterministicOutcome | None:
        """Deterministic evaluation. Return ``None`` to defer to semantic judgment."""
        return None

    def rubric(self, request: EvaluationRequest) -> Rubric | None:
        """Semantic judgment spec. Return ``None`` if the metric cannot be judged semantically."""
        return None

    def not_applicable_reason(self, request: EvaluationRequest) -> str:
        """Explanation used when neither :meth:`check` nor :meth:`rubric` applies."""
        return f"{self.display_name} is not applicable to this case"

    def aggregate(self, answers: dict[str, Answer], rubric: Rubric) -> Aggregation:
        """Combine per-question answers. Default: weighted mean of normalized scores."""
        total_weight = 0.0
        acc = 0.0
        for q in rubric.questions:
            a = answers[q.id]
            acc += a.score * q.weight
            total_weight += q.weight
        explanations = [
            answers[q.id].explanation for q in rubric.questions if answers[q.id].explanation
        ]
        return Aggregation(
            score=acc / total_weight if total_weight else 0.0,
            explanation=" ".join(e for e in explanations if e) or None,
        )

    # -- metadata -------------------------------------------------------------------

    def config(self) -> dict[str, Any]:
        """Serializable configuration, recorded with experiments."""
        return {"name": self.key, "metric": self.name, "params": self.model_dump(exclude_none=True)}

    @classmethod
    def info(cls) -> MetricInfo:
        return MetricInfo(
            name=cls.name,
            display_name=cls.display_name,
            category=cls.category,
            description=cls.description,
            primitives=list(cls.primitives),
            deterministic=cls.deterministic_support,
            required_fields=list(cls.required_fields),
            optional_fields=list(cls.optional_fields),
            default_threshold=cls.default_threshold,
            requires_reasoning=cls.requires_reasoning,
        )
