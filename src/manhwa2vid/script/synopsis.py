"""Chapter-level story synopsis before beat outlining."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.characters.bible import format_bible_for_prompt, merge_profile, naming_priority_rules, save_series_bible
from manhwa2vid.characters.bible import slugify_char_id
from manhwa2vid.config import get_nested
from manhwa2vid.llm.provider import get_llm_provider
from manhwa2vid.models import (
    ChapterSynopsis,
    CharacterProfile,
    CharacterTier,
    NamedCastEntry,
    PanelCast,
    ProjectMeta,
    SceneCard,
    SeriesBible,
    VisualProfile,
    save_json,
)

console = Console()


def _load_prompt_template(name: str) -> str:
    path = Path(__file__).parent / "prompts" / name
    return path.read_text(encoding="utf-8")


def _story_so_far(bible: SeriesBible, meta: ProjectMeta) -> str:
    if not bible.chapter_summaries:
        return "(first chapter — no prior story)"
    chapter_key = meta.chapters.split("-")[0].strip()
    prior = [
        f"Ch {ch}: {summary}"
        for ch, summary in sorted(bible.chapter_summaries.items(), key=lambda x: x[0])
        if ch != chapter_key
    ]
    return "\n".join(prior) if prior else "(first chapter — no prior story)"


def compact_scene_evidence(cards: list[SceneCard], bible: SeriesBible) -> str:
    """Panel evidence for synopsis — facts only, no hedge encouragement."""
    lines: list[str] = []
    for card in cards:
        if not card.is_story:
            continue
        cast_parts: list[str] = []
        for person in card.people:
            mc_tag = " [MC]" if person.ref == bible.protagonist_id else ""
            label = person.name_used or person.descriptor or person.ref
            cast_parts.append(f"{label}(ref={person.ref}{mc_tag})")
        speakers = ", ".join(card.speakers) if card.speakers else "(none)"
        lines.append(
            f"[{', '.join(card.panel_ids)}] cast={'; '.join(cast_parts) or '(none)'}; "
            f"speakers={speakers}; what={card.action}; said={card.dialogue_summary}; terms={card.key_terms}"
        )
    return "\n".join(lines)


def format_synopsis_for_prompt(synopsis: ChapterSynopsis) -> str:
    cast_lines = []
    for entry in synopsis.named_cast:
        desc = ", ".join(entry.descriptors) if entry.descriptors else ""
        cast_lines.append(
            f"- {entry.name} (id={entry.char_id or '?'}, role={entry.role or '?'}"
            f"{f', looks: {desc}' if desc else ''})"
            f"{f' — {entry.notes}' if entry.notes else ''}"
        )
    fact_lines = [f"  - {fact}" for fact in synopsis.plot_facts] or ["  (none)"]
    thread_lines = [f"  - {t}" for t in synopsis.open_threads] or ["  (none)"]
    parts = [
        f"Logline: {synopsis.logline}",
        "Arc:",
        *[f"  {i}. {act}" for i, act in enumerate(synopsis.arc, 1)],
        "Named cast:",
        *(cast_lines or ["  (none)"]),
        "Plot facts:",
        *fact_lines,
        "Open threads:",
        *thread_lines,
    ]
    return "\n".join(parts)


def apply_named_cast_to_bible(bible: SeriesBible, named_cast: list[NamedCastEntry]) -> None:
    """Merge synopsis sticky names into the series bible as aliases/roles."""
    for entry in named_cast:
        if not entry.name.strip():
            continue
        char_id = entry.char_id.strip() or slugify_char_id(entry.name)
        existing = bible.characters.get(char_id)
        if existing is None and entry.descriptors:
            desc_set = {d.lower() for d in entry.descriptors}
            for profile in bible.characters.values():
                profile_desc = {x.lower() for x in profile.descriptors} | {profile.canonical_name.lower()}
                if desc_set & profile_desc:
                    char_id = profile.id
                    existing = profile
                    break

        if existing:
            aliases = list(dict.fromkeys([*existing.aliases, *entry.descriptors]))
            if entry.name.lower() != existing.canonical_name.lower():
                # Prefer real name as canonical when upgrading from a descriptor profile
                use_name = entry.name if existing.tier != CharacterTier.MAIN else existing.canonical_name
                if existing.tier != CharacterTier.MAIN and entry.name[0].isupper():
                    aliases = list(dict.fromkeys([*aliases, existing.canonical_name]))
                else:
                    use_name = existing.canonical_name
            else:
                use_name = existing.canonical_name
            merge_profile(
                bible,
                CharacterProfile(
                    id=existing.id,
                    canonical_name=use_name,
                    tier=existing.tier if existing.tier == CharacterTier.MAIN else CharacterTier.SUPPORTING,
                    aliases=aliases,
                    descriptors=list(dict.fromkeys([*existing.descriptors, *entry.descriptors])),
                    pronoun=existing.pronoun,
                    role=entry.role or existing.role,
                    first_seen_panel=existing.first_seen_panel,
                    appearances=existing.appearances,
                    visual=existing.visual,
                    narration_labels=existing.narration_labels,
                    sufficiency=existing.sufficiency,
                    confidence=max(existing.confidence, 0.7),
                    source_chapters=existing.source_chapters,
                ),
            )
            continue

        merge_profile(
            bible,
            CharacterProfile(
                id=char_id,
                canonical_name=entry.name,
                tier=CharacterTier.MAIN if char_id == bible.protagonist_id else CharacterTier.SUPPORTING,
                aliases=list(entry.descriptors),
                descriptors=list(entry.descriptors),
                pronoun="he",
                role=entry.role,
                visual=VisualProfile(),
                confidence=0.7,
                sufficiency="pending",
            ),
        )


def generate_chapter_synopsis(
    meta: ProjectMeta,
    cards: list[SceneCard],
    bible: SeriesBible,
    attribution: list[PanelCast],
    config: dict[str, Any],
    *,
    out_path: Path | None = None,
) -> ChapterSynopsis:
    template = _load_prompt_template("synopsis.txt")
    llm = get_llm_provider(config=config)
    model_name = get_nested(config, "script", "model", default="gpt-4o-mini")
    if hasattr(llm, "model"):
        llm.model = model_name

    attr_lines = []
    for row in attribution[:120]:
        people = ", ".join(
            f"{p.name_used or p.descriptor or p.ref}({p.ref})" for p in row.people
        )
        attr_lines.append(f"{row.panel_id}: {people or '(none)'}")

    user = (
        f"Title: {meta.title}\nChapters: {meta.chapters}\n\n"
        f"Protagonist id: {bible.protagonist_id or '(detect from bible)'}\n\n"
        f"{naming_priority_rules(bible, config)}\n\n"
        f"Story so far:\n{_story_so_far(bible, meta)}\n\n"
        f"Character bible:\n{format_bible_for_prompt(bible)}\n\n"
        f"Cast attribution (panel → people):\n" + "\n".join(attr_lines[:100]) + "\n\n"
        f"Scene evidence (use to build ONE coherent chapter story):\n"
        f"{compact_scene_evidence(cards, bible)}"
    )
    raw = llm.complete(template, user, json_mode=True)
    data = json.loads(raw)
    named = []
    for item in data.get("named_cast", []):
        if isinstance(item, dict):
            named.append(NamedCastEntry.model_validate(item))
    synopsis = ChapterSynopsis(
        logline=str(data.get("logline", "")),
        arc=[str(a) for a in data.get("arc", [])],
        named_cast=named,
        plot_facts=[str(f) for f in data.get("plot_facts", [])],
        open_threads=[str(t) for t in data.get("open_threads", [])],
    )
    apply_named_cast_to_bible(bible, synopsis.named_cast)
    save_series_bible(bible)
    if out_path is not None:
        save_json(out_path, synopsis)
    console.print(
        f"[green]Chapter synopsis[/] — {len(synopsis.arc)} acts, "
        f"{len(synopsis.named_cast)} sticky cast, {len(synopsis.plot_facts)} facts"
    )
    return synopsis
