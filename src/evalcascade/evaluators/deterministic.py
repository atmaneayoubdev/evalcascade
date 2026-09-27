"""Deterministic evaluator — runs a metric's ``check()``. Free, instant, confidence 1.0."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from evalcascade.core.evaluator import Evaluator
from evalcascade.core.metric import Metric
from evalcascade.core.results import EvaluatorKind, Judgment, Route
from evalcascade.core.rubric import Rubric
from evalcascade.core.types import EvaluationRequest


class DeterministicEvaluator(Evaluator):
    """Evaluates metrics whose outcome can be decided by code (exact match, regex, schema...)."""

    name = "deterministic"
    kind: ClassVar[EvaluatorKind] = "deterministic"
    route_label: Route = "deterministic"

    def try_evaluate(self, metric: Metric, request: EvaluationRequest) -> Judgment | None:
        """Return a judgment if the metric can decide deterministically, else ``None``."""
        started = time.perf_counter()
        outcome = metric.check(request)
        if outcome is None:
            return None
        passed = outcome.score >= metric.pass_threshold
        return Judgment(
            evaluator=self.name,
            evaluator_kind=self.kind,
            score=outcome.score,
            confidence=1.0,
            pass_probability=1.0 if passed else 0.0,
            explanation=outcome.explanation,
            latency_ms=(time.perf_counter() - started) * 1000,
            cost_source="none",
            details=outcome.details,
        )

    async def evaluate(
        self, metric: Metric, request: EvaluationRequest, rubric: Rubric | None = None
    ) -> Judgment:
        judgment = self.try_evaluate(metric, request)
        if judgment is None:
            return Judgment(
                evaluator=self.name,
                evaluator_kind=self.kind,
                error=f"{metric.display_name} cannot be decided deterministically for this case",
            )
        return judgment

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind}
