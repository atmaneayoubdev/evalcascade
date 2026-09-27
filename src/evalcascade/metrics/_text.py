"""Text utilities shared by metrics (normalization, sentences, citations, truncation)."""

from __future__ import annotations

import json
import re
import string
import unicodedata
from typing import Any

DEFAULT_MAX_CHARS = 4000

_ARTICLES = re.compile(r"\b(a|an|the)\b", re.IGNORECASE)
_WS = re.compile(r"\s+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")
_NUMERIC_CITATION = re.compile(r"\[(\d{1,3}(?:\s*[,;-]\s*\d{1,3})*)\]")
_CITATION_PATTERNS = (
    _NUMERIC_CITATION,
    re.compile(r"\[(?:doc|source|ref|passage|context)[\s_:#-]?\w+\]", re.IGNORECASE),
    re.compile(r"\((?:source|ref|see)s?:\s*[^)]+\)", re.IGNORECASE),
    re.compile(r"\[\^\d+\]"),  # markdown footnotes
    re.compile(r"https?://[^\s)\]>]+"),
)


def normalize_answer(text: str) -> str:
    """SQuAD-style normalization: lowercase, strip punctuation/articles/extra whitespace."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = "".join(ch for ch in text if ch not in set(string.punctuation))
    text = _ARTICLES.sub(" ", text)
    return _WS.sub(" ", text).strip()


def matches_reference(output: str, references: list[str], mode: str) -> str | None:
    """Return the matching reference, or ``None``. ``mode`` is exact | normalized | contains."""
    for ref in references:
        if mode == "exact" and output.strip() == ref.strip():
            return ref
        if mode == "normalized" and normalize_answer(output) == normalize_answer(ref):
            return ref
        if mode == "contains":
            norm_ref = normalize_answer(ref)
            if norm_ref and re.search(
                rf"(?<!\w){re.escape(norm_ref)}(?!\w)", normalize_answer(output)
            ):
                return ref
    return None


def split_sentences(text: str) -> list[str]:
    """Lightweight sentence splitter (no model, no dependency)."""
    parts: list[str] = []
    for block in re.split(r"\n\s*\n|\n(?=\s*[-*•\d]+[.)]?\s)", text.strip()):
        parts.extend(s.strip() for s in _SENTENCE.split(block.strip()) if s.strip())
    return parts


def find_citations(text: str) -> list[str]:
    """All citation markers found in ``text`` (numeric, named, footnotes, URLs)."""
    found: list[str] = []
    for pattern in _CITATION_PATTERNS:
        found.extend(m.group(0) for m in pattern.finditer(text))
    return found


def numeric_citations(sentence: str) -> list[int]:
    """Numeric citation indices in a sentence: ``[1]``, ``[2, 3]``, ``[1-3]``."""
    out: list[int] = []
    for match in _NUMERIC_CITATION.finditer(sentence):
        for part in re.split(r"\s*[,;]\s*", match.group(1)):
            if "-" in part:
                lo, hi = (int(x) for x in part.split("-", 1))
                out.extend(range(lo, hi + 1) if 0 < hi - lo < 50 else [lo, hi])
            else:
                out.append(int(part))
    return out


def strip_citations(sentence: str) -> str:
    text = _WS.sub(" ", _NUMERIC_CITATION.sub("", sentence)).strip()
    return re.sub(r"\s+([.,;:!?])", r"\1", text)


def truncate(text: str | None, max_chars: int = DEFAULT_MAX_CHARS) -> str | None:
    if text is None or len(text) <= max_chars:
        return text
    keep = max(0, max_chars - 40)
    return f"{text[:keep]} …[truncated {len(text) - keep} chars]"


def compact(value: Any, max_chars: int = 1000) -> Any:
    """Truncate a JSON-able value's string form for inclusion in a judgment state."""
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return truncate(value, max_chars)
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return value
    return truncate(text, max_chars)


# ---------------------------------------------------------------------------
# Deterministic safety signals
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "api_key": re.compile(r"\b(?:sk|pk|rk)-(?:live-|test-|proj-|or-v1-)?[A-Za-z0-9]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "slack_token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "us_ssn": re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"),
}
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def find_sensitive_data(text: str) -> list[str]:
    """Kinds of secrets / sensitive identifiers present in ``text`` (never the values)."""
    kinds = [name for name, pattern in _SECRET_PATTERNS.items() if pattern.search(text)]
    for match in _CARD.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn(digits):
            kinds.append("payment_card")
            break
    return kinds
