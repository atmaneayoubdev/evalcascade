"""Configuration.

Precedence (lowest → highest): built-in defaults, ``evalcascade.toml``, environment variables,
explicit keyword arguments / CLI flags. A ``.env`` file in the working directory is loaded
into the environment (without overriding variables that are already set) unless
``EVALCASCADE_DISABLE_DOTENV=1``.

Secrets are held as :class:`pydantic.SecretStr` and never appear in ``repr()``, logs,
experiment records or API responses.
"""

from __future__ import annotations

import json
import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from evalcascade.core.policy import EvaluationPolicy
from evalcascade.errors import ConfigurationError

DEFAULT_JEV_MODEL = "typesafe/jev-1.13"
DEFAULT_JUDGE_MODEL = "openai/gpt-4.1-mini"
OPENROUTER_API_BASE = "https://openrouter.ai/api"
CONFIG_FILENAME = "evalcascade.toml"


class JevSettings(BaseModel):
    """Settings for the Jev (System One) evaluator."""

    model_config = ConfigDict(extra="forbid")

    model: str = DEFAULT_JEV_MODEL
    surface: Literal["decisions", "systemone"] = Field(
        default="decisions",
        description="decisions = POST /api/alpha/decisions; systemone = POST /api/v1/systemone",
    )
    base_url: str = OPENROUTER_API_BASE
    timeout_s: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=3, ge=0, le=10)
    max_concurrency: int = Field(default=8, ge=1)
    batch: bool = Field(
        default=True, description="Send all Jev-routed metrics of a case in one request."
    )
    max_questions_per_request: int = Field(default=32, ge=1)


class JudgeSettings(BaseModel):
    """Settings for the generative LLM judge (any OpenAI-compatible chat endpoint)."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["openrouter", "openai_compatible"] = "openrouter"
    model: str = DEFAULT_JUDGE_MODEL
    base_url: str = f"{OPENROUTER_API_BASE}/v1"
    api_key: SecretStr | None = Field(
        default=None, description="Defaults to OPENROUTER_API_KEY for the openrouter provider."
    )
    timeout_s: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=3, ge=0, le=10)
    max_concurrency: int = Field(default=8, ge=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=64)
    structured_output: Literal["json_schema", "json_object", "prompt"] = "json_schema"
    parse_retries: int = Field(default=2, ge=0, le=5)
    extra_body: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra request fields, e.g. "
        '{"chat_template_kwargs": {"enable_thinking": false}}',
    )
    input_cost_per_mtok: float | None = Field(
        default=None,
        ge=0,
        description="USD per 1M input tokens, used when the provider reports no cost.",
    )
    output_cost_per_mtok: float | None = Field(default=None, ge=0)
    require_api_key: bool = Field(
        default=True, description="Set to false for OpenAI-compatible servers without auth."
    )

    @model_validator(mode="after")
    def _infer_provider(self) -> JudgeSettings:
        # Never treat a non-OpenRouter endpoint as OpenRouter: that would send the
        # OpenRouter key to a third-party host.
        if self.provider == "openrouter" and not is_openrouter_url(self.base_url):
            self.provider = "openai_compatible"
        return self


class Settings(BaseModel):
    """Top-level EvalCascade settings."""

    model_config = ConfigDict(extra="forbid")

    openrouter_api_key: SecretStr | None = None
    home: Path = Path(".evalcascade")
    database_url: str | None = None
    jev: JevSettings = Field(default_factory=JevSettings)
    judge: JudgeSettings = Field(default_factory=JudgeSettings)
    policy: EvaluationPolicy = Field(default_factory=EvaluationPolicy)
    metrics: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Per-metric parameter overrides from evalcascade.toml."
    )
    api_token: SecretStr | None = Field(
        default=None, description="If set, the local API requires 'Authorization: Bearer <token>'."
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    app_url: str = "https://github.com/atmaneayoubdev/evalcascade"
    app_title: str = "EvalCascade"
    config_file: Path | None = None

    # -- derived -------------------------------------------------------------------

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.home / 'evalcascade.db').resolve().as_posix()}"

    def judge_api_key(self) -> SecretStr | None:
        """The key sent to the judge endpoint. The OpenRouter key only ever goes to OpenRouter."""
        if self.judge.api_key is not None:
            return self.judge.api_key
        if self.judge.provider == "openrouter" and is_openrouter_url(self.judge.base_url):
            return self.openrouter_api_key
        return None

    def summary(self) -> dict[str, Any]:
        """A secret-free description of the effective configuration."""
        from evalcascade._version import __version__

        return {
            "version": __version__,
            "database": redact_database_url(self.resolved_database_url),
            "openrouter_api_key_configured": self.openrouter_api_key is not None,
            "judge_api_key_configured": self.judge_api_key() is not None,
            "api_auth_enabled": self.api_token is not None,
            "config_file": str(self.config_file) if self.config_file else None,
            "jev": {
                "model": self.jev.model,
                "surface": self.jev.surface,
                "base_url": self.jev.base_url,
                "timeout_s": self.jev.timeout_s,
                "max_retries": self.jev.max_retries,
                "batch": self.jev.batch,
            },
            "judge": {
                "provider": self.judge.provider,
                "model": self.judge.model,
                "base_url": self.judge.base_url,
                "timeout_s": self.judge.timeout_s,
                "temperature": self.judge.temperature,
                "structured_output": self.judge.structured_output,
            },
            "policy": self.policy.model_dump(),
        }

    # -- loading ---------------------------------------------------------------------

    @classmethod
    def load(
        cls,
        config_file: str | Path | None = None,
        *,
        env: Mapping[str, str] | None = None,
        load_dotenv: bool | None = None,
        **overrides: Any,
    ) -> Settings:
        """Load settings from defaults, ``evalcascade.toml`` and the environment."""
        if env is None:
            if load_dotenv is None:
                load_dotenv = os.environ.get("EVALCASCADE_DISABLE_DOTENV", "") not in {"1", "true"}
            if load_dotenv:
                _load_dotenv()
            env = os.environ

        data: dict[str, Any] = {}
        path = _find_config_file(config_file, env)
        if path is not None:
            data = _read_toml(path)
            data["config_file"] = path
        _apply_env(data, env)
        _deep_update(data, overrides)
        try:
            return cls.model_validate(data)
        except ValueError as exc:
            raise ConfigurationError(f"invalid configuration: {exc}") from exc


def is_openrouter_url(url: str) -> bool:
    """Whether ``url`` points at OpenRouter (https, host openrouter.ai or a subdomain)."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "openrouter.ai" or host.endswith(".openrouter.ai"))


def redact_database_url(url: str) -> str:
    """Hide credentials in a database URL (``scheme://user:pass@host`` → ``scheme://***@host``)."""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        return f"{scheme}://***@{rest.split('@', 1)[1]}"
    return url


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


def _load_dotenv() -> None:
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv is a dependency
        return
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path, override=False)


def _find_config_file(explicit: str | Path | None, env: Mapping[str, str]) -> Path | None:
    if explicit is not None:
        p = Path(explicit)
        if not p.is_file():
            raise ConfigurationError(f"config file not found: {p}")
        return p
    if env.get("EVALCASCADE_CONFIG"):
        p = Path(env["EVALCASCADE_CONFIG"])
        if not p.is_file():
            raise ConfigurationError(f"EVALCASCADE_CONFIG points to a missing file: {p}")
        return p
    p = Path.cwd() / CONFIG_FILENAME
    return p if p.is_file() else None


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"cannot read {path}: {exc}") from exc
    data: dict[str, Any] = {}
    core = raw.get("evalcascade", {})
    for key in ("home", "database_url", "cors_origins"):
        if key in core:
            data[key] = core[key]
    if "database" in core:
        data["database_url"] = _sqlite_url(core["database"], base=path.parent)
    if "home" in core:
        data["home"] = (path.parent / core["home"]).resolve()
    for section in ("jev", "judge", "policy", "metrics"):
        if section in raw:
            data[section] = raw[section]
    if "api_key" in data.get("judge", {}):
        raise ConfigurationError(
            "do not put API keys in evalcascade.toml; set EVALCASCADE_JUDGE_API_KEY instead"
        )
    return data


def _sqlite_url(value: str, base: Path) -> str:
    if "://" in value:
        return value
    return f"sqlite:///{(base / value).resolve().as_posix()}"


_ENV_MAP: dict[str, tuple[tuple[str, ...], type]] = {
    "OPENROUTER_API_KEY": (("openrouter_api_key",), str),
    "EVALCASCADE_HOME": (("home",), str),
    "EVALCASCADE_DATABASE_URL": (("database_url",), str),
    "EVALCASCADE_API_TOKEN": (("api_token",), str),
    "EVALCASCADE_OPENROUTER_BASE_URL": (("jev", "base_url"), str),
    "EVALCASCADE_JEV_MODEL": (("jev", "model"), str),
    "EVALCASCADE_JEV_SURFACE": (("jev", "surface"), str),
    "EVALCASCADE_JEV_TIMEOUT": (("jev", "timeout_s"), float),
    "EVALCASCADE_JEV_MAX_RETRIES": (("jev", "max_retries"), int),
    "EVALCASCADE_JEV_BATCH": (("jev", "batch"), bool),
    "EVALCASCADE_JUDGE_PROVIDER": (("judge", "provider"), str),
    "EVALCASCADE_JUDGE_MODEL": (("judge", "model"), str),
    "EVALCASCADE_JUDGE_BASE_URL": (("judge", "base_url"), str),
    "EVALCASCADE_JUDGE_API_KEY": (("judge", "api_key"), str),
    "EVALCASCADE_JUDGE_TIMEOUT": (("judge", "timeout_s"), float),
    "EVALCASCADE_JUDGE_MAX_RETRIES": (("judge", "max_retries"), int),
    "EVALCASCADE_JUDGE_TEMPERATURE": (("judge", "temperature"), float),
    "EVALCASCADE_JUDGE_MAX_TOKENS": (("judge", "max_tokens"), int),
    "EVALCASCADE_JUDGE_STRUCTURED_OUTPUT": (("judge", "structured_output"), str),
    "EVALCASCADE_JUDGE_EXTRA_BODY": (("judge", "extra_body"), dict),
    "EVALCASCADE_JUDGE_INPUT_COST_PER_MTOK": (("judge", "input_cost_per_mtok"), float),
    "EVALCASCADE_JUDGE_OUTPUT_COST_PER_MTOK": (("judge", "output_cost_per_mtok"), float),
    "EVALCASCADE_JUDGE_REQUIRE_API_KEY": (("judge", "require_api_key"), bool),
    "EVALCASCADE_PRIMARY": (("policy", "primary"), str),
    "EVALCASCADE_FALLBACK": (("policy", "fallback"), str),
    "EVALCASCADE_ESCALATE_BELOW": (("policy", "escalate_below"), float),
}


def _apply_env(data: dict[str, Any], env: Mapping[str, str]) -> None:
    for var, (path, kind) in _ENV_MAP.items():
        raw = env.get(var)
        if raw is None or raw == "":
            continue
        value: Any
        if kind is bool:
            value = raw.strip().lower() in {"1", "true", "yes", "on"}
        elif kind is dict:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ConfigurationError(f"{var} must be a JSON object") from exc
        elif (
            kind is str and path[-1] in {"primary", "fallback"} and raw.lower() in {"none", "null"}
        ):
            value = None
        else:
            value = raw
        target = data
        for part in path[:-1]:
            target = target.setdefault(part, {})
        target[path[-1]] = value
    # A custom judge endpoint implies the OpenAI-compatible provider.
    judge = data.get("judge", {})
    if env.get("EVALCASCADE_JUDGE_BASE_URL") and "EVALCASCADE_JUDGE_PROVIDER" not in env:
        judge["provider"] = "openai_compatible"


def _deep_update(target: dict[str, Any], updates: Mapping[str, Any]) -> None:
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value
