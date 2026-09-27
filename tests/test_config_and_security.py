"""Configuration precedence and secret hygiene."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from evalcascade.config import Settings, redact_database_url
from evalcascade.errors import ConfigurationError, EvalCascadeError, ProviderError
from evalcascade.redaction import REDACTED, get_logger, redact
from tests.conftest import FAKE_KEY


def test_defaults() -> None:
    s = Settings.load(env={}, load_dotenv=False)
    assert s.jev.model == "typesafe/jev-1.13" and s.jev.surface == "decisions"
    assert s.judge.provider == "openrouter" and s.judge.model == "openai/gpt-4.1-mini"
    assert (
        s.policy.primary == "jev" and s.policy.fallback == "llm" and s.policy.escalate_below == 0.82
    )
    assert s.openrouter_api_key is None and s.judge_api_key() is None
    assert s.resolved_database_url.startswith("sqlite:///") and s.resolved_database_url.endswith(
        "/evalcascade.db"
    )


def test_environment_mapping() -> None:
    env = {
        "OPENROUTER_API_KEY": FAKE_KEY,
        "EVALCASCADE_JEV_MODEL": "~typesafe/jev-latest",
        "EVALCASCADE_JEV_SURFACE": "systemone",
        "EVALCASCADE_JEV_BATCH": "false",
        "EVALCASCADE_JEV_TIMEOUT": "12.5",
        "EVALCASCADE_JUDGE_BASE_URL": "http://localhost:8001/v1",
        "EVALCASCADE_JUDGE_MODEL": "qwen",
        "EVALCASCADE_JUDGE_EXTRA_BODY": '{"chat_template_kwargs": {"enable_thinking": false}}',
        "EVALCASCADE_JUDGE_INPUT_COST_PER_MTOK": "0.42",
        "EVALCASCADE_ESCALATE_BELOW": "0.9",
        "EVALCASCADE_FALLBACK": "none",
        "EVALCASCADE_DATABASE_URL": "sqlite:///x.db",
    }
    s = Settings.load(env=env, load_dotenv=False)
    assert (
        s.jev.model == "~typesafe/jev-latest"
        and s.jev.surface == "systemone"
        and s.jev.batch is False
    )
    assert s.jev.timeout_s == 12.5
    assert s.judge.provider == "openai_compatible"  # implied by a custom base URL
    assert s.judge.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
    assert s.judge.input_cost_per_mtok == 0.42
    assert s.judge_api_key() is None  # the OpenRouter key is not sent to a foreign endpoint
    assert s.policy.escalate_below == 0.9 and s.policy.fallback is None
    assert s.resolved_database_url == "sqlite:///x.db"


def test_toml_then_env_precedence(tmp_path: Path) -> None:
    cfg = tmp_path / "evalcascade.toml"
    cfg.write_text(
        '[evalcascade]\nhome = "ws"\n[policy]\nescalate_below = 0.7\n[jev]\nmodel = "from-toml"\n'
        '[judge]\nmodel = "judge-toml"\n[metrics.groundedness]\nthreshold = 0.8\n',
        encoding="utf-8",
    )
    s = Settings.load(cfg, env={"EVALCASCADE_JEV_MODEL": "from-env"}, load_dotenv=False)
    assert s.jev.model == "from-env" and s.judge.model == "judge-toml"
    assert s.policy.escalate_below == 0.7 and s.metrics == {"groundedness": {"threshold": 0.8}}
    assert s.home == (tmp_path / "ws").resolve() and s.config_file == cfg
    override = Settings.load(cfg, env={}, load_dotenv=False, policy={"escalate_below": 0.5})
    assert override.policy.escalate_below == 0.5


def test_config_discovery_and_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "evalcascade.toml").write_text('[jev]\nmodel = "cwd"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert Settings.load(env={}, load_dotenv=False).jev.model == "cwd"
    with pytest.raises(ConfigurationError, match="not found"):
        Settings.load(tmp_path / "missing.toml", env={}, load_dotenv=False)
    with pytest.raises(ConfigurationError, match="missing file"):
        Settings.load(env={"EVALCASCADE_CONFIG": str(tmp_path / "nope.toml")}, load_dotenv=False)
    bad = tmp_path / "bad.toml"
    bad.write_text("[jev\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="cannot read"):
        Settings.load(bad, env={}, load_dotenv=False)
    keyed = tmp_path / "keyed.toml"
    keyed.write_text('[judge]\napi_key = "x"\n', encoding="utf-8")
    with pytest.raises(ConfigurationError, match="do not put API keys"):
        Settings.load(keyed, env={}, load_dotenv=False)
    with pytest.raises(ConfigurationError, match="invalid configuration"):
        Settings.load(env={"EVALCASCADE_JEV_SURFACE": "bogus"}, load_dotenv=False)
    with pytest.raises(ConfigurationError, match="JSON object"):
        Settings.load(env={"EVALCASCADE_JUDGE_EXTRA_BODY": "{nope"}, load_dotenv=False)


def test_dotenv_loading_respects_existing_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        f"OPENROUTER_API_KEY={FAKE_KEY}\nEVALCASCADE_JEV_MODEL=dotenv-model\n", encoding="utf-8"
    )
    monkeypatch.setenv("EVALCASCADE_JEV_MODEL", "already-set")
    monkeypatch.delenv("EVALCASCADE_DISABLE_DOTENV")
    s = Settings.load()
    assert s.openrouter_api_key is not None and s.openrouter_api_key.get_secret_value() == FAKE_KEY
    assert s.jev.model == "already-set"
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.setenv("EVALCASCADE_DISABLE_DOTENV", "1")
    assert Settings.load().openrouter_api_key is None


def test_secrets_never_appear_in_repr_or_summary() -> None:
    s = Settings.load(
        env={"OPENROUTER_API_KEY": FAKE_KEY, "EVALCASCADE_API_TOKEN": "t" * 24}, load_dotenv=False
    )
    assert FAKE_KEY not in repr(s) and FAKE_KEY not in str(s.summary())
    summary = s.summary()
    assert summary["openrouter_api_key_configured"] is True and summary["api_auth_enabled"] is True
    assert FAKE_KEY not in s.model_dump_json()


def test_redaction_patterns() -> None:
    assert redact(f"Authorization: Bearer {FAKE_KEY}") == f"Authorization: {REDACTED}"
    assert FAKE_KEY not in redact(f"key {FAKE_KEY} leaked")
    assert redact('{"api_key": "abcdef123456"}') == '{"api_key": "' + REDACTED + '"}'
    assert redact("password=hunter2hunter2") == f"password={REDACTED}"
    assert redact("nothing secret here") == "nothing secret here"
    assert redact("") == ""
    assert redact_database_url("postgresql://user:pass@db:5432/x") == "postgresql://***@db:5432/x"
    assert redact_database_url("sqlite:///a.db") == "sqlite:///a.db"


def test_exceptions_and_logs_are_redacted(caplog: pytest.LogCaptureFixture) -> None:
    assert FAKE_KEY not in str(EvalCascadeError(f"bad key {FAKE_KEY}"))
    err = ProviderError(f"echo Bearer {FAKE_KEY}", provider="x", status_code=401)
    assert FAKE_KEY not in str(err) and "(HTTP 401)" in str(err)
    logger = get_logger("evalcascade.test")
    caplog.set_level(logging.INFO, logger="evalcascade")
    logger.info("calling with %s", f"Bearer {FAKE_KEY}")
    assert FAKE_KEY not in caplog.text and REDACTED in caplog.text


def test_env_example_has_placeholders_only() -> None:
    example = Path(__file__).resolve().parents[1] / ".env.example"
    if not example.exists():
        pytest.skip(".env.example not present")
    text = example.read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY" in text
    import re

    assert not re.search(r"sk-or-v1-[0-9a-f]{64}", text)
