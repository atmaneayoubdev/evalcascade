"""Jev (TypeSafe System One) evaluator.

Maps provider-independent rubric questions onto Jev's primitives:

=================  ===========  =====================================================
Rubric question    Jev type     Confidence
=================  ===========  =====================================================
BinaryQuestion     ``noul``     derived: ``max(p, 1 - p)`` (Jev reports only P(true))
ChoiceQuestion     ``choice``   Jev's ``confidence`` (fallback: max probability)
ScoreQuestion      ``score``    Jev's ``confidence`` (fallback: max level probability)
=================  ===========  =====================================================

**Batching.** Jev answers many questions about one state in a single call. When ``batch`` is
enabled, every Jev-routed metric of a case whose states are compatible (no conflicting keys)
is sent in one Decisions request: one round trip instead of N. The shared call's latency is
reported on each metric; its cost is apportioned by question count so totals stay exact.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, ClassVar

from pydantic import SecretStr

from evalcascade.config import DEFAULT_JEV_MODEL, OPENROUTER_API_BASE, JevSettings, Settings
from evalcascade.core.evaluator import EvalItem, RawAnswers, SemanticEvaluator
from evalcascade.core.results import CostSource, EvaluatorKind, Judgment, Route
from evalcascade.core.rubric import (
    Answer,
    BinaryQuestion,
    ChoiceQuestion,
    Rubric,
    ScoreQuestion,
    answer_binary,
    answer_choice,
    answer_score,
)
from evalcascade.core.types import Usage
from evalcascade.errors import EvalCascadeError, ResponseValidationError
from evalcascade.providers.jev import (
    ChoiceAnswer,
    DecisionAnswer,
    DecisionResult,
    JevClient,
    NoulAnswer,
    ScoreAnswer,
)

AnyQuestion = BinaryQuestion | ChoiceQuestion | ScoreQuestion


def to_decision_question(question: AnyQuestion) -> dict[str, Any]:
    """Translate a rubric question into a Decisions API question."""
    if isinstance(question, BinaryQuestion):
        return {
            "type": "noul",
            "instructions": question.instructions,
            "criteria": {"true": question.true, "false": question.false},
        }
    if isinstance(question, ChoiceQuestion):
        return {"type": "choice", "instructions": question.instructions, "criteria": dict(question.options)}
    return {"type": "score", "instructions": question.instructions, "criteria": list(question.levels)}


def parse_decision_answer(question: AnyQuestion, answer: DecisionAnswer) -> Answer:
    """Translate a Decisions answer into a normalized :class:`Answer`."""
    if isinstance(question, BinaryQuestion):
        if not isinstance(answer, NoulAnswer):
            raise ResponseValidationError(
                f"expected a noul answer for {question.id!r}, got {answer.type!r}", provider="jev"
            )
        return answer_binary(question, answer.noul)
    if isinstance(question, ChoiceQuestion):
        if not isinstance(answer, ChoiceAnswer):
            raise ResponseValidationError(
                f"expected a choice answer for {question.id!r}, got {answer.type!r}", provider="jev"
            )
        if answer.choice not in question.options:
            raise ResponseValidationError(
                f"Jev chose unknown option {answer.choice!r} for {question.id!r}", provider="jev"
            )
        return answer_choice(
            question,
            answer.choice,
            probabilities=answer.probabilities,
            confidence=answer.confidence,
            confidence_source="provider",
        )
    if not isinstance(answer, ScoreAnswer):
        raise ResponseValidationError(
            f"expected a score answer for {question.id!r}, got {answer.type!r}", provider="jev"
        )
    return answer_score(
        question,
        answer.score,
        probabilities=answer.probabilities,
        confidence=answer.confidence,
        confidence_source="provider",
    )


class JevEvaluator(SemanticEvaluator):
    """Answers rubrics with Jev via OpenRouter's Decisions API."""

    kind: ClassVar[EvaluatorKind] = "system_one"
    route_label: Route = "jev"

    def __init__(
        self,
        client: JevClient | None = None,
        *,
        api_key: SecretStr | str | None = None,
        model: str = DEFAULT_JEV_MODEL,
        surface: str = "decisions",
        base_url: str = OPENROUTER_API_BASE,
        timeout_s: float = 30.0,
        max_retries: int = 3,
        batch: bool = True,
        max_questions_per_request: int = 32,
        name: str = "jev",
    ) -> None:
        self.name = name
        self.client = client or JevClient(
            api_key,
            model=model,
            surface=surface,  # type: ignore[arg-type]
            base_url=base_url,
            timeout_s=timeout_s,
            max_retries=max_retries,
        )
        self.batch = batch
        self.max_questions_per_request = max_questions_per_request
        self._timeout_s = timeout_s
        self._max_retries = max_retries

    @classmethod
    def from_settings(cls, settings: Settings, *, name: str = "jev") -> JevEvaluator:
        jev: JevSettings = settings.jev
        client = JevClient(
            settings.openrouter_api_key,
            model=jev.model,
            surface=jev.surface,
            base_url=jev.base_url,
            timeout_s=jev.timeout_s,
            max_retries=jev.max_retries,
            max_concurrency=jev.max_concurrency,
            app_url=settings.app_url,
            app_title=settings.app_title,
        )
        evaluator = cls(
            client,
            batch=jev.batch,
            max_questions_per_request=jev.max_questions_per_request,
            name=name,
        )
        evaluator._timeout_s, evaluator._max_retries = jev.timeout_s, jev.max_retries
        return evaluator

    @property
    def model_name(self) -> str | None:
        return self.client.model

    def available(self) -> tuple[bool, str | None]:
        if not self.client.configured:
            return False, "OPENROUTER_API_KEY is not set (required for the Jev evaluator)"
        return True, None

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "model": self.client.model,
            "surface": self.client.surface,
            "endpoint": self.client.endpoint,
            "batch": self.batch,
            "timeout_s": self._timeout_s,
            "max_retries": self._max_retries,
        }

    async def aclose(self) -> None:
        await self.client.aclose()

    # -- single rubric ---------------------------------------------------------------

    async def answer(self, rubric: Rubric) -> RawAnswers:
        questions = {q.id: to_decision_question(q) for q in rubric.questions}
        result = await self.client.decide(rubric.state, questions)
        answers = self._parse(rubric, result, {q.id: q.id for q in rubric.questions})
        cost, source = _cost(result)
        return RawAnswers(
            answers=answers,
            model=result.response.model,
            latency_ms=result.latency_ms,
            usage=Usage(
                input_tokens=result.response.usage.input_tokens,
                output_tokens=result.response.usage.output_tokens,
            ),
            cost_usd=cost,
            cost_source=source,
            request_id=result.response.id,
            details={"attempts": result.attempts, "provider": result.response.provider},
        )

    @staticmethod
    def _parse(rubric: Rubric, result: DecisionResult, keys: dict[str, str]) -> dict[str, Answer]:
        answers: dict[str, Answer] = {}
        for q in rubric.questions:
            raw = result.response.answers.get(keys[q.id])
            if raw is not None:
                answers[q.id] = parse_decision_answer(q, raw)
        return answers

    # -- batching ----------------------------------------------------------------------

    async def evaluate_batch(self, items: Sequence[EvalItem]) -> list[Judgment]:
        if not self.batch or len(items) <= 1:
            return await super().evaluate_batch(items)
        groups = plan_batches(items, self.max_questions_per_request)
        results: list[Judgment | None] = [None] * len(items)

        async def run(group: list[int]) -> None:
            if len(group) == 1:
                i = group[0]
                results[i] = await self.evaluate(items[i].metric, items[i].request, items[i].rubric)
                return
            for i, judgment in zip(group, await self._evaluate_group([items[i] for i in group]), strict=True):
                results[i] = judgment

        await asyncio.gather(*(run(g) for g in groups))
        missing = [i for i, r in enumerate(results) if r is None]
        if missing:  # pragma: no cover - every index belongs to exactly one group
            raise RuntimeError(f"batch planning dropped items {missing}")
        return [r for r in results if r is not None]

    async def _evaluate_group(self, items: list[EvalItem]) -> list[Judgment]:
        state: dict[str, Any] = {}
        questions: dict[str, dict[str, Any]] = {}
        keymaps: list[dict[str, str]] = []
        for item in items:
            state.update(item.rubric.state)
            keymap = {}
            for q in item.rubric.questions:
                key = f"{item.metric.key}__{q.id}"
                while key in questions:
                    key += "_"
                questions[key] = to_decision_question(q)
                keymap[q.id] = key
            keymaps.append(keymap)
        try:
            result = await self.client.decide(state, questions)
        except EvalCascadeError as exc:
            return [self.error_judgment(str(exc)) for _ in items]

        total_cost, source = _cost(result)
        total_questions = len(questions)
        usage = result.response.usage
        judgments: list[Judgment] = []
        batched_with = [i.metric.key for i in items]
        for item, keymap in zip(items, keymaps, strict=True):
            share = len(item.rubric.questions) / total_questions
            try:
                answers = self._parse(item.rubric, result, keymap)
            except EvalCascadeError as exc:
                judgments.append(self.error_judgment(str(exc), latency_ms=result.latency_ms))
                continue
            raw = RawAnswers(
                answers=answers,
                model=result.response.model,
                latency_ms=result.latency_ms,
                usage=Usage(
                    input_tokens=round(usage.input_tokens * share),
                    output_tokens=round(usage.output_tokens * share),
                ),
                cost_usd=total_cost * share,
                cost_source=source,
                request_id=result.response.id,
                details={
                    "attempts": result.attempts,
                    "provider": result.response.provider,
                    "batched_with": [k for k in batched_with if k != item.metric.key],
                    "batch_questions": total_questions,
                },
            )
            judgments.append(self.to_judgment(item.metric, item.rubric, raw))
        return judgments


def plan_batches(items: Sequence[EvalItem], max_questions: int) -> list[list[int]]:
    """Group item indices whose requests are identical and whose states can be merged."""
    groups: list[tuple[int, dict[str, Any], int, list[int]]] = []  # (request id, state, n_q, idx)
    for index, item in enumerate(items):
        n_q = len(item.rubric.questions)
        placed = False
        for g, (req_id, state, count, members) in enumerate(groups):
            if req_id != id(item.request) or count + n_q > max_questions:
                continue
            if any(k in state and state[k] != v for k, v in item.rubric.state.items()):
                continue
            merged = {**state, **item.rubric.state}
            groups[g] = (req_id, merged, count + n_q, [*members, index])
            placed = True
            break
        if not placed:
            groups.append((id(item.request), dict(item.rubric.state), n_q, [index]))
    return [members for *_, members in groups]


def _cost(result: DecisionResult) -> tuple[float, CostSource]:
    cost = result.response.usage.cost
    if cost is None:
        return 0.0, "unknown"
    return float(cost), "provider"
