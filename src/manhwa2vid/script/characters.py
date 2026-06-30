"""Character name normalization across scene cards and script."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.llm.provider import get_llm_provider
from manhwa2vid.models import SceneCard, save_json

console = Console()

_REGISTRY_PROMPT = """You are building a character name registry for a manhwa recap.

Given scene summaries with speaker names and key terms, merge aliases that refer to the same person.
Return JSON:
{{
  "characters": {{
    "Canonical Full Name": ["alias1", "alias2"]
  }}
}}

Rules:
- Pick one canonical English name per character (full name preferred for main characters).
- Include obvious aliases: nicknames, surname-only, honorifics, OCR misspellings.
- Do NOT merge different characters.
- Main character examples for Solo Leveling: Sung Jin-Woo = Jin-Woo = Sung = Mr. Sung.
"""


def _collect_speaker_evidence(cards: list[SceneCard]) -> str:
    lines: list[str] = []
    for i, card in enumerate(cards, 1):
        if not card.is_story or card.panel_type != "story":
            continue
        speakers = ", ".join(card.speakers) if card.speakers else "(none)"
        terms = ", ".join(card.key_terms) if card.key_terms else ""
        lines.append(
            f"Scene {i} [{', '.join(card.panel_ids)}]: speakers=[{speakers}]; "
            f"action={card.action[:200]}; dialogue={card.dialogue_summary[:200]}; terms=[{terms}]"
        )
    return "\n".join(lines)


def _alias_lookup(characters: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for canonical, aliases in characters.items():
        lookup[str(canonical).strip()] = str(canonical).strip()
        if isinstance(aliases, list):
            for alias in aliases:
                if alias:
                    lookup[str(alias).strip()] = str(canonical).strip()
        elif isinstance(aliases, str) and aliases.strip():
            lookup[aliases.strip()] = str(canonical).strip()
    return lookup


def _normalize_name(name: str, lookup: dict[str, str]) -> str:
    key = name.strip()
    if not key:
        return key
    if key in lookup:
        return lookup[key]
    lower = key.lower()
    for alias, canonical in lookup.items():
        if alias.lower() == lower:
            return canonical
    return key


def _normalize_speakers(speakers: list[str], lookup: dict[str, str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for speaker in speakers:
        canonical = _normalize_name(speaker, lookup)
        if canonical and canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out


def merge_glossary_characters(glossary: dict[str, Any], registry: dict[str, list[str]]) -> dict[str, Any]:
    existing = glossary.get("characters") or {}
    merged = dict(existing)
    for canonical, aliases in registry.items():
        prior = merged.get(canonical, [])
        if isinstance(prior, list):
            combined = list(dict.fromkeys([*prior, *aliases]))
        else:
            combined = aliases
        merged[canonical] = combined
    glossary["characters"] = merged
    return glossary


def build_character_registry(
    cards: list[SceneCard],
    glossary: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, list[str]]:
    evidence = _collect_speaker_evidence(cards)
    if not evidence.strip():
        return glossary.get("characters") or {}

    llm = get_llm_provider(config=config)
    model_name = get_nested(config, "script", "model", default="gpt-4o-mini")
    if hasattr(llm, "model"):
        llm.model = model_name

    user = (
        f"Existing glossary characters:\n{json.dumps(glossary.get('characters', {}), ensure_ascii=False)}\n\n"
        f"Scene evidence:\n{evidence}"
    )
    raw = llm.complete(_REGISTRY_PROMPT, user, json_mode=True)
    data = json.loads(raw)
    registry = data.get("characters") or {}
    if not isinstance(registry, dict):
        return glossary.get("characters") or {}
    return {str(k): [str(a) for a in v] if isinstance(v, list) else [] for k, v in registry.items()}


def normalize_scene_cards(
    cards: list[SceneCard],
    lookup: dict[str, str],
) -> list[SceneCard]:
    normalized: list[SceneCard] = []
    for card in cards:
        normalized.append(
            SceneCard(
                panel_ids=card.panel_ids,
                speakers=_normalize_speakers(card.speakers, lookup),
                dialogue_summary=card.dialogue_summary,
                action=card.action,
                mood=card.mood,
                key_terms=[_normalize_name(t, lookup) for t in card.key_terms],
                source_text=card.source_text,
                is_story=card.is_story,
                exclude_reason=card.exclude_reason,
                panel_type=card.panel_type,
                people=card.people,
            )
        )
    return normalized


def ensure_character_registry(
    paths: dict[str, Path],
    cards: list[SceneCard],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> tuple[list[SceneCard], dict[str, Any]]:
    glossary_path = paths["glossary"]
    glossary = json.loads(glossary_path.read_text(encoding="utf-8")) if glossary_path.exists() else {}

    if paths["scene_normalized_json"].exists() and not force:
        normalized = [SceneCard.model_validate(s) for s in json.loads(paths["scene_normalized_json"].read_text())]
        console.print("[dim]Using cached normalized scene cards[/]")
        return normalized, glossary

    registry = build_character_registry(cards, glossary, config)
    glossary = merge_glossary_characters(glossary, registry)
    save_json(glossary_path, glossary)

    lookup = _alias_lookup(glossary.get("characters") or {})
    normalized = normalize_scene_cards(cards, lookup)
    save_json(paths["scene_normalized_json"], normalized)
    console.print(
        f"[green]Character registry:[/] {len(glossary.get('characters') or {})} canonical names"
    )
    return normalized, glossary


def format_character_registry(glossary: dict[str, Any]) -> str:
    characters = glossary.get("characters") or {}
    if not characters:
        return "(no characters registered yet)"
    lines = []
    for canonical, aliases in characters.items():
        alias_text = ", ".join(aliases) if isinstance(aliases, list) and aliases else ""
        if alias_text:
            lines.append(f"- {canonical} (also: {alias_text})")
        else:
            lines.append(f"- {canonical}")
    return "\n".join(lines)
