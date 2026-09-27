"""Shared fixtures. Tests never touch the network or real API keys (except tests marked live)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar

import pytest

from evalcascade.config import Settings
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
from evalcascade.core.types import EvaluationRequest, Usage
from evalcascade.errors import ProviderError
from evalcascade.storage.store import ExperimentStore

LIVE = os.environ.get("EVALCASCADE_LIVE_TESTS") == "1"
_SENSITIVE_PREFIXES = ("OPENROUTER_", "EVALCASCADE_", "QWEN_")


@pytest.fixture(autouse=True)
def _isolate_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """No .env loading, no inherited keys/config, and a clean working directory."""
    if request.node.get_closest_marker("live"):
        monkeypatch.setenv("EVALCASCADE_DISABLE_DOTENV", "1")
        return
    for key in list(os.environ):
        if key.startswith(_SENSITIVE_PREFIXES):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("EVALCASCADE_DISABLE_DOTENV", "1")
    monkeypatch.setenv("EVALCASCADE_HOME", str(tmp_path / ".evalcascade"))
    monkeypatch.chdir(tmp_path)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if LIVE:
        return
    skip = pytest.mark.skip(
        reason="live test: set EVALCASCADE_LIVE_TESTS=1 (uses real API credits)"
    )
    for item in items:
        if item.get_closest_marker("live"):
            item.add_marker(skip)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings.load(env={}, load_dotenv=False, home=tmp_path / ".evalcascade")


@pytest.fixture
def store(tmp_path: Path) -> Iterator[ExperimentStore]:
    s = ExperimentStore(
        f"sqlite:///{(tmp_path / 'test.db').as_posix()}", home=tmp_path / ".evalcascade"
    )
    yield s
    s.dispose()


FAKE_KEY = "sk-or-v1-" + "0123456789abcdef" * 4  # fake, assembled at runtime


class ScriptedEvaluator(SemanticEvaluator):
    """Deterministic test double.

    ``p``: P(true) for binary questions; ``level``: level for score questions (default: max);
    ``choice``: selected option (default: highest-scoring); ``confidence``: reported confidence
    (for binary it overrides the derived one).
    """

    kind: ClassVar[EvaluatorKind] = "system_one"

    def __init__(
        self,
        name: str = "scripted",
        *,
        route_label: Route = "jev",
        kind: EvaluatorKind = "system_one",
        p: float = 0.95,
        level: float | None = None,
        choice: str | None = None,
        confidence: float | None = 0.95,
        error: str | None = None,
        cost: float = 0.001,
        latency_ms: float = 10.0,
        explanation: str | None = None,
    ) -> None:
        self.name = name
        self.route_label = route_label
        self.kind = kind  # type: ignore[misc]
        self.p, self.level, self.choice = p, level, choice
        self.confidence, self.error = confidence, error
        self.cost, self.latency = cost, latency_ms
        self.explanation = explanation
        self.calls: list[Rubric] = []

    async def answer(self, rubric: Rubric) -> RawAnswers:
        self.calls.append(rubric)
        if self.error:
            raise ProviderError(self.error, provider=self.name, status_code=503)
        answers: dict[str, Answer] = {}
        for q in rubric.questions:
            if isinstance(q, BinaryQuestion):
                a = answer_binary(q, self.p, explanation=self.explanation).model_copy(
                    update={
                        "confidence": self.confidence,
                        "confidence_source": "provider" if self.confidence is not None else None,
                    }
                )
            elif isinstance(q, ChoiceQuestion):
                pick = self.choice or max(q.option_scores, key=lambda k: q.option_scores[k])
                a = answer_choice(q, pick, confidence=self.confidence, explanation=self.explanation)
            else:
                lvl = q.max_level if self.level is None else self.level
                a = answer_score(q, lvl, confidence=self.confidence, explanation=self.explanation)
            answers[q.id] = a
        return RawAnswers(
            answers=answers,
            model=f"{self.name}-model",
            latency_ms=self.latency,
            usage=Usage(input_tokens=100, output_tokens=5),
            cost_usd=self.cost,
            cost_source="provider",
            request_id=f"{self.name}-req",
        )

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind}


@pytest.fixture
def qa_request() -> EvaluationRequest:
    return EvaluationRequest(
        id="q1",
        input="What is the capital of France?",
        output="Paris is the capital of France [1].",
        context=[
            "Paris is the capital and largest city of France.",
            "Berlin is the capital of Germany.",
        ],
        expected={"answer": "Paris"},
    )


@pytest.fixture
def agent_request() -> EvaluationRequest:
    weather = {
        "name": "get_weather",
        "description": "Weather for a city",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "unit": {"type": "string", "enum": ["c", "f"]},
            },
            "required": ["city"],
            "additionalProperties": False,
        },
    }
    search = {
        "name": "web_search",
        "description": "Search the web",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }
    return EvaluationRequest(
        id="a1",
        input="What's the weather in Oslo?",
        output="It is 4°C and cloudy in Oslo.",
        trace={
            "tools": [weather, search],
            "steps": [
                {"type": "thought", "content": "I should check the weather."},
                {
                    "type": "tool_call",
                    "tool_call": {
                        "name": "web_search",
                        "arguments": {"query": "oslo weather"},
                        "result": "...",
                    },
                },
                {
                    "type": "tool_call",
                    "tool_call": {
                        "name": "get_weather",
                        "arguments": {"city": "Oslo"},
                        "result": {"temp": 4},
                    },
                },
                {
                    "type": "tool_call",
                    "tool_call": {
                        "name": "get_weather",
                        "arguments": {"city": "Oslo"},
                        "result": {"temp": 4},
                    },
                },
                {"type": "message", "content": "It is 4°C and cloudy in Oslo."},
            ],
        },
    )
