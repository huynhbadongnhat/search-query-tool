"""Shared term normalization and audit helpers."""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List


CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
WHITESPACE_RE = re.compile(r"\s+")


def normalize_term(term: str | None) -> str:
    """Normalize a human-entered or vocabulary term without changing meaning."""
    if term is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(term))
    normalized = CONTROL_CHARS_RE.sub(" ", normalized)
    normalized = WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def is_likely_query_term(term: str | None, *, max_length: int = 120) -> bool:
    """Return whether a term is suitable for a database query candidate."""
    normalized = normalize_term(term)
    if len(normalized) < 2 or len(normalized) > max_length:
        return False

    lowered = normalized.lower()
    noisy_fragments = (
        "product containing",
        "producto que contiene",
        "mg/1 vial",
        "milligram/1",
        "clinical drug",
        "(body structure)",
        "(disorder)",
        "(finding)",
    )
    if any(fragment in lowered for fragment in noisy_fragments):
        return False

    # Require at least one letter or digit. This keeps terms such as beta blockers
    # while rejecting punctuation-only artifacts.
    return any(ch.isalnum() for ch in normalized)


def dedupe_terms(terms: Iterable[str | None], *, max_length: int = 120) -> List[str]:
    """Normalize and deduplicate terms case-insensitively while preserving order."""
    seen: set[str] = set()
    unique: List[str] = []
    for term in terms:
        normalized = normalize_term(term)
        if not is_likely_query_term(normalized, max_length=max_length):
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique


def split_comma_terms(value: str | None) -> List[str]:
    """Parse comma-separated manual terms."""
    if not value:
        return []
    return dedupe_terms(part for part in value.split(","))


def json_safe_text(value: str | None) -> str:
    """Compact text before including it in prompts or audit output."""
    return normalize_term(value)
