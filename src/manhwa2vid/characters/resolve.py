"""Alias-aware character identity resolution."""

from __future__ import annotations

import re

from manhwa2vid.characters.bible import is_descriptor_label, is_junk_alias, normalize_name, slugify_char_id
from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible

_STOPWORDS = frozenset({"a", "an", "the", "guy", "girl", "man", "woman", "person", "with", "in", "on", "and"})
# Words that identify nobody: function words plus the generic person and appearance
# vocabulary every character description shares. A signal built from these would promote
# every "man with black hair" to protagonist, the failure this gate exists to prevent.
_UNINFORMATIVE = frozenset(
    """
    a an the and or of with in on at to for from his her their its
    man woman guy girl person boy youth kid hunter figure people someone character
    black white grey gray brown blonde blond short long tall young old big small
    hair eyes face head body wearing worn dark light messy straight curly
    """.split()
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


_RELATIONAL_RE = re.compile(r"\b\w[\w-]*'s\s+\w", re.I)


def _is_relational_phrase(text: str) -> bool:
    """"Jun-Ho's old friend" names a RELATION to Jun-Ho, not Jun-Ho.

    Possessive aliases are common in glossaries and synopses ("X's mother", "X's old
    friend") and they contain the other character's name as a substring, which is
    exactly what fuzzy containment rewards. On the second title tested this merged the
    Association president INTO the protagonist: his alias "Jun-Ho's old friend" scored
    0.85 against "Seo Jun-Ho", consolidation collapsed the two profiles, the verifier's
    cast sheet then said the protagonist was a bald association president, and every
    beat showing him with hair was flagged as a major misattribution — 61% of the
    script fell back to outline text from one corrupted alias.
    """
    return bool(_RELATIONAL_RE.search(text))


def _name_match_score(name: str, profile: CharacterProfile) -> float:
    key = normalize_name(name)
    if not key:
        return 0.0
    relational = _is_relational_phrase(name)
    for candidate in _all_names_for_profile(profile):
        cand = normalize_name(candidate)
        if key == cand:
            return 1.0
        if relational or _is_relational_phrase(candidate):
            # A relational phrase identifies someone only by EXACT match to itself.
            continue
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


def mc_signals(bible: SeriesBible) -> tuple[str, ...]:
    """Phrases that identify the protagonist strongly enough to promote a reference.

    Derived from the protagonist's own bible entry rather than a hardcoded list, so this
    works for any series. Those fields originate in the per-project glossary.json, which
    is where a reader records "this is what he is called".

    Two kinds of signal, because they come from different places:
      - NAME signals: the canonical name and aliases, plus their individual tokens. A name
        is identifying on its own.
      - VISUAL signals: 2-3 word n-grams from descriptors and the visual profile, kept
        only when EVERY word is distinctive. "green backpack" survives; "messy black
        hair" does not, because a descriptor built from generic words describes half a
        cast and promoting it to protagonist is the exact bug this gate exists to stop.

    Single visual tokens are deliberately excluded: "green" or "hoodie" alone match far
    too much. An earlier draft admitted them along with stopwords, which made "with" a
    signal and matched literally every reference.
    """
    profile = bible.characters.get(bible.protagonist_id or "")
    if profile is None:
        return ()

    def _words(text: str) -> list[str]:
        return [w for w in re.split(r"[^a-z0-9'-]+", normalize_name(str(text or ""))) if w]

    signals: set[str] = set()

    visual_sources = list(profile.descriptors)

    for item in (profile.canonical_name, *profile.aliases):
        words = _words(item)
        if not words or all(w in _UNINFORMATIVE for w in words):
            continue
        # An alias is supposed to be a NAME. Bibles drift, and this protagonist's alias
        # list had accumulated whole descriptor sentences; taking their tokens made
        # "green" a signal on its own, which then matched a different character's green
        # jacket. Anything longer than a name goes through the visual path instead, where
        # every word of an n-gram must be distinctive.
        if len(words) > 3:
            visual_sources.append(item)
            continue
        signals.add(" ".join(words))
        for word in words:
            if len(word) > 2 and word not in _UNINFORMATIVE:
                signals.add(word)

    if profile.visual is not None:
        visual_sources.extend(
            [profile.visual.hair or "", profile.visual.outfit or "", *(profile.visual.accessories or [])]
        )
    for item in visual_sources:
        words = _words(item)
        for size in (2, 3):
            for i in range(len(words) - size + 1):
                gram = words[i : i + size]
                if any(w in _UNINFORMATIVE for w in gram):
                    continue
                signals.add(" ".join(gram))

    # Longest first: a specific phrase should be tested before a token inside it.
    return tuple(sorted(signals, key=lambda x: (-len(x.split()), -len(x), x)))


def is_mc_visual_signal(
    name: str,
    descriptor: str,
    speaker: str = "",
    bible: SeriesBible | None = None,
) -> bool:
    """True when the reference carries a phrase unique to the protagonist.

    `bible` is required to mean anything; without it there is nothing to compare against
    and the answer is False, which is the safe direction (no promotion).
    """
    if bible is None:
        return False
    signals = mc_signals(bible)
    if not signals:
        return False
    blob = normalize_name(f"{name} {descriptor} {speaker}")
    return any(signal in blob for signal in signals)


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
            if not is_mc_visual_signal(name, descriptor, speaker, bible) and _name_match_score(name, protagonist_profile) < 0.85:
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
    # Two profiles that BOTH carry real names may only merge on an EXACT alias identity
    # ("Specter" listed as an alias of "Seo Jun-Ho"), never on fuzzy containment: fuzzy
    # is how "Deok-gu" (alias "Jun-Ho's old friend") became the protagonist. Fuzzy
    # matching remains available when at least one side is a descriptor-labeled profile,
    # where it is the only signal there is.
    both_named = not is_descriptor_label(a.canonical_name) and not is_descriptor_label(b.canonical_name)
    threshold = 1.0 if both_named else 0.85
    for alias in a.aliases:
        if not is_junk_alias(alias) and _name_match_score(alias, b) >= threshold:
            return True
    for alias in b.aliases:
        if not is_junk_alias(alias) and _name_match_score(alias, a) >= threshold:
            return True
    # Both descriptor-only with same slug base
    if a.tier == CharacterTier.MINOR and b.tier == CharacterTier.MINOR:
        if normalize_descriptor(a.canonical_name) == normalize_descriptor(b.canonical_name):
            return True
    return False
