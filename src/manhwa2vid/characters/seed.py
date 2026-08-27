"""Seed series character bible from glossary hints and optional wiki."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.characters.bible import load_series_bible, merge_profile, save_series_bible, slugify_char_id
from manhwa2vid.config import get_nested
from manhwa2vid.models import CharacterProfile, CharacterTier, ProjectMeta, SeriesBible

console = Console()


def profiles_from_glossary(glossary: dict[str, Any]) -> list[CharacterProfile]:
    """Glossary provides optional hints — tier assigned later by scout/quest."""
    characters = glossary.get("characters") or {}
    profiles: list[CharacterProfile] = []
    for canonical, aliases in characters.items():
        alias_list = aliases if isinstance(aliases, list) else ([aliases] if aliases else [])
        profiles.append(
            CharacterProfile(
                id=slugify_char_id(str(canonical)),
                canonical_name=str(canonical),
                tier=CharacterTier.SUPPORTING,
                aliases=[str(a) for a in alias_list if a],
                pronoun="he",
                confidence=0.3,
                sufficiency="pending",
            )
        )
    return profiles


def seed_series_bible(
    meta: ProjectMeta,
    glossary_path: Path,
    config: dict[str, Any],
) -> SeriesBible:
    bible = load_series_bible(meta.series_slug, meta.title)
    glossary = json.loads(glossary_path.read_text(encoding="utf-8")) if glossary_path.exists() else {}

    for profile in profiles_from_glossary(glossary):
        merge_profile(bible, profile)

    # Wiki seeding lived here behind characters.wiki_lookup. It was off by default
    # because scraping seeded junk profiles (Template:Infobox..., User:...) into the
    # bible; the glossary carries the sticky cast instead. Removed with the flag.

    save_series_bible(bible)
    console.print(f"[green]Series bible seeded:[/] {len(bible.characters)} character hints")
    return bible
