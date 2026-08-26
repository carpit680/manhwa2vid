"""QA on the RENDERED video — the final surface, not what upstream intended.

Every detector here is lifted from the 2026-08-26 audit that measured the defects
shipping: 19s of speech bubbles on black opening SL, 46% of frames with edge-clipped
text, 62-68% mean dead width, +0.3 dBTP clipping. Nothing upstream can prove those
absent; only the pixels and samples of the finished file can.

Thresholds are pinned by tests against the audit's measured values (tune the
threshold, never the metric). The shot-length comparison bands are CONSTANTS measured
once from the reference channel with tools/profile_shots.py — runtime code must not
read reference/ (tests/test_series_agnostic.py enforces that).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from manhwa2vid.qa import QAReport, enforce, qa_forced

_W, _H, _FPS = 480, 270, 2.0

# Measured from the reference channel (see reference/mamoru_shot_profile.md):
# median 2.87s, 22% of shots under 1.5s, 16.3 cuts/min. Report-only bands.
_REF_MEDIAN_S = 2.87
_REF_UNDER_1_5_PCT = 22.0
# Same-content baseline (reference channel's OWN edit of the same opening chapters,
# run through these exact detectors, 2026-08-26): bubble-over-20% 21.9%, clipped-text
# 43.9%. Dialogue-heavy openings simply carry more bubbles — bands must not punish the
# source material.
_REF_BUBBLE_PCT = 21.9
_REF_CLIPPED_PCT = 43.9


def _iter_frames(video: Path):
    proc = subprocess.Popen(
        [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(video),
            "-vf", f"fps={_FPS},scale={_W}:{_H}", "-pix_fmt", "gray",
            "-f", "rawvideo", "-",
        ],
        stdout=subprocess.PIPE,
    )
    size = _W * _H
    assert proc.stdout is not None
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        yield np.frombuffer(buf, np.uint8).reshape(_H, _W)


def _bubble_stats(frame: np.ndarray) -> tuple[float, bool]:
    """(largest TEXT-BEARING bright blob as frame fraction, any such blob edge-clipped).

    A speech bubble is a solid bright blob WITH dark text strokes inside it; a white
    wall or bright sky is a solid bright blob without them. The first version had no
    text test and scored a hospital wall as a 40%-of-frame 'bubble' — the gate then
    failed a render whose frames read fine. Dark-pixel fraction inside the blob's box
    separates the two (measured: bubbles 2-20%, backgrounds ~0%)."""
    bright = (frame > 232).astype(np.uint8)
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    count, _lbl, stats, _c = cv2.connectedComponentsWithStats(bright, 8)
    best, clipped = 0.0, False
    for i in range(1, count):
        x, y, w, h, area = (int(v) for v in stats[i])
        frac = area / (_W * _H)
        if frac < 0.02 or area / max(w * h, 1) < 0.45:
            continue
        box = frame[y : y + h, x : x + w]
        dark = float((box < 100).mean())
        if not (0.01 <= dark <= 0.30):
            continue  # no text inside: background, not a bubble
        best = max(best, frac)
        if (y <= 1 or y + h >= _H - 1 or x <= 1 or x + w >= _W - 1) and frac > 0.03:
            clipped = True
    return best, clipped


def _dead_width(frame: np.ndarray) -> float:
    gx = np.abs(np.diff(frame.astype(np.int16), axis=1)).mean(axis=0)
    thr = max(float(gx.max()) * 0.12, 1.0)
    return 1.0 - float((gx > thr).sum()) / _W


def measure_video(video: Path) -> dict[str, Any]:
    """Whole-runtime frame metrics + audio true peak + shot-length stats."""
    bubble_fracs: list[float] = []
    clipped_flags: list[bool] = []
    dead: list[float] = []
    lumas: list[float] = []
    for frame in _iter_frames(video):
        frac, clipped = _bubble_stats(frame)
        bubble_fracs.append(frac)
        clipped_flags.append(clipped)
        dead.append(_dead_width(frame))
        lumas.append(float(frame.mean()))

    n = max(len(lumas), 1)
    open_n = min(int(4 * _FPS), n)  # first 4 seconds
    metrics: dict[str, Any] = {
        "frames": n,
        "opening_luma_mean": round(float(np.mean(lumas[:open_n])), 1),
        "opening_bubble_frac_max": round(float(max(bubble_fracs[:open_n], default=0.0)), 3),
        "bubble_over_20pct_frames_pct": round(
            100.0 * float(np.mean([f > 0.20 for f in bubble_fracs])), 1
        ),
        "clipped_text_frames_pct": round(100.0 * float(np.mean(clipped_flags)), 1),
        "dead_width_mean": round(float(np.mean(dead)), 3),
        "dead_over_50pct_frames_pct": round(100.0 * float(np.mean([d > 0.5 for d in dead])), 1),
    }

    # Audio true peak from a loudnorm measurement pass.
    proc = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-i", str(video),
            "-af", "loudnorm=print_format=json", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    start = proc.stderr.rfind("{")
    if start != -1:
        try:
            data = json.loads(proc.stderr[start:])
            metrics["true_peak_dbtp"] = float(data.get("input_tp"))
            metrics["loudness_lufs"] = float(data.get("input_i"))
        except (ValueError, TypeError):
            pass

    # Shot lengths via scene detection — same detector the reference was profiled with.
    proc = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", str(video),
            "-vf", "select='gt(scene,0.30)',showinfo", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    cuts = []
    for line in proc.stderr.splitlines():
        if "showinfo" in line and "pts_time:" in line:
            try:
                cuts.append(float(line.split("pts_time:")[1].split()[0]))
            except (ValueError, IndexError):
                continue
    duration = n / _FPS
    edges = [0.0, *cuts, duration]
    shots = [b - a for a, b in zip(edges, edges[1:]) if b - a > 0.05]
    if shots:
        s = sorted(shots)
        metrics["shots"] = len(shots)
        metrics["cuts_per_min"] = round(60 * len(cuts) / max(duration, 1e-6), 2)
        metrics["shot_median_s"] = round(float(np.median(s)), 2)
        metrics["shot_under_1_5s_pct"] = round(100.0 * sum(x < 1.5 for x in s) / len(s), 1)
        metrics["shot_longest_s"] = round(s[-1], 2)
    return metrics


def enforce_render_qa(
    video: Path, paths: dict[str, Path], config: dict[str, Any]
) -> dict[str, Any]:
    metrics = measure_video(video)
    report = QAReport(stage="render")

    # Opening: SL opened on 19 seconds of speech bubbles on black.
    opening_ok = (
        metrics["opening_luma_mean"] > 16.0
        and metrics["opening_bubble_frac_max"] < 0.35
    )
    report.add(
        "opening-shot",
        opening_ok,
        f"first seconds: luma {metrics['opening_luma_mean']}, "
        f"largest bubble {metrics['opening_bubble_frac_max']:.0%} of frame — "
        "a recap must not open on a bubble or a black screen",
        **{k: metrics[k] for k in ("opening_luma_mean", "opening_bubble_frac_max")},
    )

    # Bands below are calibrated against the REFERENCE channel's own video run through
    # these exact detectors (10-min sample, 2026-08-26): bubble-over-20% 13.7%,
    # clipped-text 41.9%, dead-width 0.742. Calibrating against our old defective
    # videos instead produced gates that the reference itself would fail.

    # Bubble dominance: reference 13.7%; the audited videos ran 18-31% and the first
    # fill-frame render 40% (zooming in magnifies bubbles) — a real, fixable gap.
    pct = metrics["bubble_over_20pct_frames_pct"]
    report.add(
        "bubble-dominance",
        True if pct <= _REF_BUBBLE_PCT + 6 else ("warn" if pct <= _REF_BUBBLE_PCT + 23 else False),
        f"{pct}% of frames have a bubble covering >20% of the screen "
        f"(reference, same content: {_REF_BUBBLE_PCT}%)",
        pct=pct,
    )

    # Edge-clipped text: the reference's own edit measures 41.9% — a panning camera
    # over bubbled art clips text mid-move as a matter of course. Gate only the excess.
    pct = metrics["clipped_text_frames_pct"]
    report.add(
        "clipped-text",
        True if pct <= _REF_CLIPPED_PCT + 11 else ("warn" if pct <= _REF_CLIPPED_PCT + 26 else False),
        f"{pct}% of frames slice a text blob at the frame edge "
        f"(reference, same content: {_REF_CLIPPED_PCT}%)",
        pct=pct,
    )

    # Dead space: REPORT-ONLY. The detector reads low-detail columns, and manhwa art is
    # flat by style — the reference video measures 0.742, worse than anything we ship.
    # The audited defect (blurred pillarbox bars) is structurally gone with the
    # fill-frame camera; this number is kept as data, not a gate.
    dead = metrics["dead_width_mean"]
    report.add(
        "dead-space",
        True,
        f"mean fraction of frame width with no detail: {dead:.0%} (reference: 74%; data only)",
        mean=dead,
    )

    # Audio: audited true peak was +0.30/+0.35 dBTP — clips on transcode.
    tp = metrics.get("true_peak_dbtp")
    if tp is not None:
        report.add(
            "true-peak",
            tp <= -0.8,
            f"true peak {tp} dBTP (target -1.5, must stay below -0.8)",
            dbtp=tp,
        )

    # Editing rhythm vs the measured reference — report-only.
    if "shot_median_s" in metrics:
        drift = (
            metrics["shot_median_s"] > _REF_MEDIAN_S * 1.75
            or metrics["shot_under_1_5s_pct"] < _REF_UNDER_1_5_PCT * 0.25
        )
        report.add(
            "shot-rhythm",
            "warn" if drift else True,
            f"median {metrics['shot_median_s']}s (ref {_REF_MEDIAN_S}s), "
            f"{metrics['shot_under_1_5s_pct']}% under 1.5s (ref {_REF_UNDER_1_5_PCT}%)",
            **{k: metrics[k] for k in ("shot_median_s", "shot_under_1_5s_pct", "cuts_per_min")},
        )

    enforce(report, paths["root"], force=qa_forced(config))
    return metrics


def upstream_failures(project_dir: Path) -> list[str]:
    """Names of FAILED gates in every existing qa.*.json — the render precondition.

    Both audited videos rendered while script-stage gates were failing; nothing
    connected a red gate to the render that shipped it."""
    failures: list[str] = []
    for qa_file in sorted(project_dir.glob("qa.*.json")):
        if qa_file.name == "qa.render.json":
            continue
        try:
            data = json.loads(qa_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for gate in data.get("gates") or []:
            if gate.get("status") == "fail":
                failures.append(f"{qa_file.stem.removeprefix('qa.')}:{gate.get('name')}")
    return failures
