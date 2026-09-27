"""JevEvaluator: rubric <-> Decisions mapping, confidence semantics, batching, failures."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from evalcascade.core.evaluator import EvalItem
from evalcascade.core.rubric import BinaryQuestion, ChoiceQuestion, Rubric, ScoreQuestion
from evalcascade.core.types import EvaluationRequest
from evalcascade.evaluators.jev import JevEvaluator, plan_batches, to_decision_question
from evalcascade.metrics import AnswerRelevance, ContextRelevance, Groundedness, Safety
from evalcascade.providers.jev import JevClient
from tests.conftest import FAKE_KEY

URL = "https://openrouter.ai/api/alpha/decisions"


async def _no_sleep(_: float) -> None:
    return None


def evaluator(batch: bool = True) -> JevEvaluator:
    return JevEvaluator(JevClient(FAKE_KEY, sleep=_no_sleep), batch=batch)


def ok(answers: dict[str, dict[str, object]], cost: float = 0.0001) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "typesafe/jev-1.13-20260917",
            "answers": answers,
            "usage": {"input_tokens": 400, "output_tokens": 40, "cost": cost},
            "id": "gen-dec-1",
            "provider": "TypeSafe",
        },
    )


def test_question_mapping() -> None:
    assert to_decision_question(BinaryQuestion(id="b", instructions="i", true="t", false="f")) == {
        "type": "noul",
        "instructions": "i",
        "criteria": {"true": "t", "false": "f"},
    }
    assert to_decision_question(
        ChoiceQuestion(
            id="c", instructions="i", options={"x": "X", "y": "Y"}, option_scores={"x": 1, "y": 0}
        )
    ) == {
        "type": "choice",
        "instructions": "i",
        "criteria": {"x": "X", "y": "Y"},
    }
    assert to_decision_question(ScoreQuestion(id="s", instructions="i", levels=["a", "b"])) == {
        "type": "score",
        "instructions": "i",
        "criteria": ["a", "b"],
    }


@respx.mock
async def test_score_answer_normalization_and_confidence(qa_request: EvaluationRequest) -> None:
    route = respx.post(URL).mock(
        return_value=ok(
            {
                "relevance": {
                    "type": "score",
                    "score": 2.4,
                    "confidence": 0.77,
                    "probabilities": {"0": 0.0, "1": 0.1, "2": 0.4, "3": 0.5},
                }
            }
        )
    )
    j = await evaluator().evaluate(AnswerRelevance(), qa_request)
    assert j.error is None and j.evaluator == "jev" and j.evaluator_kind == "system_one"
    assert j.score == pytest.approx(0.8)
    assert (
        j.confidence == pytest.approx(0.77)
        and j.answers["relevance"].confidence_source == "provider"
    )
    # pass probability = P(level >= 0.6 * 3) = P(level 2) + P(level 3)
    assert j.pass_probability == pytest.approx(0.9)
    assert j.cost_usd == pytest.approx(0.0001) and j.cost_source == "provider"
    assert j.usage.input_tokens == 400 and j.request_id == "gen-dec-1"
    body = json.loads(route.calls.last.request.content)
    assert body["state"] == {"user_input": qa_request.input, "response": qa_request.output}
    assert body["questions"]["relevance"]["type"] == "score"


@respx.mock
async def test_noul_confidence_is_derived(qa_request: EvaluationRequest) -> None:
    respx.post(URL).mock(
        return_value=ok({"p1": {"type": "noul", "noul": 0.3}, "p2": {"type": "noul", "noul": 0.9}})
    )
    j = await evaluator().evaluate(ContextRelevance(), qa_request)
    assert j.score == pytest.approx(0.6)
    assert (
        j.answers["p1"].confidence == pytest.approx(0.7)
        and j.answers["p1"].confidence_source == "derived"
    )
    assert j.confidence == pytest.approx(0.7)  # min over questions
    assert j.details["passages"][0] == {"passage": 1, "relevance": 0.3}


@respx.mock
async def test_choice_expected_score_uses_distribution(qa_request: EvaluationRequest) -> None:
    respx.post(URL).mock(
        return_value=ok(
            {
                "category": {
                    "type": "choice",
                    "choice": "safe",
                    "confidence": 0.6,
                    "probabilities": {"safe": 0.7, "harmful_advice": 0.3},
                }
            }
        )
    )
    j = await evaluator().evaluate(Safety(), qa_request)
    assert j.score == pytest.approx(0.7)
    assert j.details["category"] == "safe"


@respx.mock
async def test_missing_answer_type_mismatch_and_unknown_choice(
    qa_request: EvaluationRequest,
) -> None:
    respx.post(URL).mock(return_value=ok({}))
    assert "missing answers" in (await evaluator().evaluate(AnswerRelevance(), qa_request)).error  # type: ignore[operator]
    respx.post(URL).mock(return_value=ok({"relevance": {"type": "noul", "noul": 0.5}}))
    assert (
        "expected a score answer"
        in (await evaluator().evaluate(AnswerRelevance(), qa_request)).error
    )  # type: ignore[operator]
    respx.post(URL).mock(return_value=ok({"category": {"type": "choice", "choice": "made_up"}}))
    assert "unknown option" in (await evaluator().evaluate(Safety(), qa_request)).error  # type: ignore[operator]


@respx.mock
async def test_provider_failure_becomes_error_judgment(qa_request: EvaluationRequest) -> None:
    respx.post(URL).mock(
        return_value=httpx.Response(
            401, json={"error": {"code": 401, "message": "No auth credentials found"}}
        )
    )
    j = await evaluator().evaluate(AnswerRelevance(), qa_request)
    assert j.score is None and "No auth credentials" in (j.error or "")


@respx.mock
async def test_batching_merges_metrics_into_one_request(qa_request: EvaluationRequest) -> None:
    route = respx.post(URL).mock(
        return_value=ok(
            {
                "answer_relevance__relevance": {"type": "score", "score": 3, "confidence": 0.9},
                "groundedness__groundedness": {"type": "score", "score": 2, "confidence": 0.8},
                "safety__category": {"type": "choice", "choice": "safe", "confidence": 0.99},
            },
            cost=0.0003,
        )
    )
    metrics = [AnswerRelevance(), Groundedness(), Safety()]
    items = [EvalItem(m, qa_request, m.rubric(qa_request)) for m in metrics]
    judgments = await evaluator().evaluate_batch(items)
    assert route.call_count == 1
    body = json.loads(route.calls.last.request.content)
    assert set(body["questions"]) == {
        "answer_relevance__relevance",
        "groundedness__groundedness",
        "safety__category",
    }
    assert set(body["state"]) == {"user_input", "response", "retrieved_context"}
    assert [j.score for j in judgments] == pytest.approx([1.0, 2 / 3, 1.0])
    assert sum(j.cost_usd for j in judgments) == pytest.approx(0.0003)
    assert judgments[0].details["batched_with"] == ["groundedness", "safety"]
    assert all(j.latency_ms == judgments[0].latency_ms for j in judgments)


@respx.mock
async def test_batching_disabled_sends_one_request_per_metric(
    qa_request: EvaluationRequest,
) -> None:
    route = respx.post(URL).mock(
        return_value=ok(
            {
                "relevance": {"type": "score", "score": 3, "confidence": 0.9},
                "groundedness": {"type": "score", "score": 3, "confidence": 0.9},
            }
        )
    )
    metrics = [AnswerRelevance(), Groundedness()]
    await evaluator(batch=False).evaluate_batch(
        [EvalItem(m, qa_request, m.rubric(qa_request)) for m in metrics]
    )
    assert route.call_count == 2


@respx.mock
async def test_batch_failure_marks_every_item(qa_request: EvaluationRequest) -> None:
    respx.post(URL).mock(
        return_value=httpx.Response(400, json={"error": {"code": 400, "message": "bad"}})
    )
    metrics = [AnswerRelevance(), Groundedness()]
    judgments = await evaluator().evaluate_batch(
        [EvalItem(m, qa_request, m.rubric(qa_request)) for m in metrics]
    )
    assert all(j.error and "bad" in j.error for j in judgments)


def test_plan_batches_respects_conflicts_requests_and_limits(qa_request: EvaluationRequest) -> None:
    q = [BinaryQuestion(id="x", instructions="i")]
    other = qa_request.model_copy()
    items = [
        EvalItem(AnswerRelevance(), qa_request, Rubric(questions=q, state={"a": 1})),
        EvalItem(Groundedness(), qa_request, Rubric(questions=q, state={"a": 1, "b": 2})),
        EvalItem(Safety(), qa_request, Rubric(questions=q, state={"a": 999})),  # conflicting value
        EvalItem(
            AnswerRelevance(alias="ar2"), other, Rubric(questions=q, state={"a": 1})
        ),  # other request
    ]
    assert plan_batches(items, max_questions=32) == [[0, 1], [2], [3]]
    assert plan_batches(items[:2], max_questions=1) == [[0], [1]]


def test_availability_and_description() -> None:
    assert JevEvaluator(JevClient(None)).available()[0] is False
    ev = JevEvaluator(JevClient(FAKE_KEY))
    assert ev.available() == (True, None)
    described = ev.describe()
    assert described["model"] == "typesafe/jev-1.13" and described["endpoint"] == URL
    assert FAKE_KEY not in json.dumps(described)
