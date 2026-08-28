#!/usr/bin/env python3
"""Measure a rendered video — every QA metric, one JSON report, one detector.

    tools/measure_render.py VIDEO [--project DIR] [--window START DUR]... [--out FILE]

With `--project` it adds the metrics that need the planned artifacts (shot list,
timeline, TTS sidecars, script) alongside the ones read off the pixels and samples.
Without it, it is reference mode: point it at any channel's video and get numbers
directly comparable to ours, because both sides run this same code.

`--window START DUR` measures only part of the file, repeatable. That is how a 5-hour
reference gets profiled without decoding 5 hours: seek, measure, move on.

This tool may read `reference/`; `src/` may not (tests/test_series_agnostic.py enforces
it), which is why every measurement function takes its paths as arguments.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np  # noqa: E402

from manhwa2vid.measure.audio import measure_audio  # noqa: E402
from manhwa2vid.measure.frames import (  # noqa: E402
    FRAME_FPS,
    bubble_stats,
    dead_width,
    iter_frames,
    lettering_masks,
)
from manhwa2vid.measure.shots import detect_cuts, shot_lengths, shot_stats  # noqa: E402


def probe_duration(video: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def measure_frames(
    video: Path, *, fps: float = FRAME_FPS,
    start: float | None = None, duration: float | None = None,
) -> dict[str, Any]:
    """Per-frame composition metrics over one window (or the whole file)."""
    lettering: list[float] = []
    art: list[float] = []
    clipped_lettering: list[bool] = []
    bubbles: list[float] = []
    bubble_clipped: list[bool] = []
    dead: list[float] = []
    lumas: list[float] = []

    for frame in iter_frames(video, fps=fps, start=start, duration=duration):
        text, content = lettering_masks(frame)
        h, w = text.shape
        lettering.append(float(text.mean()))
        # "Art" is content that is not lettering: what the viewer is here to look at.
        art.append(float((content & ~text).mean()))
        edge = bool(
            text[:2, :].any() or text[-2:, :].any() or text[:, :2].any() or text[:, -2:].any()
        )
        clipped_lettering.append(edge)
        frac, clip = bubble_stats(frame)
        bubbles.append(frac)
        bubble_clipped.append(clip)
        dead.append(dead_width(frame))
        lumas.append(float(frame.mean()))

    n = max(len(lumas), 1)
    open_n = min(int(15 * fps), n)  # the first 15 seconds decide whether anyone stays
    per_second_art = [
        float(np.mean(art[i : i + int(fps)])) for i in range(0, open_n, max(int(fps), 1))
    ]
    return {
        "frames": n,
        "fps_sampled": fps,
        # Composition, VALIDATED detector. Lettering is a share of SCREEN, not of content:
        # on a rendered frame the blurred pillarbox counts as content and drags a
        # content-relative ratio down, so a frame that is visibly half bubble reads 0.40.
        "lettering_area_median": round(float(np.median(lettering)), 3),
        "lettering_area_p95": round(float(np.percentile(lettering, 95)), 3),
        "lettering_area_max": round(float(np.max(lettering)), 3),
        "lettering_over_30pct_frames_pct": round(100.0 * float(np.mean([x > 0.30 for x in lettering])), 1),
        "lettering_over_40pct_frames_pct": round(100.0 * float(np.mean([x > 0.40 for x in lettering])), 1),
        "clipped_lettering_frames_pct": round(100.0 * float(np.mean(clipped_lettering)), 1),
        # A frame that is lettering with (almost) no art beside it: the "bare bubble".
        "bare_bubble_frames_pct": round(
            100.0 * float(np.mean([t > 0.15 and a < 0.12 for t, a in zip(lettering, art)])), 1
        ),
        "art_area_median": round(float(np.median(art)), 3),
        # Opening block.
        "opening_luma_mean": round(float(np.mean(lumas[:open_n])), 1),
        "opening_lettering_max": round(float(np.max(lettering[:open_n])), 3),
        "opening_art_per_second": [round(x, 3) for x in per_second_art],
        "opening_art_min_second": round(min(per_second_art), 3) if per_second_art else 0.0,
        # Legacy proxies — DATA ONLY, kept so historical reports stay comparable.
        "bubble_over_20pct_frames_pct": round(100.0 * float(np.mean([b > 0.20 for b in bubbles])), 1),
        "clipped_text_frames_pct": round(100.0 * float(np.mean(bubble_clipped)), 1),
        "dead_width_mean": round(float(np.mean(dead)), 3),
    }


def measure_shots(
    video: Path, *, start: float | None = None, duration: float | None = None,
    window_seconds: float | None = None,
) -> dict[str, Any]:
    cuts = detect_cuts(video, start=start, duration=duration)
    span = window_seconds if window_seconds else probe_duration(video)
    return shot_stats(shot_lengths(cuts, span), span)


def measure_project(project: Path) -> dict[str, Any]:
    """Metrics that need the planned artifacts, not the pixels."""
    from manhwa2vid.measure.binding import (
        hold_runs, match_rate, panel_utilisation, timing_measured,
    )
    from manhwa2vid.measure.script_text import (
        dialogue_verb_density, noun_repetition, quoted_span_rate, sentence_length_stats,
    )
    from manhwa2vid.models import project_paths
    from manhwa2vid.panels.filter import load_story_panels
    from manhwa2vid.script.beats import load_script_beats
    from manhwa2vid.script.read import glossary_names
    from manhwa2vid.video.timeline import load_beat_segments

    paths = project_paths(project)
    out: dict[str, Any] = {}

    timeline = json.loads(paths["timeline_json"].read_text())
    entries = timeline["entries"]
    out["timeline_duration_s"] = timeline.get("total_duration")

    shotlist = json.loads(paths["script_shotlist_json"].read_text())
    out["match"] = match_rate(shotlist)
    out["utilisation"] = panel_utilisation([p.id for p in load_story_panels(paths)], entries)
    out["utilisation"].pop("unused", None)
    out["holds"] = hold_runs(entries)

    segments: dict[int, list[dict[str, Any]]] = {}
    for e in entries:
        beat = int(e["beat_id"])
        if beat not in segments:
            segments[beat] = load_beat_segments(paths["audio"], beat)
    out["timing"] = timing_measured(shotlist, segments)

    draft = load_script_beats(paths)
    text = "\n\n".join(b.narration for b in draft.beats)
    names = glossary_names(paths)
    out["script"] = {
        "verbs": dialogue_verb_density(text),
        "quoted": quoted_span_rate(text),
        "sentences": sentence_length_stats(text),
        "noun_repetition": noun_repetition(text, exempt=names),
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video", type=Path)
    ap.add_argument("--project", type=Path, default=None)
    ap.add_argument("--window", nargs=2, type=float, action="append", metavar=("START", "DUR"))
    ap.add_argument("--fps", type=float, default=FRAME_FPS)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--label", default=None)
    args = ap.parse_args()

    started = time.time()
    report: dict[str, Any] = {
        "video": str(args.video),
        "label": args.label or args.video.stem,
        "duration_s": round(probe_duration(args.video), 2),
        "detector": "geometric lettering (panels.regions) — brightness proxies are data only",
    }

    windows = args.window or [(None, None)]
    report["windows"] = []
    for start, dur in windows:
        w: dict[str, Any] = {"start_s": start, "duration_s": dur}
        w.update(measure_frames(args.video, fps=args.fps, start=start, duration=dur))
        w.update(measure_shots(args.video, start=start, duration=dur, window_seconds=dur))
        report["windows"].append(w)

    # Audio only makes sense over the whole file.
    if len(windows) == 1 and windows[0][0] is None:
        report["audio"] = measure_audio(args.video)

    if args.project:
        report["project"] = measure_project(args.project)

    report["measured_in_s"] = round(time.time() - started, 1)
    text = json.dumps(report, indent=1)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out} in {report['measured_in_s']}s")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
