"""Metric behaviour: deterministic checks, rubric construction, aggregation, normalization."""

from __future__ import annotations

import pytest

from evalcascade.core.rubric import (
    BinaryQuestion,
    ChoiceQuestion,
    Rubric,
    ScoreQuestion,
    answer_binary,
    answer_choice,
    answer_score,
)
from evalcascade.core.types import EvaluationRequest
from evalcascade.errors import ConfigurationError
from evalcascade.metrics import (
    METRICS,
    SUITES,
    AnswerRelevance,
    CitationCorrectness,
    CitationPresence,
    ContextRelevance,
    Correctness,
    Groundedness,
    Safety,
    TaskCompletion,
    TaskSuccess,
    ToolArgumentsQuality,
    ToolSelection,
    TrajectoryEfficiency,
    UnnecessaryToolCalls,
    build_metrics,
    get_metric,
    metric_catalog,
)
from evalcascade.metrics._text import (
    find_citations,
    find_sensitive_data,
    matches_reference,
    normalize_answer,
    numeric_citations,
    split_sentences,
    truncate,
)
from evalcascade.metrics.agent import duplicate_indices, validate_arguments


def upd(request: EvaluationRequest, **updates: object) -> EvaluationRequest:
    """Copy with validation (model_copy(update=...) would skip it)."""
    return EvaluationRequest.model_validate({**request.model_dump(), **updates})


def answer_all(
    rubric: Rubric, *, p: float = 1.0, level_fraction: float = 1.0, choice: str | None = None
) -> dict:  # type: ignore[type-arg]
    out = {}
    for q in rubric.questions:
        if isinstance(q, BinaryQuestion):
            out[q.id] = answer_binary(q, p)
        elif isinstance(q, ChoiceQuestion):
            out[q.id] = answer_choice(
                q, choice or max(q.option_scores, key=q.option_scores.__getitem__)
            )
        else:
            out[q.id] = answer_score(q, q.max_level * level_fraction)
    return out


# -- registry -----------------------------------------------------------------------


def test_registry_catalog_and_suites() -> None:
    assert len(METRICS) == 13
    names = {i.name for i in metric_catalog()}
    assert names == set(METRICS)
    for suite in SUITES.values():
        assert set(suite) <= names
    assert [m.key for m in build_metrics(["rag", "groundedness"])] == list(SUITES["rag"])
    assert get_metric("groundedness", threshold=0.9).pass_threshold == 0.9
    with pytest.raises(ConfigurationError, match="unknown metric"):
        get_metric("nope")
    with pytest.raises(ConfigurationError, match="invalid parameters"):
        get_metric("groundedness", granularity="paragraph")


def test_metric_config_is_recorded() -> None:
    cfg = Groundedness(threshold=0.7, escalate_below=0.9).config()
    assert (
        cfg["name"] == "groundedness"
        and cfg["params"]["threshold"] == 0.7
        and cfg["params"]["escalate_below"] == 0.9
    )
    assert AnswerRelevance(alias="relevance_strict").key == "relevance_strict"


@pytest.mark.parametrize("name", sorted(METRICS))
def test_every_metric_normalizes_to_unit_interval(
    name: str, qa_request: EvaluationRequest, agent_request: EvaluationRequest
) -> None:
    metric = METRICS[name]()
    request = agent_request if metric.category == "agent" else qa_request
    rubric = metric.rubric(request)
    if rubric is None:
        outcome = metric.check(request)
        assert outcome is not None and 0.0 <= outcome.score <= 1.0
        return
    for p, frac in ((0.0, 0.0), (0.5, 0.5), (1.0, 1.0)):
        agg = metric.aggregate(answer_all(rubric, p=p, level_fraction=frac), rubric)
        assert 0.0 <= agg.score <= 1.0


# -- general ----------------------------------------------------------------------------


def test_answer_relevance(qa_request: EvaluationRequest) -> None:
    m = AnswerRelevance()
    assert m.check(qa_request) is None
    empty = m.check(qa_request.model_copy(update={"output": "   "}))
    assert empty is not None and empty.score == 0.0
    rubric = m.rubric(qa_request)
    assert isinstance(rubric.questions[0], ScoreQuestion) and len(rubric.questions[0].levels) == 4
    assert rubric.state == {"user_input": qa_request.input, "response": qa_request.output}
    assert m.missing_fields(EvaluationRequest(output="x")) == ["input"]


def test_correctness_deterministic_and_semantic(qa_request: EvaluationRequest) -> None:
    m = Correctness()
    exact = m.check(qa_request.model_copy(update={"output": "paris."}))
    assert exact is not None and exact.score == 1.0 and exact.details["match_mode"] == "normalized"
    assert m.check(qa_request) is None  # paraphrase: semantic
    assert Correctness(match="contains").check(qa_request) is not None
    assert (
        Correctness(match="none").check(qa_request.model_copy(update={"output": "Paris"})) is None
    )
    with_ref = m.rubric(qa_request)
    assert with_ref.state["reference_answer"] == "Paris" and not with_ref.requires_reasoning
    no_ref = m.rubric(qa_request.model_copy(update={"expected": None}))
    assert no_ref.requires_reasoning and no_ref.guidance


def test_task_completion_requirements(qa_request: EvaluationRequest) -> None:
    rubric = TaskCompletion(requirements=["Use one sentence"]).rubric(qa_request)
    assert rubric.state["requirements"] == ["Use one sentence"]
    assert "requirements" in rubric.questions[0].instructions


def test_safety_deterministic_leaks_and_choice() -> None:
    card = EvaluationRequest(output="Your card number is 4111 1111 1111 1111.")
    outcome = Safety().check(card)
    assert (
        outcome is not None
        and outcome.score == 0.0
        and outcome.details["sensitive_data"] == ["payment_card"]
    )
    not_luhn = EvaluationRequest(output="Order 4111 1111 1111 1112 shipped.")
    assert Safety().check(not_luhn) is None
    rubric = Safety().rubric(not_luhn)
    q = rubric.questions[0]
    assert (
        isinstance(q, ChoiceQuestion)
        and q.option_scores["safe"] == 1.0
        and sum(q.option_scores.values()) == 1.0
    )
    agg = Safety().aggregate(answer_all(rubric, choice="harmful_advice"), rubric)
    assert agg.score == 0.0 and agg.details["category"] == "harmful_advice"


def test_sensitive_data_detection() -> None:
    key = "sk-proj-" + "A1b2C3d4" * 4
    assert "api_key" in find_sensitive_data(f"use {key}")
    assert "private_key" in find_sensitive_data("-----BEGIN RSA PRIVATE KEY-----")
    assert "aws_access_key" in find_sensitive_data("AKIA" + "ABCDEFGHIJKLMNOP")
    assert "us_ssn" in find_sensitive_data("SSN 123-45-6789")
    assert find_sensitive_data("Call 555-0100 about order 12345") == []


# -- RAG -----------------------------------------------------------------------------------


def test_groundedness_response_and_sentence_modes(qa_request: EvaluationRequest) -> None:
    rubric = Groundedness().rubric(qa_request)
    assert rubric.state["retrieved_context"] == qa_request.context
    two = qa_request.model_copy(
        update={"output": "Paris is the capital [1]. It has 90 million residents."}
    )
    sentence = Groundedness(granularity="sentence")
    r = sentence.rubric(two)
    assert [q.id for q in r.questions] == ["s1", "s2"]
    assert r.state["claims"]["s1"] == "Paris is the capital."
    answers = {
        "s1": answer_binary(r.question("s1"), 0.95),
        "s2": answer_binary(r.question("s2"), 0.05),
    }  # type: ignore[arg-type]
    agg = sentence.aggregate(answers, r)
    assert agg.score == pytest.approx(0.5)
    assert agg.details["unsupported"] == ["It has 90 million residents."]


def test_context_relevance_per_passage(qa_request: EvaluationRequest) -> None:
    m = ContextRelevance(max_passages=1)
    rubric = m.rubric(qa_request)
    assert [q.id for q in rubric.questions] == ["p1"] and list(rubric.state["passages"]) == ["p1"]
    agg = m.aggregate(answer_all(rubric, p=1.0), rubric)
    assert agg.details["not_judged"] == 1 and agg.details["relevant"] == 1


def test_citation_presence() -> None:
    m = CitationPresence(min_citations=2)
    assert m.check(EvaluationRequest(output="As noted [1] and [doc2].")).score == 1.0  # type: ignore[union-attr]
    assert m.check(EvaluationRequest(output="One source [1].")).score == 0.5  # type: ignore[union-attr]
    assert CitationPresence().check(EvaluationRequest(output="No sources.")).score == 0.0  # type: ignore[union-attr]
    assert m.rubric(EvaluationRequest(output="x")) is None


def test_citation_correctness_paths(qa_request: EvaluationRequest) -> None:
    m = CitationCorrectness()
    invalid = qa_request.model_copy(update={"output": "Paris is the capital [7]."})
    outcome = m.check(invalid)
    assert outcome is not None and outcome.score == 0.0 and outcome.details["invalid"] == [7]
    none = qa_request.model_copy(update={"output": "Paris is the capital."})
    assert m.check(none) is None and m.rubric(none) is None
    assert "no numeric citations" in m.not_applicable_reason(none)
    mixed = qa_request.model_copy(
        update={"output": "Paris is the capital [1]. Berlin is in Germany [2]. Rome is lovely [9]."}
    )
    assert m.check(mixed) is None
    rubric = m.rubric(mixed)
    assert rubric is not None and [q.id for q in rubric.questions] == ["c1", "c2"]
    assert rubric.state["citations"]["c2"]["passage"] == qa_request.context[1]
    agg = m.aggregate(
        {
            "c1": answer_binary(rubric.question("c1"), 1.0),
            "c2": answer_binary(rubric.question("c2"), 0.0),
        },
        rubric,
    )  # type: ignore[arg-type]
    assert agg.score == pytest.approx(1 / 3) and agg.details["invalid"] == [9]


def test_text_helpers() -> None:
    assert normalize_answer("The  Eiffel Tower!") == "eiffel tower"
    assert matches_reference("It is Paris.", ["paris"], "contains") == "paris"
    assert matches_reference("Parisian food", ["paris"], "contains") is None
    assert matches_reference("Paris", ["Paris"], "exact") == "Paris"
    assert numeric_citations("See [1], [2, 3] and [4-6].") == [1, 2, 3, 4, 5, 6]
    assert find_citations("x (source: handbook) https://example.com/a [^1]") == [
        "(source: handbook)",
        "[^1]",
        "https://example.com/a",
    ]
    assert split_sentences("One. Two! Three?\n\n- bullet") == ["One.", "Two!", "Three?", "- bullet"]
    assert truncate("x" * 100, 50).endswith("chars]") and truncate("short", 50) == "short"


# -- agents ---------------------------------------------------------------------------------


def test_tool_selection(agent_request: EvaluationRequest) -> None:
    m = ToolSelection()
    assert m.check(agent_request) is None
    rubric = m.rubric(agent_request)
    assert [q.id for q in rubric.questions] == ["call_1", "call_2", "call_3"]
    assert rubric.aux["steps"] == [1, 2, 3]
    agg = m.aggregate(answer_all(rubric, p=1.0), rubric)
    assert [s["step_index"] for s in agg.details["steps"]] == [1, 2, 3]
    gt = upd(agent_request, expected={"tools": ["get_weather"]})
    outcome = m.check(gt)
    assert outcome is not None and outcome.score == pytest.approx(2 / 3)  # precision 1/2, recall 1
    assert outcome.details["unexpected"] == ["web_search"]
    assert outcome.details["steps"][0] == {
        "step_index": 1,
        "label": "unexpected_tool",
        "score": 0.0,
        "explanation": None,
    }


def test_tool_selection_without_calls() -> None:
    direct = EvaluationRequest(
        input="hi",
        output="hello",
        trace={"tools": [{"name": "t"}], "steps": [{"type": "message", "content": "hello"}]},
    )
    rubric = ToolSelection().rubric(direct)
    assert [q.id for q in rubric.questions] == ["no_tools"]
    no_tools = EvaluationRequest(
        input="hi", trace={"steps": [{"type": "message", "content": "hello"}]}
    )
    assert ToolSelection().check(no_tools).score == 1.0  # type: ignore[union-attr]


def test_tool_arguments_quality(agent_request: EvaluationRequest) -> None:
    m = ToolArgumentsQuality()
    assert m.check(agent_request) is None
    rubric = m.rubric(agent_request)
    assert rubric is not None and len(rubric.questions) == 3
    assert "parameters" in rubric.state["available_tools"]["get_weather"]
    bad = agent_request.model_copy(deep=True)
    assert bad.trace is not None
    for step in bad.trace.steps:
        if step.tool_call:
            step.tool_call.arguments = {"town": 3}
    outcome = m.check(bad)
    assert outcome is not None and outcome.score == 0.0
    expected = upd(
        agent_request,
        expected={
            "tool_calls": [
                {"name": "get_weather", "arguments": {"city": "oslo"}},
                {"name": "send_email", "arguments": {}},
            ]
        },
    )
    exp_outcome = m.check(expected)
    assert exp_outcome is not None and exp_outcome.score == pytest.approx(0.5)


def test_schema_validation() -> None:
    from evalcascade.core.types import ToolSpec

    spec = ToolSpec(
        name="t",
        parameters={
            "type": "object",
            "properties": {
                "n": {"type": "integer"},
                "mode": {"enum": ["a", "b"]},
                "flag": {"type": "boolean"},
            },
            "required": ["n"],
            "additionalProperties": False,
        },
    )
    assert validate_arguments({"n": 1, "mode": "a", "flag": True}, spec) == []
    errors = validate_arguments({"n": True, "mode": "z", "extra": 1}, spec)
    assert any("should be integer" in e for e in errors)
    assert any("must be one of" in e for e in errors)
    assert any("unexpected argument 'extra'" in e for e in errors)
    assert validate_arguments({}, spec) == ["missing required argument 'n'"]
    assert validate_arguments({"anything": 1}, None) == []


def test_unknown_tool_is_invalid(agent_request: EvaluationRequest) -> None:
    req = agent_request.model_copy(deep=True)
    assert req.trace is not None
    for step in req.trace.steps:
        if step.tool_call:
            step.tool_call.name = "delete_everything"
    outcome = ToolArgumentsQuality().check(req)
    assert outcome is not None and outcome.score == 0.0
    assert "unknown tool" in outcome.details["steps"][0]["explanation"]


def test_trajectory_efficiency(agent_request: EvaluationRequest) -> None:
    m = TrajectoryEfficiency()
    rubric = m.rubric(agent_request)
    assert rubric.state["trajectory_facts"] == {
        "steps": 5,
        "tool_calls": 3,
        "duplicate_calls": 1,
        "failed_calls": 0,
    }
    budget = m.check(upd(agent_request, expected={"max_tool_calls": 1}))
    assert budget is not None and budget.score == pytest.approx(1 / 3)
    assert m.check(upd(agent_request, expected={"max_tool_calls": 5})).score == 1.0  # type: ignore[union-attr]


def test_task_success(agent_request: EvaluationRequest) -> None:
    m = TaskSuccess()
    assert m.check(upd(agent_request, expected={"answer": "4°C"})).score == 1.0  # type: ignore[union-attr]
    rubric = m.rubric(agent_request)
    assert {"final_response", "trajectory", "user_input"} <= set(rubric.state)
    assert m.missing_fields(EvaluationRequest(input="x")) == ["output or trace"]


def test_unnecessary_tool_calls(agent_request: EvaluationRequest) -> None:
    m = UnnecessaryToolCalls()
    calls = agent_request.trace.tool_call_steps()  # type: ignore[union-attr]
    assert duplicate_indices(calls) == {2}
    assert m.check(agent_request) is None
    rubric = m.rubric(agent_request)
    assert len(rubric.questions) == 2 and rubric.aux["duplicate_steps"] == [3]
    agg = m.aggregate(answer_all(rubric, p=1.0), rubric)
    assert agg.score == pytest.approx(2 / 3)
    gt = m.check(upd(agent_request, expected={"tools": ["get_weather"]}))
    assert gt is not None and gt.score == pytest.approx(1 / 3)
    none = EvaluationRequest(input="x", trace={"steps": [{"type": "message", "content": "hi"}]})
    assert m.check(none).score == 1.0  # type: ignore[union-attr]
