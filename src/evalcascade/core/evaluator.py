"""The :class:`Evaluator` abstraction — *how* a metric gets judged.

Three families ship with EvalCascade:

* :class:`~evalcascade.evaluators.DeterministicEvaluator` — runs a metric's ``check()``.
* :class:`~evalcascade.evaluators.JevEvaluator` — answers rubrics with TypeSafe Jev (System One).
* :class:`~evalcascade.evaluators.LLMJudge` / ``OpenRouterLLMJudge`` — a generative judge.

Semantic evaluators only need to implement :meth:`SemanticEvaluator.answer`, which answers the
typed questions of a :class:`~evalcascade.core.rubric.Rubric`. Scoring, confidence and error
handling are shared so every backend is scored identically.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

from evalcascade.core.metric import Metric
from evalcascade.core.results import CostSource, EvaluatorKind, Judgment, Route
from evalcascade.core.rubric import Answer, Rubric, pass_probability
from evalcascade.core.types import EvaluationRequest, Usage
from evalcascade.errors import EvalCascadeError
from evalcascade.redaction import redact


@dataclass
class EvalItem:
    """A unit of semantic work: one metric, one request, one rubric."""

    metric: Metric
    request: EvaluationRequest
    rubric: Rubric


@dataclass
class RawAnswers:
    """What a semantic backend returns for one rubric, before metric aggregation."""

    answers: dict[str, Answer]
    model: str | None = None
    latency_ms: float = 0.0
    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0
    cost_source: CostSource = "none"
    request_id: str | None = None
    explanation: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class Evaluator(ABC):
    """Base class for evaluator backends."""

    name: str = "evaluator"
    kind: ClassVar[EvaluatorKind] = "llm_judge"
    #: Label used for routing statistics ("jev" for System One, "llm" for generative judges).
    route_label: Route = "llm"

    @abstractmethod
    async def evaluate(
        self, metric: Metric, request: EvaluationRequest, rubric: Rubric | None = None
    ) -> Judgment:
        """Judge ``metric`` on ``request``. Must not raise for provider failures."""

    async def evaluate_batch(self, items: Sequence[EvalItem]) -> list[Judgment]:
        """Judge several items. Backends may override to batch requests."""
        return list(
            await asyncio.gather(*(self.evaluate(i.metric, i.request, i.rubric) for i in items))
        )

    def available(self) -> tuple[bool, str | None]:
        """Whether the evaluator is usable (e.g. its API key is configured)."""
        return True, None

    def describe(self) -> dict[str, Any]:
        """Configuration summary recorded with experiments. Never includes secrets."""
        return {"name": self.name, "kind": self.kind}

    async def aclose(self) -> None:  # noqa: B027 - optional hook
        """Release network resources."""


class SemanticEvaluator(Evaluator):
    """Base for evaluators that answer rubrics (Jev, LLM judges, simulators)."""

    @abstractmethod
    async def answer(self, rubric: Rubric) -> RawAnswers:
        """Answer every question in ``rubric``. May raise :class:`EvalCascadeError`."""

    @property
    def model_name(self) -> str | None:
        return None

    async def evaluate(
        self, metric: Metric, request: EvaluationRequest, rubric: Rubric | None = None
    ) -> Judgment:
        if rubric is None:
            rubric = metric.rubric(request)
        if rubric is None:
            return self.error_judgment(f"{metric.display_name} has no rubric for this case")
        try:
            raw = await self.answer(rubric)
        except EvalCascadeError as exc:
            return self.error_judgment(str(exc))
        return self.to_judgment(metric, rubric, raw)

    # -- shared helpers -------------------------------------------------------------

    def error_judgment(self, message: str, **kwargs: Any) -> Judgment:
        return Judgment(
            evaluator=self.name,
            evaluator_kind=self.kind,
            model=self.model_name,
            error=redact(message),
            **kwargs,
        )

    def to_judgment(self, metric: Metric, rubric: Rubric, raw: RawAnswers) -> Judgment:
        """Aggregate raw answers into a scored :class:`Judgment`."""
        missing = [q.id for q in rubric.questions if q.id not in raw.answers]
        if missing:
            return self.error_judgment(
                f"response is missing answers for question(s): {', '.join(missing)}",
                latency_ms=raw.latency_ms,
                usage=raw.usage,
                cost_usd=raw.cost_usd,
                cost_source=raw.cost_source,
                request_id=raw.request_id,
            )
        aggregation = metric.aggregate(raw.answers, rubric)
        confidences = [a.confidence for a in raw.answers.values() if a.confidence is not None]
        pass_prob = None
        if len(rubric.questions) == 1:
            q = rubric.questions[0]
            pass_prob = pass_probability(q, raw.answers[q.id], metric.pass_threshold)
        explanation = aggregation.explanation or raw.explanation
        return Judgment(
            evaluator=self.name,
            evaluator_kind=self.kind,
            model=raw.model or self.model_name,
            score=aggregation.score,
            # A multi-question judgment is only as confident as its least confident answer.
            confidence=min(confidences) if confidences else None,
            pass_probability=pass_prob,
            answers=raw.answers,
            explanation=explanation,
            latency_ms=raw.latency_ms,
            usage=raw.usage,
            cost_usd=raw.cost_usd,
            cost_source=raw.cost_source,
            request_id=raw.request_id,
            details={**raw.details, **aggregation.details},
        )
