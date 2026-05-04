"""Shared term normalization and audit helpers."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, List, Sequence


CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
WHITESPACE_RE = re.compile(r"\s+")
ALLOWED_MEDICAL_SYMBOLS = {"α", "β", "γ", "δ", "κ", "λ", "μ", "ω"}


def normalize_term(term: str | None) -> str:
    """Normalize a human-entered or vocabulary term without changing meaning."""
    if term is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(term))
    normalized = CONTROL_CHARS_RE.sub(" ", normalized)
    normalized = WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def is_english_like_term(term: str | None) -> bool:
    """Heuristic filter for terms that can be used in English search strategies."""
    normalized = normalize_term(term)
    if not normalized:
        return False

    has_letter = False
    for char in normalized:
        if char in ALLOWED_MEDICAL_SYMBOLS:
            has_letter = True
            continue
        if not char.isalpha():
            continue
        has_letter = True
        try:
            name = unicodedata.name(char)
        except ValueError:
            return False
        if "LATIN" not in name:
            return False

    return has_letter


def is_likely_query_term(
    term: str | None,
    *,
    max_length: int = 120,
    english_only: bool = False,
) -> bool:
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
    if not any(ch.isalnum() for ch in normalized):
        return False

    if english_only and not is_english_like_term(normalized):
        return False

    return True


def dedupe_terms(
    terms: Iterable[str | None],
    *,
    max_length: int = 120,
    english_only: bool = False,
) -> List[str]:
    """Normalize and deduplicate terms case-insensitively while preserving order."""
    seen: set[str] = set()
    unique: List[str] = []
    for term in terms:
        normalized = normalize_term(term)
        if not is_likely_query_term(
            normalized,
            max_length=max_length,
            english_only=english_only,
        ):
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique


def _acronym(term: str) -> str:
    words = re.findall(r"[A-Za-z]+", term)
    return "".join(word[0] for word in words if word).casefold()


def _similarity(a: str, b: str) -> float:
    """Return a deterministic 0-100 string similarity score."""
    try:
        from rapidfuzz import fuzz

        return float(fuzz.WRatio(a, b))
    except Exception:
        return 100.0 * SequenceMatcher(None, a.casefold(), b.casefold()).ratio()


def term_relevance_score(term: str, seed_terms: Sequence[str]) -> float:
    """Score a candidate term against audited seed terms."""
    candidate = normalize_term(term)
    candidate_key = candidate.casefold()
    if not candidate_key:
        return 0.0

    best = 0.0
    candidate_acronym = _acronym(candidate)

    for seed in seed_terms:
        seed_text = normalize_term(seed)
        seed_key = seed_text.casefold()
        if not seed_key:
            continue

        score = _similarity(candidate_key, seed_key)
        if candidate_key == seed_key:
            score += 45
        elif candidate_key.startswith(seed_key) or seed_key.startswith(candidate_key):
            score += 25
        elif candidate_key in seed_key or seed_key in candidate_key:
            score += 15

        seed_acronym = _acronym(seed_text)
        if candidate_acronym and seed_acronym and candidate_acronym == seed_acronym:
            score += 20
        if len(candidate_key) <= 6 and candidate_key == seed_acronym:
            score += 25

        best = max(best, score)

    # Prefer concise terms when relevance is otherwise close.
    return best - min(len(candidate), 120) * 0.01


def rank_terms_by_relevance(
    terms: Iterable[str | None],
    seed_terms: Sequence[str],
    *,
    max_length: int = 120,
    english_only: bool = False,
) -> List[str]:
    """Deduplicate and sort candidate terms by deterministic relevance."""
    unique_terms = dedupe_terms(
        terms,
        max_length=max_length,
        english_only=english_only,
    )
    return sorted(
        unique_terms,
        key=lambda term: (
            -term_relevance_score(term, seed_terms),
            len(term),
            term.casefold(),
        ),
    )


def split_comma_terms(value: str | None) -> List[str]:
    """Parse comma-separated manual terms."""
    if not value:
        return []
    return dedupe_terms(part for part in value.split(","))


def json_safe_text(value: str | None) -> str:
    """Compact text before including it in prompts or audit output."""
    return normalize_term(value)
