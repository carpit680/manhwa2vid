"""Cross-panel identity linking and cast attribution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.characters.bible import format_bible_for_prompt, load_series_bible, merge_profile, save_series_bible
from manhwa2vid.characters.consolidate import apply_id_redirects, consolidate_profiles
from manhwa2vid.characters.resolve import normalize_descriptor, resolve_character_ref
from manhwa2vid.config import get_nested
from manhwa2vid.llm.provider import get_llm_provider
from manhwa2vid.models import (
    CharacterProfile,
    CharacterRef,
    CharacterTier,
    PanelCast,
    ProjectMeta,
    SceneCard,
    SeriesBible,
    save_json,
)
from manhwa2vid.panels.filter import load_story_scene_cards

console = Console()

_LINK_PROMPT = """You are linking manhwa panel identities across a chapter.

Given scene summaries with people descriptors and a character bible, merge duplicate identities.
Return JSON:
{{
  "merges": [
    {{"descriptor_or_name": "guy in green backpack", "char_id": "char_sung_jinwoo", "reason": "same person"}}
  ],
  "panel_updates": [
    {{"panel_id": "p0012_01", "people": [{{"ref": "char_sung_jinwoo", "name_used": "Sung Jin-Woo", "visibility": "back_turned", "notes": ""}}]}}
  ]
}}

Rules:
- Link back-turned / partial views to known cast when context implies same person
- Do NOT merge different named characters
- Prefer bible char_id when confident
"""


def _heuristic_descriptor_merge(cards: list[SceneCard], bible: SeriesBible) -> dict[str, str]:
    descriptor_to_id: dict[str, str] = {}
    for card in cards:
        for person in card.people:
            if person.ref != "new" and person.ref in bible.characters:
                key = normalize_descriptor(person.descriptor or person.name_used)
                if key:
                    descriptor_to_id[key] = person.ref
    merges: dict[str, str] = {}
    for card in cards:
        for person in card.people:
            if person.ref != "new":
                continue
            key = normalize_descriptor(person.descriptor or person.name_used)
            if key and key in descriptor_to_id:
                merges[key] = descriptor_to_id[key]
            else:
                resolved = resolve_character_ref(person.name_used, person.descriptor, bible)
                if resolved:
                    merges[key or person.name_used.lower()] = resolved
    return merges


def _apply_merges_to_cards(cards: list[SceneCard], merges: dict[str, str], bible: SeriesBible) -> list[SceneCard]:
    enriched: list[SceneCard] = []
    for card in cards:
        people: list[CharacterRef] = []
        for person in card.people:
            key = normalize_descriptor(person.descriptor or person.name_used)
            char_id = merges.get(key) or (person.ref if person.ref != "new" else "")
            if not char_id or char_id not in bible.characters:
                resolved = resolve_character_ref(person.name_used, person.descriptor, bible)
                char_id = resolved or char_id
            if char_id and char_id in bible.characters:
                profile = bible.characters[char_id]
                people.append(
                    CharacterRef(
                        ref=char_id,
                        name_used=profile.canonical_name,
                        descriptor=person.descriptor,
                        visibility=person.visibility,
                        notes=person.notes,
                    )
                )
            else:
                people.append(person)
        enriched.append(
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
    return enriched


def _apply_panel_updates(cards: list[SceneCard], panel_updates: list[dict[str, Any]], bible: SeriesBible) -> list[SceneCard]:
    update_map: dict[str, list[CharacterRef]] = {}
    for item in panel_updates:
        panel_id = str(item.get("panel_id", ""))
        people_raw = item.get("people", [])
        refs: list[CharacterRef] = []
        for p in people_raw:
            if not isinstance(p, dict):
                continue
            ref = str(p.get("ref", "new"))
            if ref == "new":
                resolved = resolve_character_ref(str(p.get("name_used", "")), str(p.get("descriptor", "")), bible)
                ref = resolved or ref
            refs.append(
                CharacterRef(
                    ref=ref,
                    name_used=str(p.get("name_used", "")),
                    descriptor=str(p.get("descriptor", "")),
                    visibility=str(p.get("visibility", "face")),
                    notes=str(p.get("notes", "")),
                )
            )
        if panel_id and refs:
            update_map[panel_id] = refs

    if not update_map:
        return cards

    updated: list[SceneCard] = []
    for card in cards:
        new_people = list(card.people)
        for panel_id in card.panel_ids:
            if panel_id in update_map:
                new_people = update_map[panel_id]
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
                people=new_people,
            )
        )
    return updated


def _build_attribution(cards: list[SceneCard]) -> list[PanelCast]:
    attribution: list[PanelCast] = []
    for card in cards:
        for panel_id in card.panel_ids:
            attribution.append(PanelCast(panel_id=panel_id, people=card.people))
    return attribution


def _llm_link_pass(
    cards: list[SceneCard],
    bible: SeriesBible,
    config: dict[str, Any],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    evidence_lines = []
    for card in cards:
        if not card.is_story:
            continue
        pid = card.panel_ids[0] if card.panel_ids else "?"
        people = json.dumps([p.model_dump() for p in card.people], ensure_ascii=False)
        evidence_lines.append(
            f"{pid}: speakers={card.speakers}; people={people}; "
            f"action={card.action[:160]}; dialogue={card.dialogue_summary[:160]}"
        )
    if not evidence_lines:
        return {}, []

    llm = get_llm_provider(config=config)
    model_name = get_nested(config, "script", "model", default="gpt-4o-mini")
    if hasattr(llm, "model"):
        llm.model = model_name

    user = (
        f"Bible:\n{format_bible_for_prompt(bible)}\n\n"
        f"Chapter scenes:\n" + "\n".join(evidence_lines[:80])
    )
    try:
        raw = llm.complete(_LINK_PROMPT, user, json_mode=True)
        data = json.loads(raw)
    except Exception:
        return {}, []

    merges: dict[str, str] = {}
    for item in data.get("merges", []):
        key = normalize_descriptor(str(item.get("descriptor_or_name", "")))
        char_id = str(item.get("char_id", "")).strip()
        if key and char_id:
            merges[key] = char_id
    panel_updates = data.get("panel_updates", [])
    return merges, panel_updates if isinstance(panel_updates, list) else []


def run_cast_linking(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> tuple[list[SceneCard], SeriesBible]:
    if (
        paths["cast_attribution_json"].exists()
        and paths["scene_enriched_json"].exists()
        and not force
    ):
        console.print("[dim]Using cached cast attribution[/]")
        cards = [SceneCard.model_validate(s) for s in json.loads(paths["scene_enriched_json"].read_text())]
        bible = load_series_bible(meta.series_slug, meta.title)
        return cards, bible

    cards = load_story_scene_cards(paths)
    if not cards:
        cards = [SceneCard.model_validate(s) for s in json.loads(paths["scene_json"].read_text())]

    bible = load_series_bible(meta.series_slug, meta.title)

    heuristic_merges = _heuristic_descriptor_merge(cards, bible)
    llm_merges, panel_updates = _llm_link_pass(cards, bible, config)
    all_merges = {**heuristic_merges, **llm_merges}

    enriched = _apply_merges_to_cards(cards, all_merges, bible)
    enriched = _apply_panel_updates(enriched, panel_updates, bible)

    for card in enriched:
        for panel_id in card.panel_ids:
            for person in card.people:
                if person.ref == "new":
                    resolved = resolve_character_ref(person.name_used, person.descriptor, bible)
                    if resolved:
                        person.ref = resolved
                if person.ref == "new":
                    continue
                if person.ref in bible.characters:
                    profile = bible.characters[person.ref]
                    merge_profile(
                        bible,
                        CharacterProfile(
                            id=profile.id,
                            canonical_name=profile.canonical_name,
                            tier=profile.tier,
                            aliases=profile.aliases,
                            descriptors=profile.descriptors,
                            pronoun=profile.pronoun,
                            role=profile.role,
                            first_seen_panel=profile.first_seen_panel or panel_id,
                            appearances=list(dict.fromkeys([*profile.appearances, panel_id])),
                            visual=profile.visual,
                            narration_labels=profile.narration_labels,
                            source_chapters=profile.source_chapters,
                        ),
                    )

    consolidate_profiles(bible, config)
    enriched = apply_id_redirects(enriched, bible)

    attribution = _build_attribution(enriched)
    save_json(paths["scene_enriched_json"], enriched)
    save_json(paths["cast_attribution_json"], attribution)
    save_series_bible(bible)

    console.print(
        f"[green]Cast linking complete[/] — {len(enriched)} scenes, "
        f"{len(bible.characters)} bible entries, MC={bible.protagonist_id or '?'}"
    )
    return enriched, bible
