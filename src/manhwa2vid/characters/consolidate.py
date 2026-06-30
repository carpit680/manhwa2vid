"""Merge duplicate character profiles and enforce max_main."""

from __future__ import annotations

from typing import Any

from rich.console import Console

from manhwa2vid.characters.bible import merge_profile
from manhwa2vid.characters.resolve import descriptor_overlap_score, normalize_name, score_character_match
from manhwa2vid.config import get_nested
from manhwa2vid.models import CharacterProfile, CharacterRef, CharacterTier, SceneCard, SeriesBible, VisualProfile

console = Console()


def _pick_canonical_id(a: CharacterProfile, b: CharacterProfile) -> str:
    if a.tier == CharacterTier.MAIN and b.tier != CharacterTier.MAIN:
        return a.id
    if b.tier == CharacterTier.MAIN and a.tier != CharacterTier.MAIN:
        return b.id
    if len(a.appearances) != len(b.appearances):
        return a.id if len(a.appearances) >= len(b.appearances) else b.id
    return a.id if len(a.canonical_name) >= len(b.canonical_name) else b.id


def _merge_visual(a: VisualProfile, b: VisualProfile) -> VisualProfile:
    return VisualProfile(
        hair=a.hair or b.hair,
        outfit=a.outfit or b.outfit,
        build=a.build or b.build,
        accessories=list(dict.fromkeys([*a.accessories, *b.accessories])),
        age_range=a.age_range or b.age_range,
        notes=a.notes or b.notes,
    )


def merge_profiles_into(bible: SeriesBible, keep_id: str, drop_id: str) -> None:
    if keep_id == drop_id or keep_id not in bible.characters or drop_id not in bible.characters:
        return
    keep = bible.characters[keep_id]
    drop = bible.characters[drop_id]

    merged_aliases = list(
        dict.fromkeys(
            [
                *keep.aliases,
                *drop.aliases,
                drop.canonical_name,
            ]
        )
    )
    merged_aliases = [a for a in merged_aliases if normalize_name(a) != normalize_name(keep.canonical_name)]

    merge_profile(
        bible,
        CharacterProfile(
            id=keep.id,
            canonical_name=keep.canonical_name,
            tier=keep.tier if keep.tier == CharacterTier.MAIN else drop.tier,
            aliases=merged_aliases,
            descriptors=list(dict.fromkeys([*keep.descriptors, *drop.descriptors])),
            pronoun=keep.pronoun or drop.pronoun,
            role=keep.role or drop.role,
            first_seen_panel=keep.first_seen_panel or drop.first_seen_panel,
            appearances=list(dict.fromkeys([*keep.appearances, *drop.appearances])),
            visual=_merge_visual(keep.visual, drop.visual),
            narration_labels=list(dict.fromkeys([*keep.narration_labels, *drop.narration_labels])),
            sufficiency=keep.sufficiency if keep.sufficiency == "sufficient" else drop.sufficiency,
            confidence=max(keep.confidence, drop.confidence),
            source_chapters=list(dict.fromkeys([*keep.source_chapters, *drop.source_chapters])),
        ),
    )
    bible.characters[drop_id].merged_into = keep_id
    if drop_id in bible.characters:
        del bible.characters[drop_id]
    if bible.protagonist_id == drop_id:
        bible.protagonist_id = keep_id


def find_duplicate_pairs(bible: SeriesBible, *, min_score: float = 0.72) -> list[tuple[str, str]]:
    ids = [cid for cid, p in bible.characters.items() if not p.merged_into]
    pairs: list[tuple[str, str]] = []
    for i, id_a in enumerate(ids):
        profile_a = bible.characters[id_a]
        for id_b in ids[i + 1 :]:
            profile_b = bible.characters[id_b]
            if normalize_name(profile_a.canonical_name) == normalize_name(profile_b.canonical_name):
                pairs.append((id_a, id_b))
                continue
            for alias in profile_a.aliases:
                if _name_match_alias(alias, profile_b):
                    pairs.append((id_a, id_b))
                    break
            else:
                score = score_character_match(profile_a.canonical_name, " ".join(profile_b.descriptors), profile_a)
                rev = score_character_match(profile_b.canonical_name, " ".join(profile_a.descriptors), profile_b)
                desc_score = max(
                    descriptor_overlap_score(" ".join(profile_a.descriptors), " ".join(profile_b.descriptors)),
                    score,
                    rev,
                )
                if desc_score >= min_score:
                    pairs.append((id_a, id_b))
    return pairs


def _name_match_alias(alias: str, profile: CharacterProfile) -> bool:
    key = normalize_name(alias)
    if key == normalize_name(profile.canonical_name):
        return True
    return any(normalize_name(a) == key for a in profile.aliases)


def consolidate_profiles(bible: SeriesBible, config: dict[str, Any]) -> int:
    """Merge duplicate profiles. Returns number of merges performed."""
    merges = 0
    for id_a, id_b in find_duplicate_pairs(bible):
        if id_a not in bible.characters or id_b not in bible.characters:
            continue
        keep = _pick_canonical_id(bible.characters[id_a], bible.characters[id_b])
        drop = id_b if keep == id_a else id_a
        merge_profiles_into(bible, keep, drop)
        merges += 1

    max_main = int(get_nested(config, "characters", "max_main", default=1))
    mains = [p for p in bible.characters.values() if p.tier == CharacterTier.MAIN]
    if len(mains) > max_main:
        mains.sort(key=lambda p: (-len(p.appearances), -p.confidence, p.canonical_name))
        for extra in mains[max_main:]:
            extra.tier = CharacterTier.SUPPORTING
            merges += 1

    if merges:
        console.print(f"[green]Consolidated[/] {merges} character merge(s) — {len(bible.characters)} entries remain")
    return merges


def apply_id_redirects(cards: list[SceneCard], bible: SeriesBible) -> list[SceneCard]:
    """Rewrite people refs after consolidation."""
    redirect: dict[str, str] = {}
    for cid, profile in list(bible.characters.items()):
        if profile.merged_into:
            redirect[cid] = profile.merged_into

    updated: list[SceneCard] = []
    for card in cards:
        people: list[CharacterRef] = []
        for person in card.people:
            ref = person.ref
            if ref in redirect:
                ref = redirect[ref]
            if ref in bible.characters:
                profile = bible.characters[ref]
                people.append(
                    CharacterRef(
                        ref=ref,
                        name_used=profile.canonical_name,
                        descriptor=person.descriptor,
                        visibility=person.visibility,
                        notes=person.notes,
                    )
                )
            else:
                people.append(person)
        updated.append(
            SceneCard(
                panel_ids=card.panel_ids,
                speakers=card.speakers,
                dialogue_summary=card.dialogue_summary,
                action=card.action,
                mood=card.mood,
                key_terms=card.key_terms,
                source_text=card.source_text,
                is_story=card.is_story,
                exclude_reason=card.exclude_reason,
                panel_type=card.panel_type,
                people=people,
            )
        )
    return updated
