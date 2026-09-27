"""EvaluationSuite SDK surface: sync/async APIs, tasks, preflight, configuration."""

from __future__ import annotations

import asyncio

import pytest

from evalcascade import EvalSuite, EvaluationPolicy, EvaluationRequest
from evalcascade.config import Settings
from evalcascade.datasets import Case, load_sample
from evalcascade.errors import ConfigurationError
from evalcascade.metrics import AnswerRelevance, CitationPresence, Correctness, Groundedness
from tests.conftest import FAKE_KEY, ScriptedEvaluator


def evaluators() -> dict[str, ScriptedEvaluator]:
    return {"jev": ScriptedEvaluator("jev"), "llm": ScriptedEvaluator("llm", route_label="llm")}


def test_evaluate_sync_readme_example(settings: Settings) -> None:
    suite = EvalSuite(
        metrics=[AnswerRelevance(), Groundedness()], evaluators=evaluators(), settings=settings
    )
    result = suite.evaluate_sync(
        input="What is the capital of France?",
        output="Paris.",
        context=["Paris is the capital of France."],
    )
    assert result.overall_score == pytest.approx(1.0) and result.passed
    assert set(result.scores) == {"answer_relevance", "groundedness"}
    assert "answer_relevance" in result.summary()
    assert result.get("nope") is None
    with pytest.raises(KeyError):
        result["nope"]


async def test_sync_helpers_refuse_inside_a_running_loop(settings: Settings) -> None:
    suite = EvalSuite(
        [CitationPresence()], settings=settings, policy=EvaluationPolicy.deterministic_only()
    )
    with pytest.raises(RuntimeError, match="event loop is already running"):
        suite.evaluate_sync(output="x [1]")
    assert (await suite.evaluate(output="x [1]")).overall_score == 1.0


async def test_evaluate_many_preserves_order(settings: Settings) -> None:
    suite = EvalSuite(
        [CitationPresence()], settings=settings, policy=EvaluationPolicy.deterministic_only()
    )
    seen: list[str | None] = []
    requests = [
        EvaluationRequest(id=str(i), output="cited [1]" if i % 2 else "none") for i in range(6)
    ]
    results = await suite.evaluate_many(
        requests, concurrency=2, on_result=lambda r: seen.append(r.case_id)
    )
    assert [r.case_id for r in results] == [str(i) for i in range(6)]
    assert [r.overall_score for r in results] == [0.0, 1.0] * 3
    assert sorted(seen) == [str(i) for i in range(6)]


def test_preflight_explains_missing_keys(settings: Settings) -> None:
    suite = EvalSuite([AnswerRelevance()], settings=settings)
    with pytest.raises(ConfigurationError) as info:
        suite.evaluate_sync(input="q", output="a")
    message = str(info.value)
    assert "OPENROUTER_API_KEY" in message and "deterministic" in message
    # Fully deterministic metrics need no evaluator at all.
    assert EvalSuite([CitationPresence()], settings=settings).evaluator_names() == set()


def test_preflight_passes_with_keys() -> None:
    settings = Settings.load(env={"OPENROUTER_API_KEY": FAKE_KEY}, load_dotenv=False)
    suite = EvalSuite([AnswerRelevance()], settings=settings)
    suite.preflight()
    cfg = suite.config()
    assert set(cfg["evaluators"]) == {"deterministic", "jev", "llm"}
    assert cfg["evaluators"]["jev"]["model"] == "typesafe/jev-1.13"
    assert FAKE_KEY not in str(cfg)


def test_suite_validation(settings: Settings) -> None:
    with pytest.raises(ConfigurationError, match="at least one metric"):
        EvalSuite([], settings=settings)
    with pytest.raises(ConfigurationError, match="duplicate metric keys"):
        EvalSuite([AnswerRelevance(), AnswerRelevance()], settings=settings)
    suite = EvalSuite(
        [AnswerRelevance(), AnswerRelevance(alias="relevance_strict", threshold=0.9)],
        evaluators=evaluators(),
        settings=settings,
    )
    result = suite.evaluate_sync(input="q", output="a")
    assert [m.metric for m in result.metrics] == ["answer_relevance", "relevance_strict"]
    assert result["relevance_strict"].threshold == 0.9


def test_run_with_sync_async_and_mapping_tasks(settings: Settings) -> None:
    ds = load_sample("support_bot").head(3)
    suite = EvalSuite([Correctness()], evaluators=evaluators(), settings=settings)

    def sync_task(case: Case) -> str:
        return case.expected.answers()[0] if case.expected and case.expected.answers() else "n/a"

    exp = suite.run_sync(ds, task=sync_task, name="sync")
    assert exp.name == "sync" and exp.dataset.size == 3 and exp.dataset.hash == ds.hash
    assert exp.results[0].case.output == exp.results[0].case.expected.answers()[0]  # type: ignore[union-attr]
    assert exp.results[0]["correctness"].route == "deterministic"

    async def async_task(case: Case) -> dict[str, object]:
        await asyncio.sleep(0)
        return {"output": "Canberra", "context": ["c"], "ignored": 1}

    exp2 = suite.run_sync(ds, task=async_task)
    assert exp2.results[1].case.output == "Canberra" and exp2.results[1].case.context == ["c"]
    assert exp2.name == "support_bot-run"


def test_run_records_task_failures(settings: Settings) -> None:
    def broken(case: Case) -> str:
        raise RuntimeError(f"model crashed on {case.id}")

    exp = EvalSuite([Correctness()], evaluators=evaluators(), settings=settings).run_sync(
        load_sample("support_bot").head(2), task=broken
    )
    assert all(r.error and "model crashed" in r.error for r in exp.results)
    assert all(not r.metrics for r in exp.results)


def test_run_accepts_paths_and_records(settings: Settings, tmp_path) -> None:  # type: ignore[no-untyped-def]
    suite = EvalSuite([CitationPresence()], settings=settings)
    path = load_sample("rag_qa").to_jsonl(tmp_path / "rag.jsonl")
    assert suite.run_sync(path, limit=4).summary.num_cases == 4
    inline = suite.run_sync([{"output": "a [1]"}, {"output": "b"}])
    assert inline.dataset.name == "inline" and inline.summary.overall_score == 0.5


def test_policy_defaults_come_from_settings() -> None:
    settings = Settings.load(env={"EVALCASCADE_ESCALATE_BELOW": "0.9"}, load_dotenv=False)
    assert EvalSuite([AnswerRelevance()], settings=settings).policy.escalate_below == 0.9


def test_policy_presets() -> None:
    assert EvaluationPolicy.preset("cascade", 0.7).escalate_below == 0.7
    assert EvaluationPolicy.preset("jev").fallback is None
    assert EvaluationPolicy.preset("llm").primary == "llm"
    assert EvaluationPolicy.preset("deterministic").primary is None
    with pytest.raises(ValueError, match="unknown policy preset"):
        EvaluationPolicy.preset("magic")
    assert EvaluationPolicy(
        overrides={"a": {"primary": "x", "fallback": "y"}}
    ).evaluator_names() == {"jev", "llm", "x", "y"}  # type: ignore[dict-item]
