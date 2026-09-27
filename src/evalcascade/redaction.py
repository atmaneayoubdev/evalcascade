"""Logging helpers with secret redaction.

EvalCascade never logs request headers. As a second line of defence, every record emitted
under the ``evalcascade`` logger namespace is scrubbed of anything that looks like a
credential (bearer tokens, ``sk-...`` style keys, ``api_key=...`` pairs).
"""

from __future__ import annotations

import logging
import re

_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Authorization: Bearer <token>
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    # OpenRouter / OpenAI style keys: sk-or-v1-..., sk-proj-..., sk-...
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    # key=value / "key": "value" pairs for common credential names
    re.compile(
        r"(?i)((?:api[_-]?key|authorization|token|secret|password)[\"']?\s*[:=]\s*[\"']?)"
        r"(?:bearer\s+)?[^\s\"',}]{6,}"
    ),
)

REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    """Return ``text`` with anything resembling a credential replaced by ``[REDACTED]``."""
    if not text:
        return text
    out = text
    for pattern in _PATTERNS:
        if pattern.groups:
            out = pattern.sub(lambda m: m.group(1) + REDACTED, out)
        else:
            out = pattern.sub(REDACTED, out)
    return out


class RedactingFilter(logging.Filter):
    """Logging filter that scrubs credentials from the formatted message."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - malformed record, let logging handle it
            return True
        cleaned = redact(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = None
        return True


def get_logger(name: str = "evalcascade") -> logging.Logger:
    """Return a logger under the ``evalcascade`` namespace with redaction installed."""
    logger = logging.getLogger(name)
    root = logging.getLogger("evalcascade")
    if not any(isinstance(f, RedactingFilter) for f in root.filters):
        root.addFilter(RedactingFilter())
    if logger is not root and not any(isinstance(f, RedactingFilter) for f in logger.filters):
        logger.addFilter(RedactingFilter())
    return logger
