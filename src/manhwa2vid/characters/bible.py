"""Series character bible load/save and formatting."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from manhwa2vid.config import find_repo_root
from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible, VisualProfile, save_json, series_paths

_DESCRIPTOR_PREFIXES = ("guy ", "man ", "woman ", "girl ", "boy ", "person ", "blonde ", "bald ", "crowd ")
_JUNK_ALIAS_RE = re.compile(r"(?i)^(template:|user:|category:)|infobox")


def normalize_name(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def is_junk_alias(text: str) -> bool:
    return bool(_JUNK_ALIAS_RE.search(text.strip()))


def slugify_char_id(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"char_{base}" if base else "char_unknown"


def is_descriptor_label(text: str) -> bool:
    t = normalize_name(text)
    if not t:
        return False
    if any(t.startswith(prefix) for prefix in _DESCRIPTOR_PREFIXES):
        return True
    if " with " in t and not any(ch.isupper() for ch in text):
        return True
    return False


def clean_profile_aliases(profile: CharacterProfile, *, protagonist_id: str = "") -> CharacterProfile:
    aliases = [a for a in profile.aliases if a.strip() and not is_junk_alias(a)]
    descriptors = list(profile.descriptors)
    if profile.id == protagonist_id:
        real_aliases: list[str] = []
        for alias in aliases:
            if is_descriptor_label(alias):
                if alias not in descriptors:
                    descriptors.append(alias)
            else:
                real_aliases.append(alias)
        aliases = real_aliases
    return CharacterProfile(
        id=profile.id,
        canonical_name=profile.canonical_name,
        tier=profile.tier,
        aliases=aliases,
        descriptors=descriptors,
        pronoun=profile.pronoun,
        role=profile.role,
        first_seen_panel=profile.first_seen_panel,
        appearances=profile.appearances,
        visual=profile.visual,
        narration_labels=profile.narration_labels,
        sufficiency=profile.sufficiency,
        confidence=profile.confidence,
        merged_into=profile.merged_into,
        source_chapters=profile.source_chapters,
    )


def clean_bible_aliases(bible: SeriesBible) -> None:
    for char_id in list(bible.characters):
        bible.characters[char_id] = clean_profile_aliases(
            bible.characters[char_id],
            protagonist_id=bible.protagonist_id,
        )


def load_series_bible(series_slug: str, title: str) -> SeriesBible:
    paths = series_paths(find_repo_root(), series_slug)
    path = paths["character_bible"]
    if path.exists():
        return SeriesBible.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return SeriesBible(series_slug=series_slug, title=title)


def save_series_bible(bible: SeriesBible) -> Path:
    paths = series_paths(find_repo_root(), bible.series_slug)
    paths["series_dir"].mkdir(parents=True, exist_ok=True)
    save_json(paths["character_bible"], bible)
    return paths["character_bible"]


def merge_profile(bible: SeriesBible, profile: CharacterProfile) -> None:
    existing = bible.characters.get(profile.id)
    if existing is None:
        bible.characters[profile.id] = profile
        return
    merged_appearances = list(dict.fromkeys([*existing.appearances, *profile.appearances]))
    merged_aliases = list(dict.fromkeys([*existing.aliases, *profile.aliases]))
    merged_aliases = [a for a in merged_aliases if not is_junk_alias(a)]
    merged_descriptors = list(dict.fromkeys([*existing.descriptors, *profile.descriptors]))
    merged_labels = list(dict.fromkeys([*existing.narration_labels, *profile.narration_labels]))
    merged_chapters = list(dict.fromkeys([*existing.source_chapters, *profile.source_chapters]))
    tier = existing.tier
    if profile.tier == CharacterTier.MAIN or (
        existing.tier != CharacterTier.MAIN and profile.tier == CharacterTier.SUPPORTING
    ):
        tier = profile.tier
    visual = VisualProfile(
        hair=profile.visual.hair or existing.visual.hair,
        outfit=profile.visual.outfit or existing.visual.outfit,
        build=profile.visual.build or existing.visual.build,
        accessories=list(dict.fromkeys([*existing.visual.accessories, *profile.visual.accessories])),
        age_range=profile.visual.age_range or existing.visual.age_range,
        notes=profile.visual.notes or existing.visual.notes,
    )
    bible.characters[profile.id] = CharacterProfile(
        id=profile.id,
        canonical_name=profile.canonical_name or existing.canonical_name,
        tier=tier,
        aliases=merged_aliases,
        descriptors=merged_descriptors,
        pronoun=profile.pronoun or existing.pronoun,
        role=profile.role or existing.role,
        first_seen_panel=existing.first_seen_panel or profile.first_seen_panel,
        appearances=merged_appearances,
        visual=visual,
        narration_labels=merged_labels,
        sufficiency=profile.sufficiency if profile.sufficiency != "pending" else existing.sufficiency,
        confidence=max(existing.confidence, profile.confidence),
        merged_into=profile.merged_into or existing.merged_into,
        source_chapters=merged_chapters,
    )


def format_bible_for_prompt(bible: SeriesBible, *, active_ids: set[str] | None = None) -> str:
    if not bible.characters:
        return "(no characters in bible yet)"
    lines: list[str] = []
    ordered = sorted(
        bible.characters.values(),
        key=lambda p: (p.tier.value, -len(p.appearances), p.canonical_name),
    )
    for profile in ordered:
        if profile.merged_into:
            continue  # tombstone — kept only so id redirects survive consolidation
        if active_ids and profile.id not in active_ids and profile.tier not in (
            CharacterTier.MAIN,
            CharacterTier.SUPPORTING,
        ):
            continue
        alias_text = ", ".join(profile.aliases) if profile.aliases else ""
        desc_text = ", ".join(profile.descriptors) if profile.descriptors else ""
        visual_bits = [profile.visual.hair, profile.visual.outfit, profile.visual.build]
        visual_text = ", ".join(v for v in visual_bits if v)
        label_text = ", ".join(profile.narration_labels) if profile.narration_labels else ""
        mc_tag = " [MC]" if profile.id == bible.protagonist_id else ""
        parts = [
            f"- [{profile.tier.value}]{mc_tag} {profile.canonical_name} (id={profile.id}, pronoun={profile.pronoun})"
        ]
        if profile.role:
            parts.append(f"role: {profile.role}")
        if alias_text:
            parts.append(f"aliases: {alias_text}")
        if desc_text:
            parts.append(f"looks: {desc_text}")
        if visual_text:
            parts.append(f"visual: {visual_text}")
        if label_text:
            parts.append(f"say_as: {label_text}")
        lines.append("; ".join(parts))
    return "\n".join(lines)


def naming_priority_rules(bible: SeriesBible | None = None, config: dict | None = None) -> str:
    """Anchor policy measured from the reference channel: the protagonist is anchored by
    NAME roughly every 80 words, with pronouns carrying everything in between (6+ pronoun
    references per anchor). Generic labels are what make a script feel like it lost its
    protagonist, so they are essentially banned."""
    mc_name = ""
    mc_pronoun = "he"
    if bible and bible.protagonist_id and bible.protagonist_id in bible.characters:
        mc = bible.characters[bible.protagonist_id]
        mc_name = mc.canonical_name.strip()
        mc_pronoun = mc.pronoun or "he"
    anchor = f"'{mc_name}'" if mc_name else "the protagonist's canonical name"
    return (
        "Naming rules (never use the word 'character' for a person on screen):\n"
        f"Protagonist{f' = {mc_name}' if mc_name else ''}:\n"
        f"  - Anchor with the NAME {anchor} roughly every 70-90 words, and at each scene change.\n"
        f"  - Between anchors use pronouns only ({mc_pronoun}/him/his) — several pronoun uses per name anchor.\n"
        "  - NEVER write 'MC'. Use the phrase 'the protagonist' at most ONCE in the whole chapter.\n"
        "  - Never describe the protagonist by clothing or gear as if a different person "
        "('the man with the backpack' is FORBIDDEN when it is him).\n"
        "Supporting cast:\n"
        "  - FIRST mention in the script: name + one short intro clause from the bible "
        "(role or look): 'Lee Joo-hee, the party's rookie healer, ...'.\n"
        "  - Every later mention: name or pronoun. Never repeat the intro clause.\n"
        "Unnamed people: a short role phrase (the guild clerk, a veteran hunter) — "
        "NEVER 'character', 'someone', 'a man', 'two people'.\n"
        "Never attribute an action or line to anyone not on screen in that beat's panels.\n"
    )


def rebuild_bible_from_glossary(
    meta: Any,
    glossary: dict[str, Any],
    *,
    chapter_summaries: dict[str, str] | None = None,
) -> SeriesBible:
    """Reset polluted bible to glossary-backed cast hints."""
    from manhwa2vid.characters.seed import profiles_from_glossary

    bible = SeriesBible(series_slug=meta.series_slug, title=meta.title)
    if chapter_summaries:
        bible.chapter_summaries = chapter_summaries

    for profile in profiles_from_glossary(glossary):
        if normalize_name(profile.canonical_name) == normalize_name("Sung Jin-Woo"):
            profile.tier = CharacterTier.MAIN
            profile.role = "protagonist"
            profile.pronoun = "he"
            profile.descriptors = [
                "man with green backpack",
                "E-Rank hunter",
                "guy with green backpack",
            ]
            profile.visual = VisualProfile(
                hair="black",
                outfit="green backpack / green hood",
                accessories=["green backpack"],
            )
            bible.protagonist_id = profile.id
        merge_profile(bible, profile)

    clean_bible_aliases(bible)
    return bible
