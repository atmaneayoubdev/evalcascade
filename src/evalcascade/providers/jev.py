"""Typed client for TypeSafe Jev via OpenRouter's Decisions API.

Verified against OpenRouter's OpenAPI spec and live responses (2026-09-27):

* ``POST https://openrouter.ai/api/alpha/decisions`` (surface ``"decisions"``, default)
* ``POST https://openrouter.ai/api/v1/systemone`` (surface ``"systemone"``, TypeSafe-SDK compatible)

Both accept ``{model, state, questions}`` where each question is one of:

* ``noul``   — ``{instructions, criteria?: {true, false}}``  → ``{noul: P(true)}``
* ``choice`` — ``{instructions, criteria: {option: description}}`` →
  ``{choice, confidence?, probabilities?}``
* ``score``  — ``{instructions, criteria: [level_0, ...]}`` →
  ``{score, confidence?, probabilities?, legend?}``

and return ``{id, model, provider, answers, usage: {input_tokens, output_tokens, cost?}}``.
"""

from __future__ import annotations

import time
from typing import Annotated, Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from evalcascade.config import DEFAULT_JEV_MODEL, OPENROUTER_API_BASE
from evalcascade.errors import ConfigurationError, ResponseValidationError
from evalcascade.providers.http import HTTPClient, RetryPolicy, Sleep

JevSurface = Literal["decisions", "systemone"]
SURFACE_PATHS: dict[str, str] = {
    "decisions": "/alpha/decisions",
    "systemone": "/v1/systemone",
}
StructuredGuidance = str | dict[str, Any] | list[Any]


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class NoulCriteria(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    true_: StructuredGuidance = Field(alias="true")
    false_: StructuredGuidance = Field(alias="false")


class NoulQuestion(BaseModel):
    type: Literal["noul"] = "noul"
    instructions: StructuredGuidance
    criteria: NoulCriteria | None = None


class ChoiceQuestion(BaseModel):
    type: Literal["choice"] = "choice"
    instructions: StructuredGuidance
    criteria: dict[str, StructuredGuidance | None]


class ScoreQuestion(BaseModel):
    type: Literal["score"] = "score"
    instructions: StructuredGuidance
    criteria: list[StructuredGuidance] = Field(min_length=1)


DecisionQuestion = Annotated[NoulQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="type")]


class DecisionsRequest(BaseModel):
    model: str
    state: str | dict[str, Any] | list[Any]
    questions: dict[str, DecisionQuestion] = Field(min_length=1)
    session_id: str | None = Field(default=None, max_length=256)
    user: str | None = Field(default=None, max_length=256)

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class NoulAnswer(BaseModel):
    type: Literal["noul"]
    noul: float


class ChoiceAnswer(BaseModel):
    type: Literal["choice"]
    choice: str
    confidence: float | None = None
    probabilities: dict[str, float] | None = None


class ScoreAnswer(BaseModel):
    type: Literal["score"]
    score: float
    confidence: float | None = None
    probabilities: dict[str, float] | None = None
    legend: dict[str, Any] | None = None


DecisionAnswer = Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")]


class DecisionsUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = None


class DecisionsResponse(BaseModel):
    id: str | None = None
    model: str
    provider: str | None = None
    answers: dict[str, DecisionAnswer]
    usage: DecisionsUsage = Field(default_factory=DecisionsUsage)


class DecisionResult(BaseModel):
    """A validated Decisions response plus client-side measurements."""

    response: DecisionsResponse
    latency_ms: float
    attempts: int


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class JevClient:
    """Async client for Jev decisions."""

    def __init__(
        self,
        api_key: SecretStr | str | None,
        *,
        model: str = DEFAULT_JEV_MODEL,
        surface: JevSurface = "decisions",
        base_url: str = OPENROUTER_API_BASE,
        timeout_s: float = 30.0,
        max_retries: int = 3,
        max_concurrency: int = 8,
        app_url: str | None = None,
        app_title: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep | None = None,
    ) -> None:
        if surface not in SURFACE_PATHS:
            raise ConfigurationError(f"unknown Jev surface {surface!r}; use decisions or systemone")
        key = SecretStr(api_key) if isinstance(api_key, str) else api_key
        self.model = model
        self.surface: JevSurface = surface
        headers = {}
        if app_url:
            headers["HTTP-Referer"] = app_url
        if app_title:
            headers["X-Title"] = app_title
        self._http = HTTPClient(
            provider="openrouter/jev",
            base_url=base_url,
            api_key=key,
            timeout_s=timeout_s,
            retry=RetryPolicy(max_retries=max_retries),
            max_concurrency=max_concurrency,
            headers=headers,
            transport=transport,
            sleep=sleep,
        )

    @property
    def base_url(self) -> str:
        return self._http.base_url

    @property
    def configured(self) -> bool:
        return self._http.has_credentials

    @property
    def endpoint(self) -> str:
        return f"{self._http.base_url}{SURFACE_PATHS[self.surface]}"

    async def decide(
        self,
        state: str | dict[str, Any] | list[Any],
        questions: dict[str, DecisionQuestion] | dict[str, dict[str, Any]],
        *,
        model: str | None = None,
        session_id: str | None = None,
    ) -> DecisionResult:
        """Submit one Decisions request and validate the response."""
        if not self.configured:
            raise ConfigurationError(
                "OPENROUTER_API_KEY is not set — it is required for the Jev evaluator"
            )
        try:
            request = DecisionsRequest(
                model=model or self.model,
                state=state,
                questions=questions,  # type: ignore[arg-type]
                session_id=session_id,
            )
        except ValidationError as exc:
            raise ConfigurationError(f"invalid Decisions request: {exc}") from exc

        started = time.perf_counter()
        http = await self._http.post_json(SURFACE_PATHS[self.surface], request.payload())
        try:
            response = DecisionsResponse.model_validate(http.data)
        except ValidationError as exc:
            raise ResponseValidationError(
                f"unexpected Decisions response shape: {_short_errors(exc)}",
                provider=self._http.provider,
                status_code=http.status_code,
                request_id=http.data.get("id") if isinstance(http.data.get("id"), str) else None,
            ) from exc
        return DecisionResult(
            response=response,
            latency_ms=(time.perf_counter() - started) * 1000,
            attempts=http.attempts,
        )

    async def aclose(self) -> None:
        await self._http.aclose()


def _short_errors(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:5]:
        loc = ".".join(str(p) for p in err["loc"])
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)
