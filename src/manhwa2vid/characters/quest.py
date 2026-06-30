"""Character sufficiency evaluation and quest loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.characters.bible import merge_profile, save_series_bible
from manhwa2vid.characters.consolidate import consolidate_profiles
from manhwa2vid.characters.search import search_sources
from manhwa2vid.config import find_repo_root, get_nested
from manhwa2vid.models import (
    CharacterFinding,
    CharacterProfile,
    CharacterQuestState,
    CharacterTier,
    ProjectMeta,
    SceneCard,
    SeriesBible,
    VisualProfile,
    save_json,
    series_paths,
)

console = Console()


def evaluate_sufficiency(profile: CharacterProfile, *, protagonist_id: str = "") -> list[str]:
    gaps: list[str] = []
    is_protagonist = profile.id == protagonist_id or profile.tier == CharacterTier.MAIN

    if is_protagonist or profile.tier == CharacterTier.SUPPORTING:
        if not profile.canonical_name.strip():
            gaps.append("canonical_name")
    elif not profile.canonical_name.strip() and not profile.descriptors:
        gaps.append("descriptor")

    if is_protagonist:
        if not profile.visual.hair:
            gaps.append("visual.hair")
        if not profile.visual.outfit:
            gaps.append("visual.outfit")
        if not profile.pronoun or profile.pronoun == "they":
            gaps.append("pronoun")
        if not profile.aliases:
            gaps.append("aliases")
        if not profile.narration_labels:
            gaps.append("narration_labels")
        if len(profile.source_chapters) < 1 and len(profile.appearances) < 3:
            gaps.append("cross_chapter_evidence")
    elif profile.tier == CharacterTier.SUPPORTING:
        if not profile.visual.hair and not profile.visual.outfit and not profile.descriptors:
            gaps.append("visual")
        if not profile.pronoun or profile.pronoun == "they":
            gaps.append("pronoun")

    return gaps


def apply_findings(profile: CharacterProfile, findings: list[CharacterFinding]) -> CharacterProfile:
    aliases = list(profile.aliases)
    descriptors = list(profile.descriptors)
    visual = profile.visual.model_copy()
    role = profile.role
    pronoun = profile.pronoun
    tier = profile.tier
    narration_labels = list(profile.narration_labels)
    source_chapters = list(profile.source_chapters)
    confidence = profile.confidence
    canonical_name = profile.canonical_name

    for finding in findings:
        confidence = max(confidence, finding.confidence)
        if finding.chapter and finding.chapter not in source_chapters:
            source_chapters.append(finding.chapter)

        if finding.field == "canonical_name" and not canonical_name:
            canonical_name = finding.value
        elif finding.field == "alias" and finding.value not in aliases:
            aliases.append(finding.value)
        elif finding.field == "descriptor" and finding.value not in descriptors:
            descriptors.append(finding.value)
        elif finding.field == "role" and not role:
            role = finding.value
        elif finding.field == "pronoun":
            pronoun = finding.value
        elif finding.field == "tier" and finding.value == "main":
            tier = CharacterTier.MAIN
        elif finding.field == "visual.hair" and not visual.hair:
            visual.hair = finding.value
        elif finding.field == "visual.outfit" and not visual.outfit:
            visual.outfit = finding.value
        elif finding.field == "visual.build" and not visual.build:
            visual.build = finding.value
        elif finding.field == "narration_labels" and finding.value not in narration_labels:
            narration_labels.append(finding.value)

    return CharacterProfile(
        id=profile.id,
        canonical_name=canonical_name or profile.canonical_name,
        tier=tier,
        aliases=aliases,
        descriptors=descriptors,
        pronoun=pronoun,
        role=role,
        first_seen_panel=profile.first_seen_panel,
        appearances=profile.appearances,
        visual=visual,
        narration_labels=narration_labels,
        sufficiency=profile.sufficiency,
        confidence=confidence,
        source_chapters=source_chapters,
    )


def detect_protagonist(bible: SeriesBible, config: dict[str, Any], wiki_mc_id: str | None = None) -> str:
    if wiki_mc_id and wiki_mc_id in bible.characters:
        return wiki_mc_id

    scored: list[tuple[float, str]] = []
    for profile in bible.characters.values():
        if profile.merged_into:
            continue
        score = len(profile.appearances) * 2.0
        score += len(profile.source_chapters) * 5.0
        score += profile.confidence * 10.0
        if profile.role == "protagonist":
            score += 20.0
        if profile.tier == CharacterTier.MAIN:
            score += 15.0
        if "hunter" in profile.role.lower() or any("hunter" in d.lower() for d in profile.descriptors):
            score += 5.0
        scored.append((score, profile.id))

    if not scored:
        return ""
    scored.sort(reverse=True)
    return scored[0][1]


def set_protagonist_labels(bible: SeriesBible, protagonist_id: str, config: dict[str, Any]) -> None:
    if not protagonist_id or protagonist_id not in bible.characters:
        return
    mc_labels = get_nested(config, "characters", "mc_labels", default=["MC", "the protagonist", "our guy"])
    profile = bible.characters[protagonist_id]
    labels = list(dict.fromkeys([*mc_labels, profile.canonical_name, "the E-Rank hunter"]))
    if profile.role:
        labels.append(profile.role)
    merge_profile(
        bible,
        CharacterProfile(
            id=profile.id,
            canonical_name=profile.canonical_name,
            tier=CharacterTier.MAIN,
            aliases=profile.aliases,
            descriptors=profile.descriptors,
            pronoun=profile.pronoun or "he",
            role=profile.role or "protagonist",
            first_seen_panel=profile.first_seen_panel,
            appearances=profile.appearances,
            visual=profile.visual,
            narration_labels=labels,
            sufficiency="sufficient",
            confidence=max(profile.confidence, 0.85),
            source_chapters=profile.source_chapters,
        ),
    )
    bible.protagonist_id = protagonist_id


def run_character_quest(
    bible: SeriesBible,
    meta: ProjectMeta,
    config: dict[str, Any],
    *,
    glossary: dict[str, Any] | None = None,
    scene_cards: list[SceneCard] | None = None,
    ocr_path: Path | None = None,
    wiki_mc_id: str | None = None,
) -> SeriesBible:
    max_iters = int(get_nested(config, "characters", "quest_max_iterations", default=4))
    glossary = glossary or {}
    scene_cards = scene_cards or []

    spaths = series_paths(find_repo_root(), meta.series_slug)
    quest_states: dict[str, CharacterQuestState] = {}

    char_ids = [cid for cid, p in bible.characters.items() if not p.merged_into]
    for char_id in char_ids:
        profile = bible.characters[char_id]
        state = CharacterQuestState(char_id=char_id)
        for iteration in range(max_iters):
            gaps = evaluate_sufficiency(profile, protagonist_id=bible.protagonist_id)
            if not gaps:
                profile.sufficiency = "sufficient"
                break
            findings = search_sources(
                profile,
                gaps,
                meta=meta,
                config=config,
                glossary=glossary,
                scene_cards=scene_cards,
                ocr_path=ocr_path,
            )
            state.iterations = iteration + 1
            state.gaps = gaps
            state.sources_used = list(dict.fromkeys([*state.sources_used, *[f.source for f in findings]]))
            if not findings:
                profile.sufficiency = "partial"
                break
            profile = apply_findings(profile, findings)
            bible.characters[char_id] = profile
        else:
            profile.sufficiency = "partial" if evaluate_sufficiency(profile, protagonist_id=bible.protagonist_id) else "sufficient"
            bible.characters[char_id] = profile
        quest_states[char_id] = state

    protagonist_id = detect_protagonist(bible, config, wiki_mc_id=wiki_mc_id)
    if protagonist_id:
        set_protagonist_labels(bible, protagonist_id, config)

    consolidate_profiles(bible, config)
    bible.quest_completed = True
    save_series_bible(bible)
    save_json(spaths["character_quest"], list(quest_states.values()))
    console.print(
        f"[green]Character quest complete[/] — protagonist={bible.protagonist_id or 'unknown'}, "
        f"{len(bible.characters)} profiles"
    )
    return bible
