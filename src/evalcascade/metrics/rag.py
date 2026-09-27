"""Retrieval-augmented generation (RAG) metrics.

Context passages are referred to 1-indexed: citation ``[1]`` refers to ``context[0]``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from evalcascade.core.metric import Aggregation, DeterministicOutcome, Metric
from evalcascade.core.rubric import Answer, BinaryQuestion, Rubric, ScoreQuestion
from evalcascade.core.types import EvaluationRequest
from evalcascade.metrics._text import (
    find_citations,
    numeric_citations,
    split_sentences,
    strip_citations,
    truncate,
)
from evalcascade.metrics.general import base_state


def context_state(request: EvaluationRequest, *, max_passages: int, max_chars: int) -> list[str]:
    return [truncate(p, max_chars) or "" for p in request.context[:max_passages]]


class Groundedness(Metric):
    """Whether the response's claims are supported by the retrieved context (faithfulness)."""

    name = "groundedness"
    display_name = "Groundedness"
    category = "rag"
    description = (
        "Whether every factual claim in the response is supported by the retrieved context. "
        "Claims that are true but absent from the context count as unsupported."
    )
    primitives = ("score", "binary")
    deterministic_support = "none"
    required_fields = ("output", "context")
    optional_fields = ("input",)
    default_threshold = 0.6

    granularity: Literal["response", "sentence"] = Field(
        default="response",
        description="'response' = one holistic 4-level judgment; 'sentence' = one yes/no "
        "judgment per sentence (score = share of supported sentences).",
    )
    max_sentences: int = Field(default=12, ge=1, le=40)
    max_passages: int = Field(default=10, ge=1, le=50)
    max_passage_chars: int = Field(default=3000, ge=200)

    def rubric(self, request: EvaluationRequest) -> Rubric:
        state = base_state(request)
        state["retrieved_context"] = context_state(
            request, max_passages=self.max_passages, max_chars=self.max_passage_chars
        )
        if self.granularity == "sentence":
            sentences = split_sentences(request.output or "")[: self.max_sentences] or [request.output or ""]
            state["claims"] = {f"s{i + 1}": strip_citations(s) for i, s in enumerate(sentences)}
            questions = [
                BinaryQuestion(
                    id=f"s{i + 1}",
                    instructions=(
                        f"Is the claim in `claims.s{i + 1}` supported by `retrieved_context`? "
                        "It is supported only if the context states it or it follows directly "
                        "from the context. Sentences without factual content (greetings, "
                        "hedges, saying the information is unavailable) count as supported."
                    ),
                    true="Supported by the retrieved context.",
                    false="Not supported: absent from, or contradicted by, the retrieved context.",
                )
                for i in range(len(sentences))
            ]
            return Rubric(questions=questions, state=state, aux={"sentences": sentences})
        return Rubric(
            questions=[
                ScoreQuestion(
                    id="groundedness",
                    instructions=(
                        "Are the factual claims in `response` supported by `retrieved_context`? "
                        "A claim is supported only if the context states it or it follows "
                        "directly from the context; claims that are true but absent from the "
                        "context are unsupported. Ignore greetings, hedges and statements that "
                        "the information is unavailable."
                    ),
                    levels=[
                        "Ungrounded: the main claims are contradicted by or absent from the context.",
                        "Weakly grounded: some claims are supported, but important claims are "
                        "unsupported or contradicted.",
                        "Mostly grounded: nearly all claims are supported; a minor detail goes "
                        "beyond the context.",
                        "Fully grounded: every factual claim is supported by the context.",
                    ],
                )
            ],
            state=state,
        )

    def aggregate(self, answers: dict[str, Answer], rubric: Rubric) -> Aggregation:
        base = super().aggregate(answers, rubric)
        if self.granularity != "sentence":
            return base
        sentences: list[str] = rubric.aux["sentences"]
        per = [
            {"sentence": truncate(s, 200), "supported": round(answers[f"s{i + 1}"].score, 4)}
            for i, s in enumerate(sentences)
        ]
        unsupported = [p["sentence"] for p in per if float(p["supported"] or 0) < 0.5]  # type: ignore[arg-type]
        return base.model_copy(update={"details": {"sentences": per, "unsupported": unsupported}})


class ContextRelevance(Metric):
    """Share of retrieved passages that are relevant to the question (context precision)."""

    name = "context_relevance"
    display_name = "Context Relevance"
    category = "rag"
    description = (
        "Judges each retrieved passage for relevance to the user's question; the score is "
        "the mean relevance probability (retrieval precision)."
    )
    primitives = ("binary",)
    deterministic_support = "none"
    required_fields = ("input", "context")
    default_threshold = 0.5

    max_passages: int = Field(default=10, ge=1, le=30)
    max_passage_chars: int = Field(default=2000, ge=200)

    def rubric(self, request: EvaluationRequest) -> Rubric:
        passages = context_state(request, max_passages=self.max_passages, max_chars=self.max_passage_chars)
        state: dict[str, Any] = {
            "user_input": truncate(request.input, 6000),
            "passages": {f"p{i + 1}": p for i, p in enumerate(passages)},
        }
        questions = [
            BinaryQuestion(
                id=f"p{i + 1}",
                instructions=(
                    f"Does `passages.p{i + 1}` contain information that helps answer `user_input`?"
                ),
                true="Relevant: the passage contains information useful for answering the question.",
                false="Irrelevant: the passage is off-topic or only superficially related.",
            )
            for i in range(len(passages))
        ]
        return Rubric(questions=questions, state=state, aux={"total_passages": len(request.context)})

    def aggregate(self, answers: dict[str, Answer], rubric: Rubric) -> Aggregation:
        base = super().aggregate(answers, rubric)
        per = [{"passage": i + 1, "relevance": round(answers[q.id].score, 4)} for i, q in enumerate(rubric.questions)]
        details: dict[str, Any] = {
            "passages": per,
            "relevant": sum(1 for p in per if p["relevance"] >= 0.5),
            "judged": len(per),
        }
        if rubric.aux.get("total_passages", 0) > len(per):
            details["not_judged"] = rubric.aux["total_passages"] - len(per)
        return base.model_copy(update={"details": details})


class CitationPresence(Metric):
    """Whether the response cites its sources (deterministic)."""

    name = "citation_presence"
    display_name = "Citation Presence"
    category = "rag"
    description = (
        "Deterministically detects citation markers: [1], [doc2], (source: ...), footnotes "
        "and URLs. Score = min(1, citations / min_citations)."
    )
    primitives = ()
    deterministic_support = "full"
    required_fields = ("output",)
    default_threshold = 1.0

    min_citations: int = Field(default=1, ge=1)

    def check(self, request: EvaluationRequest) -> DeterministicOutcome:
        citations = find_citations(request.output or "")
        score = min(1.0, len(citations) / self.min_citations)
        return DeterministicOutcome(
            score=score,
            explanation=f"Found {len(citations)} citation marker(s); {self.min_citations} required.",
            details={"citations": citations[:20], "count": len(citations)},
        )


class CitationCorrectness(Metric):
    """Whether numeric citations point to passages that actually support the cited claim."""

    name = "citation_correctness"
    display_name = "Citation Correctness"
    category = "rag"
    description = (
        "For each sentence citing [n], checks deterministically that passage n exists, then "
        "judges whether that passage supports the sentence. Score = share of correct citations."
    )
    primitives = ("binary",)
    deterministic_support = "partial"
    required_fields = ("output", "context")
    default_threshold = 0.6

    max_citations: int = Field(default=12, ge=1, le=40)
    max_passage_chars: int = Field(default=2000, ge=200)

    def _pairs(self, request: EvaluationRequest) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
        valid: list[tuple[str, int]] = []
        invalid: list[tuple[str, int]] = []
        for sentence in split_sentences(request.output or ""):
            for index in dict.fromkeys(numeric_citations(sentence)):
                pair = (strip_citations(sentence), index)
                (valid if 1 <= index <= len(request.context) else invalid).append(pair)
        return valid[: self.max_citations], invalid

    def not_applicable_reason(self, request: EvaluationRequest) -> str:
        return "no numeric citations like [1] found in the response"

    def check(self, request: EvaluationRequest) -> DeterministicOutcome | None:
        valid, invalid = self._pairs(request)
        if invalid and not valid:
            return DeterministicOutcome(
                score=0.0,
                explanation=f"All {len(invalid)} citation(s) point to passages that do not exist.",
                details={"invalid": [i for _, i in invalid], "passages": len(request.context)},
            )
        return None

    def rubric(self, request: EvaluationRequest) -> Rubric | None:
        valid, invalid = self._pairs(request)
        if not valid:
            return None
        state = {
            "citations": {
                f"c{k + 1}": {
                    "claim": truncate(claim, 1000),
                    "passage": truncate(request.context[index - 1], self.max_passage_chars),
                }
                for k, (claim, index) in enumerate(valid)
            }
        }
        questions = [
            BinaryQuestion(
                id=f"c{k + 1}",
                instructions=f"Does `citations.c{k + 1}.passage` support `citations.c{k + 1}.claim`?",
                true="The cited passage supports the claim.",
                false="The cited passage does not support the claim (irrelevant or contradicting).",
            )
            for k in range(len(valid))
        ]
        return Rubric(
            questions=questions,
            state=state,
            aux={"valid": valid, "invalid": invalid},
        )

    def aggregate(self, answers: dict[str, Answer], rubric: Rubric) -> Aggregation:
        valid: list[tuple[str, int]] = rubric.aux["valid"]
        invalid: list[tuple[str, int]] = rubric.aux["invalid"]
        supported = [answers[f"c{k + 1}"].score for k in range(len(valid))]
        total = len(valid) + len(invalid)
        score = sum(supported) / total if total else 0.0
        return Aggregation(
            score=score,
            explanation=f"{sum(1 for s in supported if s >= 0.5)}/{total} citations are correct.",
            details={
                "citations": [
                    {"passage": index, "claim": truncate(claim, 160), "supported": round(s, 4)}
                    for (claim, index), s in zip(valid, supported, strict=True)
                ],
                "invalid": [index for _, index in invalid],
            },
        )
