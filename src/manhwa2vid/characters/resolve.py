"""Alias-aware character identity resolution."""

from __future__ import annotations

import re
from typing import Any

from manhwa2vid.characters.bible import slugify_char_id
from manhwa2vid.models import CharacterProfile, SeriesBible

_STOPWORDS = frozenset({"a", "an", "the", "guy", "girl", "man", "woman", "person", "with", "in", "on", "and"})


def normalize_name(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def normalize_descriptor(text: str) -> str:
    cleaned = normalize_name(text)
    cleaned = re.sub(r"\b(guys?|girls?|men|women|people)\b", "person", cleaned)
    return cleaned


def _descriptor_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", normalize_descriptor(text)) if t not in _STOPWORDS and len(t) > 2}


def descriptor_overlap_score(a: str, b: str) -> float:
    ta, tb = _descriptor_tokens(a), _descriptor_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _all_names_for_profile(profile: CharacterProfile) -> list[str]:
    names = [profile.canonical_name, *profile.aliases]
    return [n for n in names if n.strip()]


def _visual_text(profile: CharacterProfile) -> str:
    v = profile.visual
    parts = [v.hair, v.outfit, v.build, v.age_range, v.notes, *v.accessories]
    return " ".join(p for p in parts if p)


def _name_match_score(name: str, profile: CharacterProfile) -> float:
    key = normalize_name(name)
    if not key:
        return 0.0
    for candidate in _all_names_for_profile(profile):
        cand = normalize_name(candidate)
        if key == cand:
            return 1.0
        if key in cand or cand in key:
            return 0.85
    return 0.0


def _descriptor_match_score(descriptor: str, profile: CharacterProfile) -> float:
    if not descriptor.strip():
        return 0.0
    best = 0.0
    for desc in profile.descriptors:
        best = max(best, descriptor_overlap_score(descriptor, desc))
    visual = _visual_text(profile)
    if visual:
        best = max(best, descriptor_overlap_score(descriptor, visual))
    return best


def score_character_match(
    name: str,
    descriptor: str,
    profile: CharacterProfile,
) -> float:
    if profile.merged_into:
        return 0.0
    name_score = _name_match_score(name, profile)
    desc_score = _descriptor_match_score(descriptor, profile)
    if name_score >= 0.85:
        return name_score
    if name_score > 0 and desc_score > 0.3:
        return 0.7 * name_score + 0.3 * desc_score
    return max(name_score, desc_score)


def resolve_character_ref(
    name: str,
    descriptor: str,
    bible: SeriesBible,
    *,
    min_score: float = 0.55,
) -> str | None:
    """Return existing char_id if name/descriptor matches bible entry."""
    if not bible.characters:
        return None

    if name.strip():
        direct_id = slugify_char_id(name)
        if direct_id in bible.characters and not bible.characters[direct_id].merged_into:
            if _name_match_score(name, bible.characters[direct_id]) >= 0.85:
                return direct_id

    scored: list[tuple[float, str]] = []
    for profile in bible.characters.values():
        score = score_character_match(name, descriptor, profile)
        if score >= min_score:
            scored.append((score, profile.id))

    if not scored:
        return None
    scored.sort(reverse=True)
    best_score, best_id = scored[0]
    if len(scored) > 1 and scored[1][0] >= best_score - 0.1:
        # Ambiguous — require strong name match
        if _name_match_score(name, bible.characters[best_id]) < 0.85:
            return None
    return best_id


def resolve_or_create_id(name: str, descriptor: str, bible: SeriesBible) -> tuple[str, bool]:
    """Return (char_id, is_new)."""
    existing = resolve_character_ref(name, descriptor, bible)
    if existing:
        return existing, False
    label = name.strip() or descriptor.strip() or "unknown"
    return slugify_char_id(label), True
