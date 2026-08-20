"""TTS orchestration and timeline building."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress

from manhwa2vid.models import ProjectMeta, save_json
from manhwa2vid.panels.filter import load_story_panels
from manhwa2vid.script.generate import load_script_beats
from manhwa2vid.tts.provider import get_tts_provider
from manhwa2vid.video.timeline import build_timeline

console = Console()


def run_tts_and_timeline(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> None:
    audio_dir = paths["audio"]
    if paths["timeline_json"].exists() and not force and any(audio_dir.glob("beat_*.wav")):
        console.print("[dim]Using cached TTS and timeline[/]")
        return

    script = load_script_beats(paths)
    if paths["script_final"].exists():
        from manhwa2vid.script.generate import _parse_markdown_beats

        beats = _parse_markdown_beats(paths["script_final"])
        script.beats = beats

    provider = get_tts_provider(config)
    console.print(f"[dim]TTS provider:[/] {type(provider).__name__}")

    audio_dir.mkdir(parents=True, exist_ok=True)

    with Progress() as progress:
        task = progress.add_task("Generating TTS", total=len(script.beats))
        for beat in script.beats:
            out = audio_dir / f"beat_{beat.beat_id:03d}.wav"
            if not out.exists() or force:
                provider.synthesize(beat.narration, out, config)
            progress.advance(task)

    panels = load_story_panels(paths)
    # Importance signals for panel curation: dialogue and people, from artifacts that
    # already exist. Curation is skipped gracefully when cards are absent (old projects).
    salience = None
    try:
        from manhwa2vid.panels.filter import load_story_scene_cards
        from manhwa2vid.video.timeline import panel_salience

        cards = load_story_scene_cards(paths)
        attribution = None
        if paths["cast_attribution_json"].exists():
            attribution = json.loads(paths["cast_attribution_json"].read_text(encoding="utf-8"))
        salience = panel_salience(cards, attribution)
    except Exception:
        salience = None
    timeline = build_timeline(script.beats, panels, audio_dir, config, salience=salience)
    save_json(paths["timeline_json"], timeline)
    console.print(
        f"[green]TTS complete[/] — {len(script.beats)} beats, "
        f"timeline {timeline.total_duration:.1f}s"
    )

    _enforce_timeline_qa(script.beats, panels, timeline, paths, config)


def _enforce_timeline_qa(beats, panels, timeline, paths, config) -> None:
    """Final-surface checks: what actually ships in the timeline, not what upstream
    stages intended. Catches blank entries, starved-into-static beats, and beats whose
    panels all vanished after the script was written."""
    from manhwa2vid.config import get_nested
    from manhwa2vid.panels.filter import is_blank_panel
    from manhwa2vid.qa import QAReport, enforce, qa_forced

    report = QAReport(stage="timeline")
    panel_map = {p.id: p for p in panels}

    blanks = sorted(
        {
            e.panel_id
            for e in timeline.entries
            if e.panel_id in panel_map and is_blank_panel(panel_map[e.panel_id], config)
        }
    )
    report.add(
        "no-blank-panels",
        not blanks,
        f"blank panel(s) shipped in timeline: {blanks}" if blanks else "",
        blanks=blanks,
    )

    max_sec = float(get_nested(config, "video", "max_panel_seconds", default=8.0))
    multiplier = float(get_nested(config, "video", "dwell_warn_multiplier", default=1.5))
    limit = max_sec * multiplier
    words_by_beat = {b.beat_id: len(b.narration.split()) for b in beats}
    panels_by_beat = {b.beat_id: max(len(b.panel_ids), 1) for b in beats}
    over = [
        f"beat {e.beat_id}: {e.duration:.1f}s on {e.panel_id} "
        f"({words_by_beat.get(e.beat_id, 0)}w / {panels_by_beat.get(e.beat_id, 1)} panel(s))"
        for e in timeline.entries
        if e.duration > limit
    ]
    report.add(
        "dwell-over-limit",
        "warn" if over else True,
        "; ".join(over[:4]) + " — narration too long for its panel count" if over else "",
        over=over,
    )

    report.add(
        "panel-budget",
        "warn" if timeline.dropped_panels else True,
        f"{timeline.dropped_panels} panel(s) dropped by the per-beat budget"
        if timeline.dropped_panels else "",
        dropped=timeline.dropped_panels,
    )

    orphan_beats = [
        b.beat_id for b in beats if b.panel_ids and not any(pid in panel_map for pid in b.panel_ids)
    ]
    report.add(
        "beat-panels-missing",
        "warn" if orphan_beats else True,
        f"beat(s) {orphan_beats} lost all panels to exclusion — nearest panel substituted"
        if orphan_beats else "",
        beats=orphan_beats,
    )

    enforce(report, paths["root"], force=qa_forced(config))
