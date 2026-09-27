"""Live integration tests — skipped unless EVALCASCADE_LIVE_TESTS=1.

* Jev tests need ``OPENROUTER_API_KEY`` (cost: a few hundred-thousandths of a dollar).
* The LLM-judge test needs an OpenAI-compatible endpoint via ``EVALCASCADE_JUDGE_BASE_URL``,
  ``EVALCASCADE_JUDGE_API_KEY`` and ``EVALCASCADE_JUDGE_MODEL`` (or OpenRouter defaults).
"""

from __future__ import annotations

import os

import pytest

from evalcascade import EvalSuite, EvaluationPolicy
from evalcascade.config import Settings
from evalcascade.core.types import EvaluationRequest
from evalcascade.evaluators import JevEvaluator, LLMJudge
from evalcascade.metrics import AnswerRelevance, Groundedness, Safety

pytestmark = pytest.mark.live

GOOD = EvaluationRequest(
    input="How long are backups kept on the Starter plan?",
    output="Backups on the Starter plan are kept for 7 days.",
    context=["Automated backups are retained for 30 days on Business plans and 7 days on Starter."],
)


def _settings() -> Settings:
    return Settings.load(env=dict(os.environ), load_dotenv=False)


@pytest.fixture
def jev_settings() -> Settings:
    settings = _settings()
    if settings.openrouter_api_key is None:
        pytest.skip("OPENROUTER_API_KEY not set")
    return settings


async def test_live_jev_single_and_batched(jev_settings: Settings) -> None:
    evaluator = JevEvaluator.from_settings(jev_settings)
    try:
        judgment = await evaluator.evaluate(Groundedness(), GOOD)
        assert judgment.error is None, judgment.error
        assert judgment.model and judgment.model.startswith("typesafe/jev")
        assert judgment.score is not None and 0 <= judgment.score <= 1
        assert judgment.confidence is not None and judgment.cost_source == "provider"

        suite = EvalSuite(
            [AnswerRelevance(), Groundedness(), Safety()],
            policy=EvaluationPolicy.jev_only(),
            evaluators={"jev": evaluator},
            settings=jev_settings,
        )
        result = await suite.evaluate(request=GOOD)
        assert all(m.status == "ok" for m in result.metrics), [m.message for m in result.metrics]
        request_ids = {m.judgments[0].request_id for m in result.metrics}
        assert len(request_ids) == 1  # one batched Decisions call
    finally:
        await evaluator.aclose()


async def test_live_llm_judge() -> None:
    settings = _settings()
    if settings.judge_api_key() is None:
        pytest.skip("no judge endpoint configured")
    judge = LLMJudge.from_settings(settings)
    try:
        judgment = await judge.evaluate(Groundedness(), GOOD)
        assert judgment.error is None, judgment.error
        assert judgment.score is not None and judgment.explanation
    finally:
        await judge.aclose()
