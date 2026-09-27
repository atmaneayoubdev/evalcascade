"""JevClient / HTTP layer: request shape, parsing, retries, errors and secret hygiene."""

from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx

from evalcascade.errors import (
    AuthenticationError,
    ConfigurationError,
    InsufficientCreditsError,
    ProviderError,
    ProviderTimeoutError,
    RateLimitError,
    ResponseValidationError,
)
from evalcascade.providers.http import RetryPolicy
from evalcascade.providers.jev import ChoiceAnswer, JevClient, NoulAnswer, ScoreAnswer
from tests.conftest import FAKE_KEY

URL = "https://openrouter.ai/api/alpha/decisions"
QUESTIONS = {
    "ok": {"type": "noul", "instructions": "Is it ok?", "criteria": {"true": "yes", "false": "no"}},
    "kind": {"type": "choice", "instructions": "Kind?", "criteria": {"a": "A", "b": "B"}},
    "grade": {"type": "score", "instructions": "Grade?", "criteria": ["bad", "ok", "good"]},
}
RESPONSE = {
    "model": "typesafe/jev-1.13-20260917",
    "answers": {
        "ok": {"type": "noul", "noul": 0.93},
        "kind": {
            "type": "choice",
            "choice": "a",
            "confidence": 0.8,
            "probabilities": {"a": 0.9, "b": 0.1},
        },
        "grade": {
            "type": "score",
            "score": 1.7,
            "confidence": 0.66,
            "probabilities": {"0": 0.05, "1": 0.2, "2": 0.75},
            "legend": {"0": "bad", "1": "ok", "2": "good"},
        },
    },
    "usage": {"input_tokens": 443, "output_tokens": 71, "cost": 1.8606e-05},
    "id": "gen-dec-123",
    "provider": "TypeSafe",
}


async def _no_sleep(_: float) -> None:
    return None


def client(**kwargs: object) -> JevClient:
    return JevClient(FAKE_KEY, sleep=_no_sleep, **kwargs)  # type: ignore[arg-type]


@respx.mock
async def test_request_shape_and_parsing() -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=RESPONSE))
    result = await client().decide({"answer": "Paris"}, QUESTIONS)
    request = route.calls.last.request
    assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
    body = json.loads(request.content)
    assert body == {
        "model": "typesafe/jev-1.13",
        "state": {"answer": "Paris"},
        "questions": QUESTIONS,
    }
    r = result.response
    assert (
        r.model == "typesafe/jev-1.13-20260917"
        and r.id == "gen-dec-123"
        and r.provider == "TypeSafe"
    )
    assert isinstance(r.answers["ok"], NoulAnswer) and r.answers["ok"].noul == 0.93
    assert isinstance(r.answers["kind"], ChoiceAnswer) and r.answers["kind"].probabilities == {
        "a": 0.9,
        "b": 0.1,
    }
    assert isinstance(r.answers["grade"], ScoreAnswer) and r.answers["grade"].score == 1.7
    assert r.usage.cost == pytest.approx(1.8606e-05) and r.usage.input_tokens == 443
    assert result.attempts == 1 and result.latency_ms >= 0


@respx.mock
async def test_systemone_surface_and_custom_model() -> None:
    route = respx.post("https://openrouter.ai/api/v1/systemone").mock(
        return_value=httpx.Response(200, json=RESPONSE)
    )
    await client(surface="systemone", model="~typesafe/jev-latest").decide("text", QUESTIONS)
    assert json.loads(route.calls.last.request.content)["model"] == "~typesafe/jev-latest"


@respx.mock
async def test_optional_answer_fields_may_be_missing() -> None:
    minimal = {
        "model": "m",
        "answers": {"kind": {"type": "choice", "choice": "b"}},
        "usage": {"input_tokens": 1, "output_tokens": 0},
    }
    respx.post(URL).mock(return_value=httpx.Response(200, json=minimal))
    result = await client().decide("s", {"kind": QUESTIONS["kind"]})
    answer = result.response.answers["kind"]
    assert (
        isinstance(answer, ChoiceAnswer)
        and answer.confidence is None
        and answer.probabilities is None
    )
    assert result.response.usage.cost is None


@pytest.mark.parametrize("status", [429, 500, 502, 503, 524, 529])
@respx.mock
async def test_retries_transient_statuses(status: int) -> None:
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(status, json={"error": {"code": status, "message": "try again"}}),
            httpx.Response(200, json=RESPONSE),
        ]
    )
    result = await client().decide("s", QUESTIONS)
    assert route.call_count == 2 and result.attempts == 2


@respx.mock
async def test_exponential_backoff_and_retry_after() -> None:
    delays: list[float] = []

    async def record(d: float) -> None:
        delays.append(d)

    respx.post(URL).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, json=RESPONSE),
        ]
    )
    jev = JevClient(FAKE_KEY, sleep=record)
    jev._http.retry = RetryPolicy(max_retries=3, base_delay=0.5, jitter=0.0)
    await jev.decide("s", QUESTIONS)
    assert delays == [0.5, 7.0]


def test_backoff_grows_and_is_capped() -> None:
    policy = RetryPolicy(base_delay=0.5, max_delay=4.0, jitter=0.0)
    assert [policy.delay(i) for i in range(5)] == [0.5, 1.0, 2.0, 4.0, 4.0]


@respx.mock
async def test_gives_up_after_max_retries_with_rate_limit_error() -> None:
    route = respx.post(URL).mock(
        return_value=httpx.Response(429, json={"error": {"code": 429, "message": "slow down"}})
    )
    with pytest.raises(RateLimitError, match="slow down"):
        await client(max_retries=2).decide("s", QUESTIONS)
    assert route.call_count == 3


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (400, ProviderError),
        (401, AuthenticationError),
        (403, AuthenticationError),
        (402, InsufficientCreditsError),
        (404, ProviderError),
        (413, ProviderError),
    ],
)
@respx.mock
async def test_non_retryable_statuses_fail_fast(status: int, exc: type[Exception]) -> None:
    route = respx.post(URL).mock(
        return_value=httpx.Response(status, json={"error": {"code": status, "message": "nope"}})
    )
    with pytest.raises(exc) as info:
        await client().decide("s", QUESTIONS)
    assert route.call_count == 1
    assert isinstance(info.value, ProviderError) and info.value.status_code == status


@respx.mock
async def test_timeouts_are_retried_then_raised() -> None:
    route = respx.post(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderTimeoutError, match="timed out"):
        await client(max_retries=1, timeout_s=5).decide("s", QUESTIONS)
    assert route.call_count == 2


@respx.mock
async def test_connection_errors_are_retried() -> None:
    respx.post(URL).mock(
        side_effect=[httpx.ConnectError("refused"), httpx.Response(200, json=RESPONSE)]
    )
    assert (await client().decide("s", QUESTIONS)).attempts == 2


@respx.mock
async def test_invalid_json_and_schema_raise_validation_errors() -> None:
    respx.post(URL).mock(return_value=httpx.Response(200, text="<html>oops</html>"))
    with pytest.raises(ResponseValidationError, match="not valid JSON"):
        await client().decide("s", QUESTIONS)
    respx.post(URL).mock(
        return_value=httpx.Response(200, json={"model": "m", "answers": {"ok": {"type": "noul"}}})
    )
    with pytest.raises(ResponseValidationError, match="unexpected Decisions response shape"):
        await client().decide("s", QUESTIONS)


@respx.mock
async def test_error_payload_with_http_200_is_an_error() -> None:
    respx.post(URL).mock(
        return_value=httpx.Response(
            200, json={"error": {"code": 502, "message": "provider failed"}}
        )
    )
    with pytest.raises(ProviderError, match="provider failed"):
        await client(max_retries=0).decide("s", QUESTIONS)


async def test_missing_key_is_a_configuration_error() -> None:
    with pytest.raises(ConfigurationError, match="OPENROUTER_API_KEY"):
        await JevClient(None).decide("s", QUESTIONS)


async def test_invalid_questions_are_rejected_locally() -> None:
    with pytest.raises(ConfigurationError, match="invalid Decisions request"):
        await client().decide("s", {"q": {"type": "score", "instructions": "x", "criteria": []}})


@respx.mock
async def test_api_key_never_leaks_into_errors_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    # A misbehaving upstream echoes the Authorization header back in its error message.
    echoed = f"invalid header Authorization: Bearer {FAKE_KEY}"
    respx.post(URL).mock(
        return_value=httpx.Response(401, json={"error": {"code": 401, "message": echoed}})
    )
    caplog.set_level(logging.DEBUG, logger="evalcascade")
    with pytest.raises(AuthenticationError) as info:
        await client().decide("s", QUESTIONS)
    assert FAKE_KEY not in str(info.value)
    assert "[REDACTED]" in str(info.value)
    assert FAKE_KEY not in caplog.text
    assert FAKE_KEY not in repr(client().__dict__)
