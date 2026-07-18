"""Alias-aware character identity resolution."""

from __future__ import annotations

import re

from manhwa2vid.characters.bible import is_junk_alias, normalize_name, slugify_char_id
from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible

_STOPWORDS = frozenset({"a", "an", "the", "guy", "girl", "man", "woman", "person", "with", "in", "on", "and"})
_MC_STRONG_SIGNALS = (
    "green backpack",
    "green hood",
    "man with green backpack",
    "guy in green backpack",
    "guy with green backpack",
    "jin-woo",
    "jin woo",
    "sung jin",
    "sung jin-woo",
    "e-rank hunter",
)


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
    names = [profile.canonical_name, *[a for a in profile.aliases if not is_junk_alias(a)]]
    return [n for n in names if n.strip()]


def _visual_text(profile: CharacterProfile) -> str:
    v = profile.visual
    parts = [v.hair, v.outfit, v.build, v.age_range, v.notes, *v.accessories, *profile.descriptors]
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


def is_mc_visual_signal(name: str, descriptor: str, speaker: str = "") -> bool:
    blob = normalize_name(f"{name} {descriptor} {speaker}")
    return any(signal in blob for signal in _MC_STRONG_SIGNALS)


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
    # Descriptor-only matches are weak — cap score
    if name_score == 0.0 and desc_score > 0:
        return desc_score * 0.75
    return max(name_score, desc_score)


def resolve_character_ref(
    name: str,
    descriptor: str,
    bible: SeriesBible,
    *,
    min_score: float = 0.55,
    speaker: str = "",
) -> str | None:
    """Return existing char_id if name/descriptor matches bible entry."""
    if not bible.characters:
        return None

    protagonist_id = bible.protagonist_id
    protagonist_profile = bible.characters.get(protagonist_id) if protagonist_id else None

    if name.strip():
        direct_id = slugify_char_id(name)
        if direct_id in bible.characters and not bible.characters[direct_id].merged_into:
            if _name_match_score(name, bible.characters[direct_id]) >= 0.85:
                return direct_id

    scored: list[tuple[float, str]] = []
    for profile in bible.characters.values():
        if profile.merged_into:
            continue
        score = score_character_match(name, descriptor, profile)
        if profile.id == protagonist_id and protagonist_profile:
            if not is_mc_visual_signal(name, descriptor, speaker) and _name_match_score(name, protagonist_profile) < 0.85:
                if descriptor.strip() and score < 0.9:
                    continue
        if score >= min_score:
            scored.append((score, profile.id))

    if not scored:
        return None
    scored.sort(reverse=True)
    best_score, best_id = scored[0]
    if len(scored) > 1 and scored[1][0] >= best_score - 0.1:
        if _name_match_score(name, bible.characters[best_id]) < 0.85:
            return None
    return best_id


def resolve_or_create_id(name: str, descriptor: str, bible: SeriesBible, *, speaker: str = "") -> tuple[str, bool]:
    """Return (char_id, is_new)."""
    existing = resolve_character_ref(name, descriptor, bible, speaker=speaker)
    if existing:
        return existing, False
    label = name.strip() or speaker.strip() or descriptor.strip() or "unknown"
    return slugify_char_id(label), True


def profiles_are_same_person(a: CharacterProfile, b: CharacterProfile) -> bool:
    """Strict duplicate check for consolidation — avoid merging distinct cast."""
    if a.id == b.id or a.merged_into or b.merged_into:
        return False
    if normalize_name(a.canonical_name) == normalize_name(b.canonical_name):
        return True
    for alias in a.aliases:
        if not is_junk_alias(alias) and _name_match_score(alias, b) >= 0.85:
            return True
    for alias in b.aliases:
        if not is_junk_alias(alias) and _name_match_score(alias, a) >= 0.85:
            return True
    # Both descriptor-only with same slug base
    if a.tier == CharacterTier.MINOR and b.tier == CharacterTier.MINOR:
        if normalize_descriptor(a.canonical_name) == normalize_descriptor(b.canonical_name):
            return True
    return False
