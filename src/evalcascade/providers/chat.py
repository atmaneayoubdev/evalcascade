"""Client for OpenAI-compatible ``/chat/completions`` endpoints.

Works with OpenRouter (``https://openrouter.ai/api/v1``) and any server that implements the
OpenAI chat completions wire format (vLLM, SGLang, llama.cpp, LiteLLM, Azure-compatible
gateways, ...). Usage and — when the provider reports it (OpenRouter does) — cost are parsed.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from pydantic import BaseModel, SecretStr

from evalcascade.errors import ResponseValidationError
from evalcascade.providers.http import HTTPClient, RetryPolicy, Sleep


class ChatUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float | None = None


class ChatResult(BaseModel):
    id: str | None = None
    model: str | None = None
    provider: str | None = None
    content: str
    reasoning: str | None = None
    finish_reason: str | None = None
    usage: ChatUsage
    latency_ms: float
    attempts: int


class ChatCompletionsClient:
    """Minimal async chat completions client."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr | str | None,
        provider: str = "openai_compatible",
        timeout_s: float = 60.0,
        max_retries: int = 3,
        max_concurrency: int = 8,
        headers: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep | None = None,
    ) -> None:
        key = SecretStr(api_key) if isinstance(api_key, str) else api_key
        self._http = HTTPClient(
            provider=provider,
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
    def provider(self) -> str:
        return self._http.provider

    @property
    def base_url(self) -> str:
        return self._http.base_url

    @property
    def configured(self) -> bool:
        return self._http.has_credentials

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format is not None:
            payload["response_format"] = response_format
        if extra_body:
            payload.update(extra_body)

        started = time.perf_counter()
        http = await self._http.post_json("/chat/completions", payload)
        data = http.data
        try:
            choice = data["choices"][0]
            message = choice.get("message") or {}
            content = message.get("content")
        except (KeyError, IndexError, TypeError) as exc:
            raise ResponseValidationError(
                "chat completion response has no choices",
                provider=self.provider,
                status_code=http.status_code,
            ) from exc
        if isinstance(content, list):  # content parts
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        if not isinstance(content, str) or not content.strip():
            raise ResponseValidationError(
                "chat completion returned empty content "
                f"(finish_reason={choice.get('finish_reason')})",
                provider=self.provider,
                status_code=http.status_code,
            )
        reasoning = message.get("reasoning") or message.get("reasoning_content")
        return ChatResult(
            id=data.get("id"),
            model=data.get("model"),
            provider=data.get("provider"),
            content=content,
            reasoning=reasoning if isinstance(reasoning, str) else None,
            finish_reason=choice.get("finish_reason"),
            usage=_parse_usage(data.get("usage")),
            latency_ms=(time.perf_counter() - started) * 1000,
            attempts=http.attempts,
        )

    async def aclose(self) -> None:
        await self._http.aclose()


def _parse_usage(raw: Any) -> ChatUsage:
    if not isinstance(raw, dict):
        return ChatUsage()
    details = raw.get("completion_tokens_details") or {}
    cost = raw.get("cost")
    return ChatUsage(
        prompt_tokens=int(raw.get("prompt_tokens") or 0),
        completion_tokens=int(raw.get("completion_tokens") or 0),
        reasoning_tokens=int(details.get("reasoning_tokens") or 0)
        if isinstance(details, dict)
        else 0,
        cost=float(cost) if isinstance(cost, int | float) else None,
    )
