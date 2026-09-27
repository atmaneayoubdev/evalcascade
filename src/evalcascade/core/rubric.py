"""Provider-independent judgment primitives.

A metric that needs semantic judgment describes *what* it wants judged as a :class:`Rubric`:
a *state* (the data under evaluation) plus one or more typed questions:

* :class:`BinaryQuestion` — does a condition hold? (Jev ``noul``)
* :class:`ChoiceQuestion` — which of these options applies? (Jev ``choice``)
* :class:`ScoreQuestion` — where on this ordered scale does it fall? (Jev ``score``)

Any evaluator backend — Jev, a generative LLM judge, a simulator — answers the same
questions and returns :class:`Answer` objects. The helpers at the bottom of this module
convert raw provider outputs into answers with a normalized ``score`` in ``[0, 1]`` so every
backend is scored identically.
"""

from __future__ import annotations

import math
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

QuestionKind = Literal["binary", "choice", "score"]
ConfidenceSource = Literal["provider", "derived", "self_reported", "deterministic"]

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
MAX_SCORE_LEVELS = 10  # Jev supports at most 10 ordered levels


def _check_id(value: str) -> str:
    if not _ID_RE.match(value):
        raise ValueError(
            f"invalid question id {value!r}: use letters, digits and underscores, "
            "starting with a letter (max 64 chars)"
        )
    return value


class _QuestionBase(BaseModel):
    id: str
    instructions: str = Field(min_length=1)
    weight: float = Field(default=1.0, gt=0)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        return _check_id(value)


class BinaryQuestion(_QuestionBase):
    """A yes/no question. ``true_is_good`` says which answer is the desirable outcome."""

    kind: Literal["binary"] = "binary"
    true: str = "The statement holds."
    false: str = "The statement does not hold."
    true_is_good: bool = True

    def score_of(self, p_true: float) -> float:
        return p_true if self.true_is_good else 1.0 - p_true


class ChoiceQuestion(_QuestionBase):
    """Pick one option. Each option maps to a normalized score via ``option_scores``."""

    kind: Literal["choice"] = "choice"
    options: dict[str, str]
    option_scores: dict[str, float]

    @model_validator(mode="after")
    def _validate_options(self) -> ChoiceQuestion:
        if len(self.options) < 2:
            raise ValueError("a choice question needs at least 2 options")
        for key in self.options:
            _check_id(key)
        if set(self.options) != set(self.option_scores):
            raise ValueError("option_scores must define a score for exactly the declared options")
        for key, value in self.option_scores.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"option score for {key!r} must be within [0, 1]")
        return self


class ScoreQuestion(_QuestionBase):
    """An ordered scale. ``levels[0]`` is the worst outcome, ``levels[-1]`` the best."""

    kind: Literal["score"] = "score"
    levels: list[str]

    @field_validator("levels")
    @classmethod
    def _validate_levels(cls, value: list[str]) -> list[str]:
        if not 2 <= len(value) <= MAX_SCORE_LEVELS:
            raise ValueError(f"a score question needs between 2 and {MAX_SCORE_LEVELS} levels")
        return value

    @property
    def max_level(self) -> int:
        return len(self.levels) - 1

    def score_of(self, level: float) -> float:
        return _clamp(level / self.max_level)


Question = Annotated[BinaryQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="kind")]


class Rubric(BaseModel):
    """What a metric wants judged: a shared state plus typed questions."""

    questions: list[Question] = Field(min_length=1)
    state: dict[str, Any]
    requires_reasoning: bool = Field(
        default=False,
        description="Hint that the task needs deeper reasoning; the policy may route it "
        "straight to the generative judge.",
    )
    guidance: str | None = Field(
        default=None, description="Extra guidance for generative judges (not sent to Jev)."
    )
    aux: dict[str, Any] = Field(
        default_factory=dict,
        description="Data used by the metric's aggregation; never sent to an evaluator.",
    )

    @model_validator(mode="after")
    def _unique_ids(self) -> Rubric:
        ids = [q.id for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question ids within a rubric must be unique")
        return self

    def question(self, question_id: str) -> BinaryQuestion | ChoiceQuestion | ScoreQuestion:
        for q in self.questions:
            if q.id == question_id:
                return q
        raise KeyError(question_id)


class Answer(BaseModel):
    """A backend's answer to one question, normalized to a score in ``[0, 1]``."""

    question_id: str
    kind: QuestionKind
    value: bool | str | float
    probability: float | None = Field(default=None, description="Binary only: P(true).")
    probabilities: dict[str, float] | None = None
    confidence: float | None = None
    confidence_source: ConfidenceSource | None = None
    score: float
    explanation: str | None = None


# ---------------------------------------------------------------------------
# Normalization helpers — used by every evaluator backend
# ---------------------------------------------------------------------------


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if math.isnan(value):
        return low
    return max(low, min(high, value))


def _normalize_distribution(probabilities: dict[str, float]) -> dict[str, float]:
    cleaned = {k: _clamp(float(v)) for k, v in probabilities.items()}
    total = sum(cleaned.values())
    if total <= 0:
        return cleaned
    return {k: v / total for k, v in cleaned.items()}


def answer_binary(
    question: BinaryQuestion,
    p_true: float,
    *,
    confidence: float | None = None,
    confidence_source: ConfidenceSource = "derived",
    explanation: str | None = None,
) -> Answer:
    """Build an answer from P(true).

    When the backend does not report a confidence, it is derived as ``max(p, 1 - p)`` —
    the probability assigned to the predicted outcome.
    """
    p = _clamp(float(p_true))
    if confidence is None:
        confidence = max(p, 1.0 - p)
        confidence_source = "derived"
    return Answer(
        question_id=question.id,
        kind="binary",
        value=p >= 0.5,
        probability=p,
        probabilities={"true": p, "false": 1.0 - p},
        confidence=_clamp(confidence),
        confidence_source=confidence_source,
        score=question.score_of(p),
        explanation=explanation,
    )


def answer_choice(
    question: ChoiceQuestion,
    choice: str,
    *,
    probabilities: dict[str, float] | None = None,
    confidence: float | None = None,
    confidence_source: ConfidenceSource = "provider",
    explanation: str | None = None,
) -> Answer:
    """Build an answer for a choice question.

    With a probability distribution the score is the expected option score; otherwise it is
    the score of the selected option.
    """
    if choice not in question.options:
        raise ValueError(f"choice {choice!r} is not one of {sorted(question.options)}")
    probs = None
    if probabilities:
        probs = {k: v for k, v in _normalize_distribution(probabilities).items() if k in question.options}
    if probs:
        score = sum(p * question.option_scores[k] for k, p in probs.items())
    else:
        score = question.option_scores[choice]
    if confidence is None and probs:
        confidence = max(probs.values())
        confidence_source = "derived"
    return Answer(
        question_id=question.id,
        kind="choice",
        value=choice,
        probabilities=probs,
        confidence=None if confidence is None else _clamp(confidence),
        confidence_source=confidence_source if confidence is not None else None,
        score=_clamp(score),
        explanation=explanation,
    )


def answer_score(
    question: ScoreQuestion,
    level: float,
    *,
    probabilities: dict[str, float] | None = None,
    confidence: float | None = None,
    confidence_source: ConfidenceSource = "provider",
    explanation: str | None = None,
) -> Answer:
    """Build an answer for an ordered-scale question.

    ``level`` may be fractional (Jev returns the probability-weighted level); it is clamped to
    the scale and normalized to ``level / max_level``.
    """
    lvl = max(0.0, min(float(question.max_level), float(level)))
    probs = None
    if probabilities:
        probs = {
            k: v
            for k, v in _normalize_distribution(probabilities).items()
            if k.isdigit() and int(k) <= question.max_level
        }
    if confidence is None and probs:
        confidence = max(probs.values())
        confidence_source = "derived"
    return Answer(
        question_id=question.id,
        kind="score",
        value=lvl,
        probabilities=probs or None,
        confidence=None if confidence is None else _clamp(confidence),
        confidence_source=confidence_source if confidence is not None else None,
        score=question.score_of(lvl),
        explanation=explanation,
    )


def pass_probability(
    question: BinaryQuestion | ChoiceQuestion | ScoreQuestion, answer: Answer, threshold: float
) -> float | None:
    """Probability that the true outcome meets ``threshold`` on the normalized scale.

    Uses the answer's probability distribution when available; otherwise falls back to the
    (self-reported) confidence in the predicted outcome. Returns ``None`` if neither exists.
    """
    if isinstance(question, BinaryQuestion) and answer.probability is not None:
        return answer.score  # P(desirable outcome)
    if answer.probabilities:
        if isinstance(question, ChoiceQuestion):
            return sum(p for k, p in answer.probabilities.items() if question.option_scores[k] >= threshold)
        if isinstance(question, ScoreQuestion):
            return sum(
                p for k, p in answer.probabilities.items() if question.score_of(int(k)) >= threshold
            )
    if answer.confidence is None:
        return None
    predicted_pass = answer.score >= threshold
    return answer.confidence if predicted_pass else 1.0 - answer.confidence
