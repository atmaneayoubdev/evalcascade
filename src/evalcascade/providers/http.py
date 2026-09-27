"""A small async JSON-over-HTTP client with retries, backoff and secret-safe errors.

* Timeouts on every request.
* Exponential backoff with jitter on transient failures (timeouts, connection errors,
  408/409/425/429/5xx and Cloudflare 52x), honouring ``Retry-After``.
* Non-retryable failures (400/401/402/403/404/413) fail fast with a typed exception.
* Request headers are never logged; error messages are redacted.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import SecretStr

from evalcascade._version import __version__
from evalcascade.errors import (
    AuthenticationError,
    InsufficientCreditsError,
    ProviderError,
    ProviderTimeoutError,
    RateLimitError,
    ResponseValidationError,
)
from evalcascade.redaction import get_logger, redact

logger = get_logger("evalcascade.providers.http")

Sleep = Callable[[float], Awaitable[None]]

RETRYABLE_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 520, 521, 522, 524, 529})


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff: ``min(max_delay, base_delay * 2**attempt) ± jitter``."""

    max_retries: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0
    jitter: float = 0.25
    retry_statuses: frozenset[int] = field(default=RETRYABLE_STATUSES)

    def delay(self, attempt: int, retry_after: float | None = None) -> float:
        if retry_after is not None:
            return min(self.max_delay * 4, max(0.0, retry_after))
        backoff = min(self.max_delay, self.base_delay * (2.0**attempt))
        spread = backoff * self.jitter
        return max(0.0, backoff + random.uniform(-spread, spread))  # noqa: S311 - not crypto


@dataclass
class HTTPResponse:
    data: dict[str, Any]
    status_code: int
    latency_ms: float
    attempts: int


class HTTPClient:
    """JSON client bound to one provider base URL."""

    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: SecretStr | None,
        timeout_s: float,
        retry: RetryPolicy | None = None,
        max_concurrency: int = 8,
        headers: Mapping[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep | None = None,
    ) -> None:
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.timeout_s = timeout_s
        self.retry = retry or RetryPolicy()
        self.max_concurrency = max_concurrency
        self._extra_headers = dict(headers or {})
        self._transport = transport
        self._sleep: Sleep = sleep or asyncio.sleep
        self._client: httpx.AsyncClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._semaphore: asyncio.Semaphore | None = None

    # -- lifecycle ------------------------------------------------------------------

    @property
    def has_credentials(self) -> bool:
        return self._api_key is not None and bool(self._api_key.get_secret_value())

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"evalcascade/{__version__}",
            **self._extra_headers,
        }
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key.get_secret_value()}"
        return headers

    def _ensure_client(self) -> tuple[httpx.AsyncClient, asyncio.Semaphore]:
        loop = asyncio.get_running_loop()
        if self._client is None or self._loop is not loop or self._client.is_closed:
            # httpx clients are bound to the event loop they were created on.
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout_s, connect=min(10.0, self.timeout_s)),
                transport=self._transport,
                limits=httpx.Limits(max_connections=max(self.max_concurrency, 4)),
            )
            self._semaphore = asyncio.Semaphore(self.max_concurrency)
            self._loop = loop
        assert self._semaphore is not None
        return self._client, self._semaphore

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None and not client.is_closed:
            with contextlib.suppress(RuntimeError):  # loop already closed
                await client.aclose()

    # -- requests ---------------------------------------------------------------------

    async def post_json(self, path: str, payload: Mapping[str, Any]) -> HTTPResponse:
        return await self._request("POST", path, payload)

    async def get_json(self, path: str) -> HTTPResponse:
        return await self._request("GET", path, None)

    async def _request(
        self, method: str, path: str, payload: Mapping[str, Any] | None
    ) -> HTTPResponse:
        client, semaphore = self._ensure_client()
        started = time.perf_counter()
        attempt = 0
        async with semaphore:
            while True:
                attempt_started = time.perf_counter()
                retry_after: float | None = None
                try:
                    response = await client.request(
                        method, path, json=payload, headers=self._headers()
                    )
                except httpx.TimeoutException as exc:
                    error: ProviderError = ProviderTimeoutError(
                        f"request timed out after {self.timeout_s:.0f}s ({type(exc).__name__})",
                        provider=self.provider,
                        retryable=True,
                    )
                except httpx.TransportError as exc:
                    error = ProviderError(
                        f"connection error: {type(exc).__name__}: {exc}",
                        provider=self.provider,
                        retryable=True,
                    )
                else:
                    elapsed = (time.perf_counter() - attempt_started) * 1000
                    logger.debug(
                        "%s %s%s -> %s in %.0fms (attempt %d)",
                        method,
                        self.base_url,
                        path,
                        response.status_code,
                        elapsed,
                        attempt + 1,
                    )
                    if response.status_code < 400:
                        data = _parse_json(response, self.provider)
                        embedded = _embedded_error(data, self.provider, response.status_code)
                        if embedded is None:
                            return HTTPResponse(
                                data=data,
                                status_code=response.status_code,
                                latency_ms=(time.perf_counter() - started) * 1000,
                                attempts=attempt + 1,
                            )
                        error = embedded
                    else:
                        error = _status_error(response, self.provider, self.retry.retry_statuses)
                        retry_after = _retry_after_seconds(response)

                if not error.retryable or attempt >= self.retry.max_retries:
                    if isinstance(error, ProviderError) and error.status_code == 429:
                        raise RateLimitError(
                            f"rate limited after {attempt + 1} attempt(s): {error.args[0]}",
                            provider=self.provider,
                            status_code=429,
                        ) from None
                    raise error
                delay = self.retry.delay(attempt, retry_after)
                logger.info(
                    "%s: retrying %s %s in %.2fs (attempt %d/%d): %s",
                    self.provider,
                    method,
                    path,
                    delay,
                    attempt + 1,
                    self.retry.max_retries + 1,
                    error.args[0],
                )
                attempt += 1
                await self._sleep(delay)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _parse_json(response: httpx.Response, provider: str) -> dict[str, Any]:
    try:
        data = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ResponseValidationError(
            f"response is not valid JSON: {response.text[:200]!r}",
            provider=provider,
            status_code=response.status_code,
        ) from exc
    if not isinstance(data, dict):
        raise ResponseValidationError(
            "response JSON is not an object", provider=provider, status_code=response.status_code
        )
    return data


def _error_message(data: Any, fallback: str) -> tuple[str, Any]:
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            message = err.get("message") or fallback
            return str(message)[:800], err.get("code")
        if isinstance(err, str):
            return err[:800], None
        if isinstance(data.get("detail"), str):
            return data["detail"][:800], None
    return fallback, None


def _embedded_error(data: dict[str, Any], provider: str, status: int) -> ProviderError | None:
    """Some gateways return HTTP 200 with an ``error`` object; treat it as a failure."""
    if "error" not in data or not data["error"]:
        return None
    if any(k in data for k in ("answers", "choices")):
        return None
    message, code = _error_message(data, "provider returned an error")
    code_int = code if isinstance(code, int) else None
    return ProviderError(
        message,
        provider=provider,
        status_code=code_int or status,
        retryable=code_int in RETRYABLE_STATUSES if code_int else False,
    )


def _status_error(
    response: httpx.Response, provider: str, retry_statuses: frozenset[int]
) -> ProviderError:
    status = response.status_code
    try:
        body: Any = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = None
    message, _ = _error_message(body, response.reason_phrase or f"HTTP {status}")
    message = redact(message)
    kwargs: dict[str, Any] = {"provider": provider, "status_code": status}
    if status in (401, 403):
        return AuthenticationError(
            f"{message} — check that the API key is set and valid", retryable=False, **kwargs
        )
    if status == 402:
        return InsufficientCreditsError(message, retryable=False, **kwargs)
    return ProviderError(message, retryable=status in retry_statuses, **kwargs)


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
