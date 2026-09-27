"""Regression tests for issues found during review (key routing, references, CLI edge cases)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from evalcascade.cli.app import app
from evalcascade.config import Settings, is_openrouter_url
from evalcascade.core.types import EvaluationRequest
from evalcascade.errors import DatasetError
from evalcascade.evaluators import LLMJudge, OpenRouterLLMJudge
from evalcascade.metrics import AnswerRelevance
from evalcascade.storage.store import ExperimentStore, resolve_dataset
from tests.conftest import FAKE_KEY
from tests.test_storage import experiment

OTHER_KEY = "k-other-endpoint-0123456789"


def test_openrouter_url_detection() -> None:
    assert is_openrouter_url("https://openrouter.ai/api/v1")
    assert is_openrouter_url("https://eu.openrouter.ai/api/v1")
    assert not is_openrouter_url("http://openrouter.ai/api/v1")  # no plaintext
    assert not is_openrouter_url("https://openrouter.ai.evil.example/v1")
    assert not is_openrouter_url("https://my-gateway.example/v1")


def test_toml_custom_judge_url_never_receives_the_openrouter_key(tmp_path: Path) -> None:
    cfg = tmp_path / "evalcascade.toml"
    cfg.write_text('[judge]\nbase_url = "https://my-gateway.example/v1"\n', encoding="utf-8")
    settings = Settings.load(cfg, env={"OPENROUTER_API_KEY": FAKE_KEY}, load_dotenv=False)
    assert settings.judge.provider == "openai_compatible"
    assert settings.judge_api_key() is None
    judge = LLMJudge.from_settings(settings)
    assert not judge.client.configured and judge.available()[0] is False


def test_explicit_openrouter_judge_uses_only_the_openrouter_key() -> None:
    env = {
        "OPENROUTER_API_KEY": FAKE_KEY,
        "EVALCASCADE_JUDGE_BASE_URL": "https://my-gateway.example/v1",
        "EVALCASCADE_JUDGE_API_KEY": OTHER_KEY,
        "EVALCASCADE_JUDGE_MODEL": "gateway-model",
        "EVALCASCADE_JUDGE_EXTRA_BODY": '{"chat_template_kwargs": {"enable_thinking": false}}',
    }
    settings = Settings.load(env=env, load_dotenv=False)
    judge = OpenRouterLLMJudge.from_settings(settings)
    assert judge.client.base_url == "https://openrouter.ai/api/v1"
    assert judge.client._http._api_key is not None
    assert judge.client._http._api_key.get_secret_value() == FAKE_KEY
    assert judge.model == "openai/gpt-4.1-mini" and judge.extra_body == {}
    gateway = LLMJudge.from_settings(settings)
    assert gateway.client._http._api_key is not None
    assert gateway.client._http._api_key.get_secret_value() == OTHER_KEY


def test_keyless_openai_compatible_server() -> None:
    env = {
        "EVALCASCADE_JUDGE_BASE_URL": "http://localhost:8001/v1",
        "EVALCASCADE_JUDGE_REQUIRE_API_KEY": "false",
    }
    judge = LLMJudge.from_settings(Settings.load(env=env, load_dotenv=False))
    assert judge.available() == (True, None)
    assert "Authorization" not in judge.client._http._headers()


def test_names_starting_with_latest_resolve_by_name(
    store: ExperimentStore, settings: Settings
) -> None:
    named = experiment(settings, "latest-model")
    newer = experiment(settings, "other")
    newer.created_at = named.created_at.replace(year=named.created_at.year + 1)
    store.save_experiment(named)
    store.save_experiment(newer)
    assert store.resolve("latest-model") == named.id
    assert store.resolve("latest") == newer.id and store.resolve("latest~1") == named.id


def test_unknown_sample_is_a_dataset_error() -> None:
    with pytest.raises(DatasetError, match="unknown sample"):
        resolve_dataset("sample:nope")


def test_empty_output_is_scored_not_skipped() -> None:
    request = EvaluationRequest(input="question?", output="")
    metric = AnswerRelevance()
    assert metric.missing_fields(request) == []
    outcome = metric.check(request)
    assert outcome is not None and outcome.score == 0.0


def test_cli_edge_cases(tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["init", str(tmp_path)]).exit_code == 0
    result = runner.invoke(app, ["run", "sample:nope", "--no-save"])
    assert result.exit_code == 2 and "unknown sample" in result.output
    metrics = runner.invoke(app, ["metrics"])
    assert "[doc2]" in metrics.output  # descriptions are not parsed as Rich markup
    runner.invoke(app, ["demo"])
    bad_format = runner.invoke(app, ["gate", "-b", "latest", "-c", "latest", "--format", "yaml"])
    assert bad_format.exit_code == 2
    assert runner.invoke(app, ["datasets", "create", "clash", "-o", "a.jsonl"]).exit_code == 0
    second = runner.invoke(app, ["datasets", "create", "clash", "-o", "b.jsonl"])
    assert second.exit_code == 2 and not (tmp_path / "b.jsonl").exists()
