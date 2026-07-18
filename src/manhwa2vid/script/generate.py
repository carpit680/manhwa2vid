"""Recap script generation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.characters.bible import format_bible_for_prompt, load_series_bible, naming_priority_rules
from manhwa2vid.characters.link import run_cast_linking
from manhwa2vid.config import get_nested
from manhwa2vid.llm.provider import get_llm_provider
from manhwa2vid.models import (
    ChapterSynopsis,
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
from manhwa2vid.script.synopsis import (
    compact_scene_evidence,
    format_synopsis_for_prompt,
    generate_chapter_synopsis,
)

console = Console()

_PANEL_SORT_RE = re.compile(r"p(\d+)_(\d+)", re.I)


def _load_prompt_template(name: str) -> str:
    path = Path(__file__).parent / "prompts" / name
    return path.read_text(encoding="utf-8")


def _panel_sort_key(panel_id: str) -> tuple[int, int, str]:
    match = _PANEL_SORT_RE.match(panel_id)
    if match:
        return int(match.group(1)), int(match.group(2)), panel_id
    return 9999, 9999, panel_id


def _scene_cards_to_context(cards: list[SceneCard], bible: SeriesBible) -> str:
    return compact_scene_evidence(cards, bible)


def _sticky_label(person: Any, bible: SeriesBible) -> str:
    if person.ref in bible.characters:
        profile = bible.characters[person.ref]
        if profile.tier.value in ("main", "supporting") or profile.canonical_name[:1].isupper():
            # Prefer canonical name for known cast; keep descriptor only for pure minors
            if not profile.canonical_name.lower().startswith(("guy ", "man ", "woman ", "blonde ")):
                return profile.canonical_name
    return person.name_used or person.descriptor or person.ref


def _cast_context_for_beats(
    outline_beats: list[ScriptOutlineBeat],
    attribution: list[PanelCast],
    bible: SeriesBible,
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
                mc_tag = " [MC]" if person.ref == bible.protagonist_id else ""
                label = _sticky_label(person, bible)
                entry = f"{label}(ref={person.ref}{mc_tag})"
                if entry not in people:
                    people.append(entry)
        char_ids = ", ".join(beat.character_ids) if beat.character_ids else "(from cast below)"
        lines.append(
            f"Beat {beat.beat_id} [{', '.join(beat.panel_ids)}]: "
            f"char_ids={char_ids}; on_screen={'; '.join(people) or '(none)'}; plot={beat.plot_beat}\n"
            f"  Tell the story event; panels illustrate — protagonist id={bible.protagonist_id or '?'}"
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


def _covered_panel_ids(beats: list[ScriptBeat] | list[ScriptOutlineBeat]) -> set[str]:
    return {pid for beat in beats for pid in beat.panel_ids}


def _attach_missing_panels_to_beats(
    all_panel_ids: list[str],
    beats: list[ScriptBeat],
) -> list[ScriptBeat]:
    """Attach uncovered story panels to the nearest story beat — never invent caption beats."""
    if not beats:
        return beats

    covered = _covered_panel_ids(beats)
    missing = [pid for pid in all_panel_ids if pid not in covered]
    if not missing:
        return beats

    # Build ordered list of (panel_id, beat_index) anchors from existing coverage
    anchors: list[tuple[str, int]] = []
    for idx, beat in enumerate(beats):
        for pid in sorted(beat.panel_ids, key=_panel_sort_key):
            anchors.append((pid, idx))
    if not anchors:
        beats[0].panel_ids = list(dict.fromkeys([*beats[0].panel_ids, *missing]))
        return beats

    for panel_id in missing:
        best_idx = 0
        best_dist = 10**9
        p_key = _panel_sort_key(panel_id)
        for anchor_id, beat_idx in anchors:
            a_key = _panel_sort_key(anchor_id)
            dist = abs(p_key[0] - a_key[0]) * 100 + abs(p_key[1] - a_key[1])
            if dist < best_dist:
                best_dist = dist
                best_idx = beat_idx
        beats[best_idx].panel_ids = list(dict.fromkeys([*beats[best_idx].panel_ids, panel_id]))
        beats[best_idx].panel_ids.sort(key=_panel_sort_key)
        anchors.append((panel_id, best_idx))

    console.print(
        f"[yellow]Attached {len(missing)} uncovered panel(s) to nearest story beats[/] "
        f"(no caption filler)"
    )
    return beats


def _panel_cast_index(cards: list[SceneCard], bible: SeriesBible) -> str:
    """Compact panel → cast map for outline coverage (no frame captions)."""
    lines: list[str] = []
    for card in cards:
        if not card.is_story:
            continue
        cast_parts: list[str] = []
        for person in card.people:
            mc_tag = " [MC]" if person.ref == bible.protagonist_id else ""
            label = person.name_used or person.descriptor or person.ref
            if person.ref in bible.characters:
                profile = bible.characters[person.ref]
                if not profile.canonical_name.lower().startswith(("guy ", "man ", "woman ", "blonde ")):
                    label = profile.canonical_name
            cast_parts.append(f"{label}{mc_tag}")
        lines.append(f"{','.join(card.panel_ids)}: {'; '.join(cast_parts) or '(none)'}")
    return "\n".join(lines)


def _complete_json(llm: Any, system: str, user: str, *, fallback_model: str = "llama-3.3-70b-versatile") -> dict[str, Any]:
    """Complete with JSON mode; retry once on validate failure with fallback model."""
    try:
        raw = llm.complete(system, user, json_mode=True)
        if raw.strip():
            return json.loads(raw)
    except Exception as exc:
        console.print(f"[yellow]JSON complete failed ({getattr(llm, 'model', '?')}):[/] {exc}")

    original = getattr(llm, "model", None)
    if hasattr(llm, "model") and original != fallback_model:
        console.print(f"[yellow]Retrying JSON with fallback model[/] {fallback_model}")
        llm.model = fallback_model
        try:
            # Trim user payload for fallback reliability
            trimmed = user if len(user) < 24000 else user[:12000] + "\n…\n" + user[-8000:]
            raw = llm.complete(system, trimmed, json_mode=True)
            return json.loads(raw)
        finally:
            if original:
                llm.model = original
    raise RuntimeError("script JSON generation failed")


def _run_outline_pass(
    meta: ProjectMeta,
    cards: list[SceneCard],
    bible: SeriesBible,
    synopsis: ChapterSynopsis,
    config: dict[str, Any],
) -> tuple[str, list[ScriptOutlineBeat]]:
    template = _load_prompt_template("outline.txt")
    max_beats = int(get_nested(config, "script", "max_beats", default=18))
    system = template.format(max_beats=max_beats)

    llm = get_llm_provider(config=config)
    model_name = get_nested(config, "script", "model", default="gpt-4o-mini")
    if hasattr(llm, "model"):
        llm.model = model_name

    all_panel_ids = sorted({pid for card in cards for pid in card.panel_ids}, key=_panel_sort_key)
    user = (
        f"Title: {meta.title}\nChapters: {meta.chapters}\n\n"
        f"Protagonist id: {bible.protagonist_id or '(detect from bible)'}\n"
        f"Soft max beats: {max_beats}\n"
        f"All story panel_ids to cover ({len(all_panel_ids)}): {', '.join(all_panel_ids)}\n\n"
        f"{naming_priority_rules(bible, config)}\n\n"
        f"Chapter synopsis (SOURCE OF TRUTH):\n{format_synopsis_for_prompt(synopsis)}\n\n"
        f"Story so far:\n{_story_so_far(bible, meta)}\n\n"
        f"Character bible:\n{format_bible_for_prompt(bible)}\n\n"
        f"Panel cast index (assign every panel_id to a beat; do NOT caption frames):\n"
        f"{_panel_cast_index(cards, bible)}"
    )
    data = _complete_json(llm, system, user)
    outline = [ScriptOutlineBeat.model_validate(b) for b in data.get("beats", [])]
    return str(data.get("hook", synopsis.logline)), outline


def _run_narration_pass(
    meta: ProjectMeta,
    outline_beats: list[ScriptOutlineBeat],
    hook: str,
    bible: SeriesBible,
    attribution: list[PanelCast],
    synopsis: ChapterSynopsis,
    config: dict[str, Any],
) -> list[ScriptBeat]:
    template = _load_prompt_template("recap.txt")
    target_wpm = get_nested(config, "script", "target_wpm", default=150)
    commentary = meta.commentary_level or get_nested(config, "script", "commentary_level", default="light")
    genz_level = get_nested(config, "script", "genz_level", default="medium")
    max_asides = int(get_nested(config, "script", "max_narrator_asides", default=1))
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
        f"Title: {meta.title}\nChapters: {meta.chapters}\nHook: {hook}\n\n"
        f"Protagonist id: {bible.protagonist_id} — full name only in beat 1; then MC/protagonist/he\n\n"
        f"{naming_priority_rules(bible, config)}\n\n"
        f"Chapter synopsis (SOURCE OF TRUTH):\n{format_synopsis_for_prompt(synopsis)}\n\n"
        f"Story so far:\n{_story_so_far(bible, meta)}\n\n"
        f"Character bible:\n{format_bible_for_prompt(bible)}\n\n"
        f"Beat outline (convert plot_beat to narration; keep beat_id and panel_ids):\n"
        f"{_cast_context_for_beats(outline_beats, attribution, bible)}"
    )
    data = _complete_json(llm, system, user)
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

    attribution: list[PanelCast] = []
    if paths["cast_attribution_json"].exists():
        attribution = [
            PanelCast.model_validate(a)
            for a in json.loads(paths["cast_attribution_json"].read_text(encoding="utf-8"))
        ]

    synopsis = generate_chapter_synopsis(
        meta,
        cards,
        bible,
        attribution,
        config,
        out_path=paths["script_synopsis_json"],
    )
    # Reload bible after synopsis sticky-name merges
    bible = load_series_bible(meta.series_slug, meta.title)

    hook, outline_beats = _run_outline_pass(meta, cards, bible, synopsis, config)
    save_json(
        paths["script_outline_json"],
        {"hook": hook, "beats": [b.model_dump(mode="json") for b in outline_beats]},
    )

    beats = _run_narration_pass(meta, outline_beats, hook, bible, attribution, synopsis, config)

    all_panels = sorted({pid for card in cards for pid in card.panel_ids}, key=_panel_sort_key)
    covered = _covered_panel_ids(beats)
    if len(covered) < len(all_panels):
        beats = _attach_missing_panels_to_beats(all_panels, beats)

    beats = lint_and_rewrite_script(beats, bible, paths["cast_attribution_json"], config)

    draft = ScriptDraft(
        title=meta.title,
        chapters=meta.chapters,
        beats=beats,
        hook=hook,
    )

    save_json(paths["script_json"], draft)
    paths["script_draft"].write_text(_beats_to_markdown(draft), encoding="utf-8")
    console.print(f"[green]Script draft written[/] → {paths['script_draft']} ({len(beats)} beats)")
    return draft
