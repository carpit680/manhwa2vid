"""Series character bible load/save and formatting."""

from __future__ import annotations

import json
import re
from pathlib import Path

from manhwa2vid.config import find_repo_root
from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible, VisualProfile, save_json, series_paths


def slugify_char_id(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"char_{base}" if base else "char_unknown"


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
    mc_labels = "MC, the protagonist, our guy"
    if config:
        from manhwa2vid.config import get_nested

        labels = get_nested(config, "characters", "mc_labels", default=[])
        if labels:
            mc_labels = ", ".join(str(label) for label in labels)
    protagonist_note = ""
    if bible and bible.protagonist_id and bible.protagonist_id in bible.characters:
        mc = bible.characters[bible.protagonist_id]
        protagonist_note = f"\nProtagonist id={bible.protagonist_id} ({mc.canonical_name}). Use {mc_labels} after the hook beat."
    return (
        "Naming priority (never use the word 'character' for a person on screen):\n"
        f"Protagonist:{protagonist_note}\n"
        "  1. MC / the protagonist / configured mc_labels (after opening hook)\n"
        "  2. Pronoun (he/she/they) once established\n"
        "  3. Full canonical name (intro, re-intro after gap, or clarity needed)\n"
        "  4. Role descriptor (the E-Rank hunter, the guild clerk)\n"
        "Supporting:\n"
        "  1. Name once per chapter, then pronoun or role\n"
        "  2. Never use MC labels for non-protagonist characters\n"
        "Background: some hunters, a bystander — NEVER 'character'\n"
        "Never attribute an action to the protagonist unless they are on screen in that beat's panels.\n"
    )
