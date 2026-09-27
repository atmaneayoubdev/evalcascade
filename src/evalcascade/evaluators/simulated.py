"""Simulated evaluator — **demonstration data only**.

Produces deterministic pseudo-random answers (seeded by the state and question) so the
dashboard and tutorials work without API keys. Judgments are tagged
``evaluator_kind="simulated"`` and experiments that use it are stored with ``is_demo=True``.
Never use it to draw conclusions about a real system.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, ClassVar, Literal

from evalcascade.core.evaluator import RawAnswers, SemanticEvaluator
from evalcascade.core.results import EvaluatorKind, Route
from evalcascade.core.rubric import (
    Answer,
    BinaryQuestion,
    ChoiceQuestion,
    Rubric,
    answer_binary,
    answer_choice,
    answer_score,
)
from evalcascade.core.types import Usage


class _Rng:
    """Tiny deterministic generator (sha256 counter mode) — reproducible across platforms."""

    def __init__(self, *parts: str) -> None:
        self._seed = "\x1f".join(parts).encode()
        self._counter = 0

    def random(self) -> float:
        digest = hashlib.sha256(self._seed + self._counter.to_bytes(8, "big")).digest()
        self._counter += 1
        return int.from_bytes(digest[:8], "big") / 2**64

    def uniform(self, low: float, high: float) -> float:
        return low + (high - low) * self.random()


class SimulatedEvaluator(SemanticEvaluator):
    """Seeded fake judge for demos and offline tutorials."""

    kind: ClassVar[EvaluatorKind] = "simulated"

    def __init__(
        self,
        name: str = "simulated",
        *,
        role: Literal["jev", "llm"] = "jev",
        seed: str = "evalcascade-demo",
        quality: float = 0.8,
        uncertain_rate: float = 0.2,
        latency_ms: tuple[float, float] = (60.0, 180.0),
        cost_per_call: float = 0.00002,
    ) -> None:
        self.name = name
        self.role = role
        self.route_label: Route = "jev" if role == "jev" else "llm"
        self.seed = seed
        self.quality = quality
        self.uncertain_rate = uncertain_rate
        self.latency_range = latency_ms
        self.cost_per_call = cost_per_call

    @property
    def model_name(self) -> str | None:
        return f"simulated/{self.role}-demo"

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind, "role": self.role, "model": self.model_name, "demo": True}

    async def answer(self, rubric: Rubric) -> RawAnswers:
        state_key = json.dumps(rubric.state, sort_keys=True, default=str)
        rng = _Rng(self.seed, self.role, state_key)
        answers: dict[str, Answer] = {}
        for q in rubric.questions:
            r = _Rng(self.seed, self.role, state_key, q.id)
            good = r.random() < self.quality
            uncertain = self.role == "jev" and r.random() < self.uncertain_rate
            if isinstance(q, BinaryQuestion):
                p_good = r.uniform(0.38, 0.62) if uncertain else (r.uniform(0.86, 0.99) if good else r.uniform(0.02, 0.25))
                p_true = p_good if q.true_is_good else 1.0 - p_good
                answers[q.id] = answer_binary(q, p_true, explanation=_explain(self.role))
            elif isinstance(q, ChoiceQuestion):
                ranked = sorted(q.options, key=lambda k: q.option_scores[k], reverse=True)
                pick = ranked[0] if good else ranked[min(len(ranked) - 1, 1 + int(r.random() * (len(ranked) - 1)))]
                top = r.uniform(0.45, 0.65) if uncertain else r.uniform(0.85, 0.98)
                rest = (1.0 - top) / max(1, len(ranked) - 1)
                probs = {k: (top if k == pick else rest) for k in q.options}
                answers[q.id] = answer_choice(
                    q, pick, probabilities=probs, confidence=top if self.role == "jev" else None,
                    confidence_source="provider", explanation=_explain(self.role),
                )
            else:
                top_level = q.max_level if good else int(r.random() * q.max_level)
                peak = r.uniform(0.45, 0.65) if uncertain else r.uniform(0.84, 0.97)
                spill = 1.0 - peak
                probs = {str(i): 0.0 for i in range(len(q.levels))}
                probs[str(top_level)] = peak
                neighbour = top_level - 1 if top_level > 0 else top_level + 1
                probs[str(neighbour)] += spill
                level = sum(int(k) * p for k, p in probs.items())
                answers[q.id] = answer_score(
                    q, level, probabilities=probs, confidence=peak if self.role == "jev" else None,
                    confidence_source="provider", explanation=_explain(self.role),
                )
            if self.role == "llm":
                a = answers[q.id]
                answers[q.id] = a.model_copy(
                    update={"confidence": r.uniform(0.8, 0.97), "confidence_source": "self_reported"}
                )
        latency = rng.uniform(*self.latency_range)
        tokens = 120 + len(state_key) // 4
        return RawAnswers(
            answers=answers,
            model=self.model_name,
            latency_ms=latency,
            usage=Usage(input_tokens=tokens, output_tokens=0 if self.role == "jev" else 90),
            cost_usd=self.cost_per_call,
            cost_source="estimated",
            request_id=None,
            explanation="Simulated judgment (demonstration data).",
            details={"simulated": True},
        )


def _explain(role: str) -> str:
    return f"Simulated {'System One' if role == 'jev' else 'LLM judge'} answer (demonstration data)."
