"""Evaluation policy: which evaluator judges each metric, and when to escalate.

The default policy is the System One → System Two cascade::

    EvaluationPolicy(
        deterministic_first=True,  # use a metric's deterministic check when it can decide
        primary="jev",             # fast System One judgment
        fallback="llm",            # generative LLM judge
        escalate_below=0.82,       # escalate when Jev confidence < 0.82
    )

Thresholds can be set globally, per metric instance (``Groundedness(escalate_below=0.9)``) or
per metric in the policy (``overrides={"groundedness": MetricPolicy(escalate_below=0.9)}``).
Precedence: policy override > metric instance > global default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from evalcascade.core.metric import Metric

PolicyPreset = Literal["cascade", "jev", "llm", "deterministic"]


class MetricPolicy(BaseModel):
    """Per-metric policy overrides. ``None`` means "inherit from the global policy"."""

    model_config = ConfigDict(extra="forbid")

    deterministic_first: bool | None = None
    primary: str | None = None
    fallback: str | None = None
    escalate: bool | None = Field(
        default=None, description="Set to False to never escalate this metric."
    )
    escalate_below: float | None = Field(default=None, ge=0.0, le=1.0)


@dataclass(frozen=True)
class ResolvedPolicy:
    """The effective policy for one metric after applying overrides."""

    deterministic_first: bool
    primary: str | None
    fallback: str | None
    escalate_below: float
    escalate_on_error: bool
    route_reasoning_to_fallback: bool


class EvaluationPolicy(BaseModel):
    """Routing policy for the evaluation cascade."""

    model_config = ConfigDict(extra="forbid")

    deterministic_first: bool = True
    primary: str | None = "jev"
    fallback: str | None = "llm"
    escalate_below: float = Field(default=0.82, ge=0.0, le=1.0)
    escalate_on_error: bool = Field(
        default=True, description="Escalate to the fallback when the primary evaluator errors."
    )
    route_reasoning_to_fallback: bool = Field(
        default=True,
        description="Send rubrics flagged requires_reasoning straight to the fallback judge.",
    )
    overrides: dict[str, MetricPolicy] = Field(default_factory=dict)

    # -- presets ---------------------------------------------------------------

    @classmethod
    def cascade(
        cls, escalate_below: float = 0.82, *, primary: str = "jev", fallback: str = "llm"
    ) -> EvaluationPolicy:
        """Deterministic → Jev → LLM judge on low confidence (the default)."""
        return cls(primary=primary, fallback=fallback, escalate_below=escalate_below)

    @classmethod
    def jev_only(cls) -> EvaluationPolicy:
        """Deterministic checks, then Jev. Never calls a generative judge."""
        return cls(primary="jev", fallback=None, route_reasoning_to_fallback=False)

    @classmethod
    def llm_only(cls, judge: str = "llm") -> EvaluationPolicy:
        """Deterministic checks, then the generative judge for everything semantic."""
        return cls(primary=judge, fallback=None, route_reasoning_to_fallback=False)

    @classmethod
    def deterministic_only(cls) -> EvaluationPolicy:
        """Only deterministic checks; semantic metrics are skipped. Needs no API keys."""
        return cls(primary=None, fallback=None, route_reasoning_to_fallback=False)

    @classmethod
    def preset(
        cls, name: PolicyPreset | str, escalate_below: float | None = None
    ) -> EvaluationPolicy:
        match name:
            case "cascade":
                return cls.cascade(0.82 if escalate_below is None else escalate_below)
            case "jev" | "jev_only":
                return cls.jev_only()
            case "llm" | "llm_only":
                return cls.llm_only()
            case "deterministic" | "deterministic_only":
                return cls.deterministic_only()
        raise ValueError(f"unknown policy preset {name!r}; use cascade, jev, llm or deterministic")

    # -- resolution ------------------------------------------------------------

    def resolve(self, metric: Metric) -> ResolvedPolicy:
        override = self.overrides.get(metric.key) or MetricPolicy()

        escalate_below = self.escalate_below
        if metric.escalate_below is not None:
            escalate_below = metric.escalate_below
        if override.escalate_below is not None:
            escalate_below = override.escalate_below

        primary = override.primary if override.primary is not None else self.primary
        fallback = override.fallback if override.fallback is not None else self.fallback
        if override.escalate is False or fallback == primary:
            fallback = None if primary is not None else fallback

        return ResolvedPolicy(
            deterministic_first=(
                self.deterministic_first
                if override.deterministic_first is None
                else override.deterministic_first
            ),
            primary=primary,
            fallback=fallback,
            escalate_below=escalate_below,
            escalate_on_error=self.escalate_on_error,
            route_reasoning_to_fallback=self.route_reasoning_to_fallback,
        )

    def evaluator_names(self) -> set[str]:
        names = {n for n in (self.primary, self.fallback) if n}
        for o in self.overrides.values():
            names.update(n for n in (o.primary, o.fallback) if n)
        return names
