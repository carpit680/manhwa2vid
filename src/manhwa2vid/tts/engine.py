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
from manhwa2vid.script.beats import load_script_beats
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
        from manhwa2vid.script.beats import _parse_markdown_beats

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
    # Panel salience (dialogue + people, derived from cast_attribution.json) used to be
    # loaded here as a curation signal. It was only ever consulted by build_timeline's
    # NO-SHOT-PLAN fallback — and the story-first path always writes a shot list, so it
    # never fired: both real projects had plans covering every beat. It died with the
    # CAST stage that produced its input.
    salience = None
    # Join the align stage's sentence->panel claims with the sidecars' measured
    # per-sentence seconds. Durations only exist here (sidecars are written at
    # synthesis), which is why the shot list stores claims and the plan is built now.
    shot_plan = None
    if paths["script_shotlist_json"].exists():
        from manhwa2vid.script.match import plan_shots_with_sentences
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

        from manhwa2vid.panels.regions import is_content_free, is_text_dominant_panel
        from manhwa2vid.panels.split import is_visually_empty_file

        text_only: set[str] = set()
        empty: set[str] = set()
        for p in panels:
            path = paths["root"] / p.image_path
            if is_visually_empty_file(path):
                empty.add(p.id)
                continue
            img = cv2.imread(str(path))
            # is_text_dominant_panel, NOT is_text_only_panel: the latter asks a tonal
            # question and is used on split BANDS, where it works. On whole panels it
            # flagged 0 of FP's 100 shown panels, because it needs a large BRIGHT region
            # and half the offending frames are white type on black. See regions.py.
            if img is not None and (is_text_dominant_panel(img) or is_content_free(img)):
                text_only.add(p.id)

        # Reading order for both fill candidates and bubble substitution. Text-only
        # panels stay in the ORDER (so a swap can find its neighbour) but are excluded
        # from fill by the planner itself.
        fill_order = [p.id for p in panels if p.id not in empty]
        shot_plan = plan_shots_with_sentences(
            shotlist,
            segments_by_beat,
            floor=floor,
            panel_order=fill_order,
            accent_floor=accent_floor,
            text_only=text_only,
            # Cap one image's screen time. The reference's own longest shot is 16.37s;
            # a cross-beat hold shipped 27.8s on Solo Leveling.
            max_shot=float(get_nested(config, "video", "max_shot_seconds", default=10.0)),
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


# Binding and timing bands. Sources in reports/render_audit_2026-08-28.md; the brief's
# own proposals except where measurement contradicted them.
# Re-derived 2026-08-28 from the fixed matcher, replacing the brief's unsourced 70.
# Measured after window-scoping and the distinct-sentence filter objective: FP 63.0%,
# SL 57.1%. The ceiling is not 100 and never was — the matcher is INSTRUCTED to claim
# nothing for narrator commentary ("a sentence of pure narrator commentary depicts
# nothing"), and across both titles the model volunteers a claim for only 74.6-78.7%
# of sentences. So 70 demanded matching nearly every claimable sentence. 55 sits below
# the worse title with margin; the residual gap to the ceiling is the monotonic filter
# refusing claims that contradict reading order, which is it working. Raising this
# number requires a better matcher, not a lower floor.
_MATCH_MIN_PCT = 55.0
_UTILISATION_MIN_PCT = 60.0    # brief; measured 58.8 / 71.5
_HOLD_MAX_SENTENCES = 3        # brief
_TIMING_MIN_PCT = 95.0         # replaces the brief's "80% measured": 100% today, so this
                               # guards a REGRESSION to word-proration, not a deficit


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
    # Measured on MERGED runs, not planned entries. Consecutive entries on one panel are
    # one shot to the viewer, so counting entries reports half a hold: Frozen Player's
    # 18.6s hold on p0024_02 was two entries of 7.4s and 11.2s, and neither tripped a
    # 12s limit.
    from manhwa2vid.measure.shots import merged_runs

    runs_all = merged_runs(timeline.entries)
    over = [
        f"beat {run['beat_ids'][0]}: {run['seconds']:.1f}s on {run['panel_id']} "
        f"({words_by_beat.get(run['beat_ids'][0], 0)}w / "
        f"{panels_by_beat.get(run['beat_ids'][0], 1)} panel(s))"
        for run in runs_all
        if run["seconds"] > limit
    ]
    report.add(
        "dwell-over-limit",
        "warn" if over else True,
        "; ".join(over[:4]) + " — narration too long for its panel count" if over else "",
        over=over,
    )

    # Two entries in a row on the same panel are ONE shot to the viewer, whatever the
    # plan says. Holding across a beat boundary is a legitimate fallback, so this warns
    # rather than fails — but it must be visible, because the dwell limit above counts
    # planned entries and cannot see that it is really reporting half a hold.
    runs = [
        f"{run['panel_id']} across beats {run['beat_ids'][0]}->{run['beat_ids'][-1]} "
        f"({run['seconds']:.1f}s seen as one shot)"
        for run in runs_all
        if run["entries"] > 1
    ]
    report.add(
        "no-invisible-cuts",
        "warn" if runs else True,
        "; ".join(runs[:4]) + " — consecutive entries on one panel" if runs else "",
        runs=runs,
    )

    # The last thing on screen. Frozen Player ch1-2 closed on a "WHAT?!" starburst held
    # 18.6s: the 2026-08-26 audit filed it as defect A2, the end card hid it rather than
    # fixing it, and removing the card brought it straight back. A recap must not end on
    # a wall of lettering while the narrator is asking for the subscribe.
    closing = ""
    if timeline.entries:
        import cv2

        from manhwa2vid.panels.regions import is_text_dominant_panel

        last = timeline.entries[-1]
        img = cv2.imread(str(paths["root"] / last.panel_path))
        if img is not None and is_text_dominant_panel(img):
            closing = f"the video ends on {last.panel_id}, which is lettering not art"
    report.add("closing-shot-is-art", not closing, closing)

    # --- panel binding -----------------------------------------------------------------
    #
    # These read the PLANNED artifacts, so they can catch a bad edit before a render is
    # paid for. Thresholds from docs/qa-hardening-brief.md, measured today at
    # match 61.1% (FP) / 48.7% (SL) and utilisation 58.8% / 71.5%.
    from manhwa2vid.measure.binding import hold_runs, match_rate, panel_utilisation

    shotlist_path = paths["script_shotlist_json"]
    if shotlist_path.exists():
        import json as _json

        shotlist = _json.loads(shotlist_path.read_text(encoding="utf-8"))
        match = match_rate(shotlist)
        report.add(
            "match-rate",
            True if match["match_rate_pct"] >= _MATCH_MIN_PCT else "warn",
            f"{match['match_rate_pct']}% of sentences are bound to a panel of their own "
            f"(floor {_MATCH_MIN_PCT}%) — the rest inherit the picture rather than choose it",
            **match,
        )

    story_ids = [p.id for p in panels]
    util = panel_utilisation(story_ids, timeline.entries)
    unused = util.pop("unused", [])
    report.add(
        "panel-utilisation",
        True if util["utilisation_pct"] >= _UTILISATION_MIN_PCT else "warn",
        f"{util['utilisation_pct']}% of story panels reach the screen "
        f"(floor {_UTILISATION_MIN_PCT}%); {len(unused)} never shown",
        **util,
    )

    # How much NARRATION one image has to carry. Needs TimelineEntry.sentence_numbers;
    # without it the honest answer is entries-per-run, which understates the hold, so
    # hold_runs reports which basis it used and returns no verdict on the weaker one.
    holds = hold_runs(timeline.entries, max_sentences=_HOLD_MAX_SENTENCES)
    if holds["basis"] == "sentences":
        worst = holds["over_limit"]
        report.add(
            "hold-run",
            "warn" if worst else True,
            (f"{len(worst)} panel(s) hold more than {_HOLD_MAX_SENTENCES} consecutive "
             f"sentences: " + "; ".join(
                 f"{w['panel_id']} ({w['sentences']} sentences, {w['seconds']}s)"
                 for w in worst[:4]
             )) if worst else "",
            longest_hold_sentences=holds["longest_hold"], over_limit=worst,
        )
    else:
        report.add(
            "hold-run", True,
            "not measured: this timeline predates TimelineEntry.sentence_numbers",
            basis=holds["basis"],
        )

    report.add(
        "panel-budget",
        "warn" if timeline.dropped_panels else True,
        f"{timeline.dropped_panels} panel(s) dropped by the per-beat budget"
        if timeline.dropped_panels else "",
        dropped=timeline.dropped_panels,
    )

    # Sentence durations: MEASURED, or estimated? Kokoro synthesizes one clip per
    # sentence, so its sidecar seconds are measured and sentence identity with the shot
    # list holds by construction. Other providers return one opaque clip per beat and
    # `timeline._subdivide_segments` word-prorates it — a plausible-looking estimate that
    # silently decouples every cut from the speech. So this checks IDENTITY (per-beat
    # sentence counts line up), not merely that a sidecar exists.
    if shotlist_path.exists():
        from manhwa2vid.measure.binding import timing_measured
        from manhwa2vid.video.timeline import load_beat_segments

        segments: dict[int, list[dict]] = {}
        for entry in timeline.entries:
            beat = int(entry.beat_id or 0)
            if beat not in segments:
                segments[beat] = load_beat_segments(paths["audio"], beat)
        timing = timing_measured(shotlist, segments)
        report.add(
            "timing-measured",
            timing["measured_pct"] >= _TIMING_MIN_PCT,
            f"{timing['measured_pct']}% of sentences have a measured duration "
            f"(floor {_TIMING_MIN_PCT}%); beats falling back to word-proration: "
            f"{timing['mismatched_beats'][:8]}",
            **timing,
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
    target_wpm = float(get_nested(config, "script", "target_wpm", default=220))
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
