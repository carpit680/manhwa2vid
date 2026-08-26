"""TTS orchestration and timeline building."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress

from manhwa2vid.config import get_nested
from manhwa2vid.models import ProjectMeta, save_json
from manhwa2vid.panels.filter import load_story_panels
from manhwa2vid.script.generate import load_script_beats
from manhwa2vid.script.sentences import split_sentences
from manhwa2vid.tts.provider import get_tts_provider
from manhwa2vid.video.timeline import _wav_duration, build_timeline

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
                _ensure_segments_sidecar(beat.narration, out)
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
    except Exception as exc:
        # Say so. This was a bare `except: salience = None`, and a swallowed failure here
        # silently downgrades panel curation to a blind positional stride for the whole
        # video — the writer's key_panel_ids stop being honoured and nobody is told.
        console.print(f"[yellow]Panel salience unavailable ({exc}) — using key panels only[/]")
        salience = None
    # Join the align stage's sentence->panel claims with the sidecars' measured
    # per-sentence seconds. Durations only exist here (sidecars are written at
    # synthesis), which is why the shot list stores claims and the plan is built now.
    shot_plan = None
    if paths["script_shotlist_json"].exists():
        from manhwa2vid.script.match import plan_shots
        from manhwa2vid.video.timeline import _subdivide_segments, load_beat_segments

        shotlist = json.loads(paths["script_shotlist_json"].read_text(encoding="utf-8"))
        segments_by_beat = {
            b.beat_id: _subdivide_segments(load_beat_segments(audio_dir, b.beat_id) or [])
            for b in script.beats
        }
        floor = float(get_nested(config, "align", "min_shot_seconds", default=1.0))
        accent_floor = float(get_nested(config, "align", "accent_shot_seconds", default=0.4))
        # Bounded-fill candidates: story panels in reading order, minus visually-empty
        # ones — fill must never resurrect the blank panels the align stage excluded —
        # and minus bare-bubble panels (mostly solid bright blob): the first fill-frame
        # render measured 40% of frames bubble-dominant against the reference's 13.7%,
        # and fill walking through text-only panels was a main contributor. A panel the
        # MATCHER claims still shows (quoting its line is legitimate); fill just never
        # volunteers one.
        import cv2

        from manhwa2vid.panels.regions import is_text_only_panel
        from manhwa2vid.panels.split import is_visually_empty_file

        def _fill_worthy(p) -> bool:
            path = paths["root"] / p.image_path
            if is_visually_empty_file(path):
                return False
            img = cv2.imread(str(path))
            return img is None or not is_text_only_panel(img)

        fill_order = [p.id for p in panels if _fill_worthy(p)]
        shot_plan = plan_shots(
            shotlist,
            segments_by_beat,
            floor=floor,
            panel_order=fill_order,
            accent_floor=accent_floor,
        )
        if shot_plan:
            shots = sum(len(v) for v in shot_plan.values())
            console.print(f"[dim]Shot plan: {shots} shot(s) across {len(shot_plan)} beat(s)[/]")
        else:
            console.print(
                "[yellow]Shot list did not line up with the audio sidecars — "
                "falling back to airtime weighting[/]"
            )

    timeline = build_timeline(
        script.beats, panels, audio_dir, config, salience=salience, shot_plan=shot_plan
    )
    save_json(paths["timeline_json"], timeline)
    console.print(
        f"[green]TTS complete[/] — {len(script.beats)} beats, "
        f"timeline {timeline.total_duration:.1f}s"
    )

    _enforce_timeline_qa(script.beats, panels, timeline, paths, config)


def _ensure_segments_sidecar(narration: str, wav_path: Path) -> None:
    """Guarantee a per-sentence timing sidecar exists next to the WAV.

    Kokoro writes an EXACT one during synthesis (it splits on sentences internally and
    the chunk lengths are free). Every other provider returns opaque audio, so the
    fallback prorates the measured WAV duration across sentences by word count. Same
    schema either way — the timeline never knows which provider ran. Word-proration is
    systematically imperfect (pauses, numbers, names), which is exactly why the Kokoro
    path keeps the real numbers instead of estimating.
    """
    sidecar = wav_path.with_suffix(".segments.json")
    if sidecar.exists():
        return
    sentences = split_sentences(narration)
    if not sentences:
        return
    try:
        duration = _wav_duration(wav_path)
    except Exception:
        return
    total_words = sum(len(s.split()) for s in sentences) or 1
    sidecar.write_text(
        json.dumps(
            [
                {"text": s, "seconds": round(duration * len(s.split()) / total_words, 4)}
                for s in sentences
            ],
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )


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

    # Does the voice actually speak at the rate the script was PLANNED for?
    #
    # Nothing measured this, and the answer was no by 30%. `script.target_wpm` (235) is
    # what curate.words_per_shown_panel budgets panels from, but the TTS delivered ~171,
    # so the pipeline planned 9.79 words into 2.5s of screen time that really took 3.4s —
    # every panel dwelled a third too long and the whole video ran 55% longer than the
    # reference for the same chapters. The two values live in completely disjoint code
    # paths (`tts.kokoro_speed` only affects synthesis; `target_wpm` only affects script
    # planning) and nothing reconciled them, which is exactly why the miss was invisible.
    # This is the reconciliation: the one place where planned and delivered rate can be
    # compared, because it is the first point at which real audio exists.
    # Count words only for beats that actually reached the screen. A beat whose panels
    # all resolved to nothing is `continue`d in build_timeline, contributing words but no
    # seconds — so its narration inflated the apparent WPM and could mask a real pace
    # miss. Harmless while every beat was guaranteed panels; not once narration may
    # deliberately leave panels unshown.
    shipped_beat_ids = {e.beat_id for e in timeline.entries}
    total_words = sum(
        len(b.narration.split()) for b in beats if b.beat_id in shipped_beat_ids
    )
    total_seconds = sum(e.duration for e in timeline.entries)
    target_wpm = float(get_nested(config, "script", "target_wpm", default=235))
    tolerance = float(get_nested(config, "qa", "pace_tolerance", default=0.15))
    if total_words and total_seconds > 0 and target_wpm > 0:
        actual_wpm = total_words / (total_seconds / 60.0)
        drift = abs(actual_wpm - target_wpm) / target_wpm
        report.add(
            "narration-pace",
            True if drift <= tolerance else "warn",
            (
                f"narration delivers {actual_wpm:.0f} WPM but the script was budgeted at "
                f"{target_wpm:.0f} ({drift:.0%} off) — panel dwell and total runtime are "
                "planned from target_wpm, so they are wrong by the same factor; adjust "
                "tts.kokoro_speed (or target_wpm) until they agree"
            )
            if drift > tolerance else "",
            actual_wpm=round(actual_wpm, 1),
            target_wpm=target_wpm,
            words=total_words,
            seconds=round(total_seconds, 1),
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
