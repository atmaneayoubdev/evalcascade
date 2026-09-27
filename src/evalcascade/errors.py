"""Exception hierarchy.

Every error message that can carry provider text is passed through :func:`redact` so that
API keys and bearer tokens can never leak through exception strings or logs.
"""

from __future__ import annotations

from evalcascade.redaction import redact


class EvalCascadeError(Exception):
    """Base class for all EvalCascade errors."""

    def __init__(self, message: str) -> None:
        super().__init__(redact(message))


class ConfigurationError(EvalCascadeError):
    """Missing or invalid configuration (e.g. an API key is not set)."""


class DatasetError(EvalCascadeError):
    """A dataset file is missing, malformed or fails validation."""


class NotFoundError(EvalCascadeError):
    """A dataset or experiment reference could not be resolved."""


class ProviderError(EvalCascadeError):
    """An upstream provider (OpenRouter, an OpenAI-compatible endpoint, ...) failed."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
        retryable: bool = False,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable
        self.request_id = request_id

    def __str__(self) -> str:
        base = super().__str__()
        status = f" (HTTP {self.status_code})" if self.status_code is not None else ""
        return f"{self.provider}{status}: {base}"


class AuthenticationError(ProviderError):
    """HTTP 401/403 — the API key is missing, invalid or lacks permission."""


class InsufficientCreditsError(ProviderError):
    """HTTP 402 — the account has no remaining credits."""


class RateLimitError(ProviderError):
    """HTTP 429 after all retries were exhausted."""


class ProviderTimeoutError(ProviderError):
    """The request did not complete within the configured timeout."""


class ResponseValidationError(ProviderError):
    """The provider answered, but the payload did not match the expected schema."""
