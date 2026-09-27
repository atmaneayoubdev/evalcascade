"""The System One → System Two evaluation cascade.

For each metric of a request:

1. **Deterministic.** If the policy allows it (or the metric is fully deterministic) run the
   metric's ``check()``. A decided outcome is final: free, instant, confidence 1.0.
2. **Primary (System One).** Otherwise build the metric's rubric and send it to the primary
   evaluator (Jev by default). All primary-routed metrics of the request are submitted
   together so backends can batch them (Jev answers them in one Decisions call).
   Rubrics flagged ``requires_reasoning`` go straight to the fallback judge when
   ``route_reasoning_to_fallback`` is on.
3. **Escalation (System Two).** If the primary judgment's confidence is below the metric's
   ``escalate_below`` threshold — or the primary failed and ``escalate_on_error`` is on — the
   same rubric is sent to the fallback evaluator (a generative LLM judge).
4. **Record.** Both judgments are kept on the :class:`MetricResult` with the route taken,
   the escalation reason, and combined latency and cost.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from evalcascade.core.evaluator import EvalItem, Evaluator
from evalcascade.core.metric import Metric
from evalcascade.core.policy import EvaluationPolicy, ResolvedPolicy
from evalcascade.core.results import (
    EscalationReason,
    EvaluationResult,
    Judgment,
    MetricResult,
    MetricStatus,
    Route,
)
from evalcascade.core.rubric import Rubric
from evalcascade.core.types import EvaluationRequest
from evalcascade.evaluators.registry import EvaluatorRegistry
from evalcascade.redaction import get_logger, redact

logger = get_logger("evalcascade.runtime")


@dataclass
class _Slot:
    metric: Metric
    policy: ResolvedPolicy
    rubric: Rubric | None = None
    first: str | None = None
    direct_reason: EscalationReason | None = None
    judgments: list[Judgment] = field(default_factory=list)
    labels: list[Route] = field(default_factory=list)
    escalation_reason: EscalationReason | None = None
    result: MetricResult | None = None


class CascadeRuntime:
    """Evaluates a set of metrics on one request according to an :class:`EvaluationPolicy`."""

    def __init__(self, registry: EvaluatorRegistry, policy: EvaluationPolicy) -> None:
        self.registry = registry
        self.policy = policy

    async def evaluate(self, metrics: Sequence[Metric], request: EvaluationRequest) -> EvaluationResult:
        started = time.perf_counter()
        slots = [self._prepare(metric, request) for metric in metrics]
        pending = [s for s in slots if s.result is None]

        await self._run_stage(pending, request, lambda s: s.first)

        escalations = []
        for slot in pending:
            reason = self._escalation_reason(slot)
            if reason is not None:
                slot.escalation_reason = reason
                escalations.append(slot)
        await self._run_stage(escalations, request, lambda s: s.policy.fallback)

        for slot in pending:
            slot.result = self._finalize(slot)
        results = [s.result for s in slots if s.result is not None]
        return _case_result(request, results, [s.metric for s in slots], started)

    # -- stage 0: deterministic + routing ------------------------------------------------

    def _prepare(self, metric: Metric, request: EvaluationRequest) -> _Slot:
        policy = self.policy.resolve(metric)
        slot = _Slot(metric=metric, policy=policy)
        missing = metric.missing_fields(request)
        if missing:
            slot.result = _terminal(metric, "skipped", f"missing required field(s): {', '.join(missing)}")
            return slot

        deterministic_tried = False
        try:
            if policy.deterministic_first or metric.deterministic_support == "full":
                deterministic_tried = True
                judgment = self.registry.deterministic.try_evaluate(metric, request)
                if judgment is not None:
                    slot.judgments, slot.labels = [judgment], ["deterministic"]
                    slot.result = self._finalize(slot)
                    return slot
            rubric = metric.rubric(request)
            if rubric is None and not deterministic_tried:
                judgment = self.registry.deterministic.try_evaluate(metric, request)
                if judgment is not None:
                    slot.judgments, slot.labels = [judgment], ["deterministic"]
                    slot.result = self._finalize(slot)
                    return slot
        except Exception as exc:
            logger.debug("metric %s failed while preparing", metric.key, exc_info=True)
            slot.result = _terminal(metric, "error", f"{type(exc).__name__}: {exc}")
            return slot

        if rubric is None:
            slot.result = _terminal(metric, "skipped", metric.not_applicable_reason(request))
            return slot
        slot.rubric = rubric

        if rubric.requires_reasoning and policy.route_reasoning_to_fallback and policy.fallback:
            slot.first, slot.direct_reason = policy.fallback, "requires_reasoning"
        elif policy.primary:
            slot.first = policy.primary
        elif policy.fallback:
            slot.first = policy.fallback
        else:
            slot.result = _terminal(
                metric, "skipped", "needs semantic judgment but the policy is deterministic-only"
            )
        return slot

    # -- stages 1 and 2: semantic evaluators ------------------------------------------------

    async def _run_stage(
        self,
        slots: Sequence[_Slot],
        request: EvaluationRequest,
        pick: Callable[[_Slot], str | None],
    ) -> None:
        groups: dict[str, list[_Slot]] = defaultdict(list)
        for slot in slots:
            name = pick(slot)
            if name:
                groups[name].append(slot)
        await asyncio.gather(*(self._run_group(name, group, request) for name, group in groups.items()))

    async def _run_group(self, name: str, slots: list[_Slot], request: EvaluationRequest) -> None:
        try:
            evaluator: Evaluator = self.registry.get(name)
        except Exception as exc:
            for slot in slots:
                slot.judgments.append(_error_judgment(name, str(exc)))
                slot.labels.append("none")
            return
        items = [EvalItem(s.metric, request, s.rubric) for s in slots if s.rubric is not None]
        try:
            judgments = await evaluator.evaluate_batch(items)
        except Exception as exc:  # a misbehaving custom evaluator must not sink the run
            logger.debug("evaluator %s raised", name, exc_info=True)
            judgments = [_error_judgment(name, f"{type(exc).__name__}: {exc}") for _ in items]
        for slot, judgment in zip(slots, judgments, strict=True):
            slot.judgments.append(judgment)
            slot.labels.append(evaluator.route_label)

    def _escalation_reason(self, slot: _Slot) -> EscalationReason | None:
        if slot.direct_reason is not None or not slot.judgments:
            return None
        fallback = slot.policy.fallback
        if not fallback or fallback == slot.first:
            return None
        judgment = slot.judgments[-1]
        if judgment.error is not None:
            return "primary_error" if slot.policy.escalate_on_error else None
        if judgment.confidence is None or judgment.confidence < slot.policy.escalate_below:
            return "low_confidence"
        return None

    # -- stage 3: results ---------------------------------------------------------------------

    def _finalize(self, slot: _Slot) -> MetricResult:
        metric = slot.metric
        judgments = slot.judgments
        primary = judgments[0]
        used, used_label = judgments[-1], slot.labels[-1]
        message: str | None = None
        escalated = slot.escalation_reason is not None
        if escalated and used.error is not None and primary.ok:
            used, used_label = primary, slot.labels[0]
            message = f"fallback failed ({used_label} judgment kept): {judgments[-1].error}"

        route: Route
        if escalated and used is not primary:
            route = "jev_to_llm"
        else:
            route = used_label

        decision_made = slot.direct_reason is None and slot.policy.fallback is not None and (
            slot.first is not None and slot.first != slot.policy.fallback
        )
        common = {
            "metric": metric.key,
            "display_name": metric.display_name,
            "category": metric.category,
            "threshold": metric.pass_threshold,
            "route": route,
            "final_evaluator": used.evaluator,
            "escalated": escalated,
            "escalation_reason": slot.escalation_reason or slot.direct_reason,
            "escalate_below": slot.policy.escalate_below if decision_made else None,
            "judgments": judgments,
            "latency_ms": sum(j.latency_ms for j in judgments),
            "cost_usd": sum(j.cost_usd for j in judgments),
        }
        if used.error is not None or used.score is None:
            return MetricResult(
                status="error",
                message=used.error or "evaluator returned no score",
                confidence=used.confidence,
                **common,  # type: ignore[arg-type]
            )
        return MetricResult(
            status="ok",
            score=used.score,
            passed=used.score >= metric.pass_threshold,
            confidence=used.confidence,
            explanation=used.explanation,
            details=used.details,
            message=message,
            **common,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _terminal(metric: Metric, status: MetricStatus, message: str) -> MetricResult:
    return MetricResult(
        metric=metric.key,
        display_name=metric.display_name,
        category=metric.category,
        status=status,
        threshold=metric.pass_threshold,
        route="none",
        message=redact(message),
    )


def _error_judgment(name: str, message: str) -> Judgment:
    return Judgment(evaluator=name, evaluator_kind="llm_judge", error=redact(message))


def _case_result(
    request: EvaluationRequest,
    results: list[MetricResult],
    metrics: list[Metric],
    started: float,
) -> EvaluationResult:
    weights = {m.key: m.weight for m in metrics}
    scored = [r for r in results if r.status == "ok" and r.score is not None]
    total_weight = sum(weights[r.metric] for r in scored)
    overall = (
        sum((r.score or 0.0) * weights[r.metric] for r in scored) / total_weight
        if scored and total_weight > 0
        else None
    )
    return EvaluationResult(
        case_id=request.id,
        overall_score=overall,
        passed=all(bool(r.passed) for r in scored) if scored else None,
        metrics=results,
        latency_ms=(time.perf_counter() - started) * 1000,
        cost_usd=sum(r.cost_usd for r in results),
        escalations=sum(1 for r in results if r.escalated),
    )
