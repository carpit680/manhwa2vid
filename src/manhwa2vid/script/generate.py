"""Recap script generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.characters.bible import format_bible_for_prompt, load_series_bible, naming_priority_rules
from manhwa2vid.characters.link import run_cast_linking
from manhwa2vid.config import get_nested
from manhwa2vid.llm.provider import get_llm_provider
from manhwa2vid.models import (
    PanelCast,
    ProjectMeta,
    SceneCard,
    ScriptBeat,
    ScriptDraft,
    ScriptOutlineBeat,
    SeriesBible,
    save_json,
)
from manhwa2vid.panels.filter import load_story_scene_cards
from manhwa2vid.script.lint import banned_words, lint_and_rewrite_script

console = Console()


def _load_prompt_template(name: str) -> str:
    path = Path(__file__).parent / "prompts" / name
    return path.read_text(encoding="utf-8")


def _scene_cards_to_context(cards: list[SceneCard]) -> str:
    blocks = []
    for i, card in enumerate(cards, 1):
        speakers = ", ".join(card.speakers) if card.speakers else "(none)"
        people = ", ".join(
            p.name_used or p.descriptor or p.ref for p in card.people
        ) or "(none)"
        blocks.append(
            f"Scene {i} [{', '.join(card.panel_ids)}]: "
            f"people={people}; speakers={speakers}; action={card.action}; mood={card.mood}; "
            f"dialogue={card.dialogue_summary}; terms={card.key_terms}"
        )
    return "\n".join(blocks)


def _cast_context_for_beats(
    outline_beats: list[ScriptOutlineBeat],
    attribution: list[PanelCast],
) -> str:
    attr_map = {row.panel_id: row for row in attribution}
    lines: list[str] = []
    for beat in outline_beats:
        people: list[str] = []
        for panel_id in beat.panel_ids:
            row = attr_map.get(panel_id)
            if not row:
                continue
            for person in row.people:
                label = person.name_used or person.descriptor or person.ref
                if label and label not in people:
                    people.append(label)
        char_ids = ", ".join(beat.character_ids) if beat.character_ids else "(infer from panels)"
        lines.append(
            f"Beat {beat.beat_id} [{', '.join(beat.panel_ids)}]: "
            f"char_ids={char_ids}; on_screen={', '.join(people) or '(none)'}; plot={beat.plot_beat}"
        )
    return "\n".join(lines)


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


def _beats_to_markdown(draft: ScriptDraft) -> str:
    lines = [
        f"# {draft.title} — Chapters {draft.chapters}",
        "",
        f"**Hook:** {draft.hook}",
        "",
        "## Beats",
        "",
    ]
    for beat in draft.beats:
        lines.extend(
            [
                f"### Beat {beat.beat_id}",
                f"<!-- panels: {', '.join(beat.panel_ids)} -->",
                "",
                beat.narration,
                "",
            ]
        )
    lines.append("---")
    lines.append("Edit freely. Save approved version as script.final.md")
    return "\n".join(lines)


def _parse_markdown_beats(path: Path) -> list[ScriptBeat]:
    """Parse beats from markdown (for final script after human edit)."""
    text = path.read_text(encoding="utf-8")
    beats: list[ScriptBeat] = []
    current_panels: list[str] = []
    current_lines: list[str] = []
    beat_id = 0

    for line in text.splitlines():
        if line.startswith("<!-- panels:"):
            current_panels = [
                p.strip()
                for p in line.replace("<!-- panels:", "").replace("-->", "").split(",")
                if p.strip()
            ]
        elif line.startswith("### Beat"):
            if current_lines and beat_id:
                beats.append(
                    ScriptBeat(
                        beat_id=beat_id,
                        panel_ids=current_panels or [f"unknown_{beat_id}"],
                        narration=" ".join(current_lines).strip(),
                    )
                )
            beat_id += 1
            current_lines = []
        elif line.startswith("#") or line.startswith("**Hook:") or line == "---":
            continue
        elif beat_id > 0 and line.strip():
            current_lines.append(line.strip())

    if current_lines and beat_id:
        beats.append(
            ScriptBeat(
                beat_id=beat_id,
                panel_ids=current_panels or [f"unknown_{beat_id}"],
                narration=" ".join(current_lines).strip(),
            )
        )
    return beats


def load_script_beats(paths: dict[str, Path]) -> ScriptDraft:
    if paths["script_json"].exists():
        data = json.loads(paths["script_json"].read_text())
        return ScriptDraft.model_validate(data)
    final = paths["script_final"] if paths["script_final"].exists() else paths["script_draft"]
    beats = _parse_markdown_beats(final)
    meta = json.loads(paths["meta"].read_text())
    return ScriptDraft(title=meta["title"], chapters=meta["chapters"], beats=beats)


def _covered_panel_ids(beats: list[ScriptBeat]) -> set[str]:
    return {pid for beat in beats for pid in beat.panel_ids}


def _narration_from_card(card: SceneCard, bible: SeriesBible) -> str:
    labels: list[str] = []
    for person in card.people:
        if person.ref in bible.characters:
            labels.append(bible.characters[person.ref].canonical_name)
        elif person.name_used:
            labels.append(person.name_used)
        elif person.descriptor:
            labels.append(person.descriptor)
    if card.speakers:
        labels.extend(card.speakers)
    lead = labels[0] if labels else "Someone"
    parts = [p.strip() for p in (card.action, card.dialogue_summary) if p and p.strip()]
    if parts:
        return f"{lead}: {'. '.join(parts)}"[:400]
    return f"{lead} appears in a key moment."


def _expand_beats_from_scenes(
    cards: list[SceneCard],
    beats: list[ScriptBeat],
    bible: SeriesBible,
) -> list[ScriptBeat]:
    """Fill in beats for any panels the LLM skipped."""
    covered = _covered_panel_ids(beats)
    next_id = max((beat.beat_id for beat in beats), default=0) + 1
    expanded = list(beats)

    for card in cards:
        for panel_id in card.panel_ids:
            if panel_id in covered:
                continue
            expanded.append(
                ScriptBeat(
                    beat_id=next_id,
                    panel_ids=[panel_id],
                    narration=_narration_from_card(card, bible)[:400],
                )
            )
            covered.add(panel_id)
            next_id += 1

    expanded.sort(key=lambda beat: beat.beat_id)
    for index, beat in enumerate(expanded, start=1):
        beat.beat_id = index
    return expanded


def _run_outline_pass(
    meta: ProjectMeta,
    cards: list[SceneCard],
    bible: SeriesBible,
    config: dict[str, Any],
) -> tuple[str, list[ScriptOutlineBeat]]:
    template = _load_prompt_template("outline.txt")
    llm = get_llm_provider(config=config)
    model_name = get_nested(config, "script", "model", default="gpt-4o-mini")
    if hasattr(llm, "model"):
        llm.model = model_name

    user = (
        f"Title: {meta.title}\nChapters: {meta.chapters}\n\n"
        f"Protagonist id: {bible.protagonist_id or '(detect from bible)'}\n\n"
        f"{naming_priority_rules(bible, config)}\n\n"
        f"Character bible (use character_ids from here):\n{format_bible_for_prompt(bible)}\n\n"
        f"Scene cards:\n{_scene_cards_to_context(cards)}"
    )
    raw = llm.complete(template, user, json_mode=True)
    data = json.loads(raw)
    outline = [ScriptOutlineBeat.model_validate(b) for b in data.get("beats", [])]
    return str(data.get("hook", "")), outline


def _run_narration_pass(
    meta: ProjectMeta,
    outline_beats: list[ScriptOutlineBeat],
    hook: str,
    bible: SeriesBible,
    attribution: list[PanelCast],
    config: dict[str, Any],
) -> list[ScriptBeat]:
    template = _load_prompt_template("recap.txt")
    target_wpm = get_nested(config, "script", "target_wpm", default=150)
    commentary = meta.commentary_level or get_nested(config, "script", "commentary_level", default="light")
    genz_level = get_nested(config, "script", "genz_level", default="medium")
    max_asides = int(get_nested(config, "script", "max_narrator_asides", default=2))
    ban = ", ".join(banned_words(config))

    system = template.format(
        target_wpm=target_wpm,
        commentary_level=commentary,
        genz_level=genz_level,
        max_narrator_asides=max_asides,
        ban_words=ban,
        naming_priority_rules=naming_priority_rules(bible, config),
    )

    llm = get_llm_provider(config=config)
    model_name = get_nested(config, "script", "model", default="gpt-4o-mini")
    if hasattr(llm, "model"):
        llm.model = model_name

    user = (
        f"Title: {meta.title}\nChapters: {meta.chapters}\nHook (from outline): {hook}\n\n"
        f"Protagonist id: {bible.protagonist_id} — use MC/protagonist labels for this character after beat 1\n\n"
        f"{naming_priority_rules(bible, config)}\n\n"
        f"Story so far:\n{_story_so_far(bible, meta)}\n\n"
        f"Character bible:\n{format_bible_for_prompt(bible)}\n\n"
        f"Beat outline (convert plot_beat to narration; keep beat_id and panel_ids):\n"
        f"{_cast_context_for_beats(outline_beats, attribution)}"
    )
    raw = llm.complete(system, user, json_mode=True)
    data = json.loads(raw)
    return [ScriptBeat.model_validate(b) for b in data.get("beats", [])]


def generate_script(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> ScriptDraft:
    if paths["script_draft"].exists() and not force:
        console.print(f"[dim]Using existing script draft[/] → {paths['script_draft']}")
        return load_script_beats(paths)

    if not paths["scene_enriched_json"].exists() or force:
        run_cast_linking(meta, paths, config, force=force)

    cards = load_story_scene_cards(paths)
    if not cards:
        scene_data = json.loads(paths["scene_json"].read_text())
        cards = [SceneCard.model_validate(s) for s in scene_data]

    bible = load_series_bible(meta.series_slug, meta.title)

    hook, outline_beats = _run_outline_pass(meta, cards, bible, config)
    save_json(
        paths["script_outline_json"],
        {"hook": hook, "beats": [b.model_dump(mode="json") for b in outline_beats]},
    )

    attribution: list[PanelCast] = []
    if paths["cast_attribution_json"].exists():
        attribution = [
            PanelCast.model_validate(a)
            for a in json.loads(paths["cast_attribution_json"].read_text(encoding="utf-8"))
        ]

    beats = _run_narration_pass(meta, outline_beats, hook, bible, attribution, config)

    all_panels = {pid for card in cards for pid in card.panel_ids}
    covered = _covered_panel_ids(beats)
    if len(covered) < len(all_panels):
        console.print(
            f"[yellow]Script covered {len(covered)}/{len(all_panels)} panels — expanding from scene cards.[/]"
        )
        beats = _expand_beats_from_scenes(cards, beats, bible)

    beats = lint_and_rewrite_script(beats, bible, paths["cast_attribution_json"], config)

    draft = ScriptDraft(
        title=meta.title,
        chapters=meta.chapters,
        beats=beats,
        hook=hook,
    )

    save_json(paths["script_json"], draft)
    paths["script_draft"].write_text(_beats_to_markdown(draft), encoding="utf-8")
    console.print(f"[green]Script draft written[/] → {paths['script_draft']}")
    return draft
