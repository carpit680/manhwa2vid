"""Multi-source character information search."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from manhwa2vid.characters.wiki import fetch_wiki_cast
from manhwa2vid.config import find_repo_root, get_nested
from manhwa2vid.models import CharacterFinding, CharacterProfile, CharacterTier, ProjectMeta, SceneCard, SeriesBible, series_paths


def search_glossary_hint(glossary: dict[str, Any], profile: CharacterProfile) -> list[CharacterFinding]:
    findings: list[CharacterFinding] = []
    characters = glossary.get("characters") or {}
    for canonical, aliases in characters.items():
        alias_list = aliases if isinstance(aliases, list) else ([aliases] if aliases else [])
        names = [canonical, *alias_list]
        if any(profile.canonical_name.lower() in n.lower() or n.lower() in profile.canonical_name.lower() for n in names):
            findings.append(
                CharacterFinding(field="canonical_name", value=str(canonical), source="glossary", confidence=0.5)
            )
            for alias in alias_list:
                findings.append(
                    CharacterFinding(field="alias", value=str(alias), source="glossary", confidence=0.4)
                )
    return findings


def search_wiki(title: str, profile: CharacterProfile, config: dict[str, Any]) -> list[CharacterFinding]:
    findings: list[CharacterFinding] = []
    for wiki_profile in fetch_wiki_cast(title, config):
        if profile.canonical_name and wiki_profile.canonical_name.lower() not in profile.canonical_name.lower():
            if profile.canonical_name.lower() not in wiki_profile.canonical_name.lower():
                if not any(a.lower() in wiki_profile.canonical_name.lower() for a in profile.aliases):
                    continue
        if wiki_profile.role:
            findings.append(CharacterFinding(field="role", value=wiki_profile.role, source="wiki", confidence=0.7))
        if wiki_profile.visual.hair:
            findings.append(
                CharacterFinding(field="visual.hair", value=wiki_profile.visual.hair, source="wiki", confidence=0.65)
            )
        if wiki_profile.visual.outfit:
            findings.append(
                CharacterFinding(field="visual.outfit", value=wiki_profile.visual.outfit, source="wiki", confidence=0.65)
            )
        for alias in wiki_profile.aliases:
            findings.append(CharacterFinding(field="alias", value=alias, source="wiki", confidence=0.6))
        if wiki_profile.tier == CharacterTier.MAIN:
            findings.append(CharacterFinding(field="tier", value="main", source="wiki", confidence=0.8))
    return findings


def search_current_chapter(
    profile: CharacterProfile,
    scene_cards: list[SceneCard],
    ocr_path: Path | None,
) -> list[CharacterFinding]:
    findings: list[CharacterFinding] = []
    name_keys = {profile.canonical_name.lower(), *[a.lower() for a in profile.aliases]}

    for card in scene_cards:
        blob = " ".join([card.action, card.dialogue_summary, " ".join(card.speakers), " ".join(card.key_terms)])
        if not any(k and k in blob.lower() for k in name_keys if k):
            continue
        for person in card.people:
            if person.descriptor:
                findings.append(
                    CharacterFinding(field="descriptor", value=person.descriptor, source="current_scene", confidence=0.7)
                )
        for speaker in card.speakers:
            if speaker.lower() in name_keys or profile.canonical_name.lower() in speaker.lower():
                findings.append(
                    CharacterFinding(field="alias", value=speaker, source="current_scene", confidence=0.75)
                )

    if ocr_path and ocr_path.exists():
        ocr_data = json.loads(ocr_path.read_text(encoding="utf-8"))
        for row in ocr_data:
            text = str(row.get("full_text", "")) + str(row.get("translated_text", ""))
            if any(k and k in text.lower() for k in name_keys if k):
                findings.append(
                    CharacterFinding(field="ocr_mention", value=text[:120], source="current_ocr", confidence=0.5)
                )
    return findings


def search_future_panels(
    profile: CharacterProfile,
    series_slug: str,
    gaps: list[str],
) -> list[CharacterFinding]:
    findings: list[CharacterFinding] = []
    scout_dir = series_paths(find_repo_root(), series_slug)["scout_dir"]
    if not scout_dir.exists():
        return findings

    manifest_path = scout_dir / "manifest.json"
    if not manifest_path.exists():
        return findings
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scout_samples = manifest.get("samples", [])

    name_keys = {profile.canonical_name.lower(), *[a.lower() for a in profile.aliases]}
    for sample in scout_samples:
        blob = json.dumps(sample, ensure_ascii=False).lower()
        if not any(k and k in blob for k in name_keys if k):
            if "visual" not in gaps and "descriptor" not in gaps:
                continue
        for person in sample.get("people", []):
            desc = str(person.get("descriptor", ""))
            name = str(person.get("name_used", ""))
            if desc:
                findings.append(
                    CharacterFinding(
                        field="descriptor",
                        value=desc,
                        source="scout_panel",
                        chapter=sample.get("chapter"),
                        confidence=0.65,
                    )
                )
            if name:
                findings.append(
                    CharacterFinding(
                        field="alias",
                        value=name,
                        source="scout_panel",
                        chapter=sample.get("chapter"),
                        confidence=0.7,
                    )
                )
        for key in ("hair", "outfit", "build"):
            if sample.get(key):
                findings.append(
                    CharacterFinding(
                        field=f"visual.{key}",
                        value=str(sample[key]),
                        source="scout_panel",
                        chapter=sample.get("chapter"),
                        confidence=0.6,
                    )
                )
    return findings


def search_sources(
    profile: CharacterProfile,
    gaps: list[str],
    *,
    meta: ProjectMeta,
    config: dict[str, Any],
    glossary: dict[str, Any],
    scene_cards: list[SceneCard],
    ocr_path: Path | None,
) -> list[CharacterFinding]:
    findings: list[CharacterFinding] = []
    findings.extend(search_glossary_hint(glossary, profile))
    findings.extend(search_wiki(meta.title, profile, config))
    findings.extend(search_current_chapter(profile, scene_cards, ocr_path))
    findings.extend(search_future_panels(profile, meta.series_slug, gaps))
    return findings
