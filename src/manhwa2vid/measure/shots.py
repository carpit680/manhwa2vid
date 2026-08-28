"""Shot-length measurement: what the viewer sees cut, and what the planner intended.

Two sources, and the difference between them is a defect class in its own right:

* `detect_cuts` reads the FINISHED VIDEO with ffmpeg scene detection — the same detector
  `reference/mamoru_shot_profile.md` was built with, so its numbers are comparable to the
  reference channel's.
* `merged_runs` reads the PLANNED timeline, fusing consecutive entries that show the same
  panel. Those are cuts the planner scheduled and the viewer cannot see; counting entries
  instead of runs turned 106 planned shots into 100 seen ones on Frozen Player and made a
  16.7s longest shot report when the screen actually held one image for 18.6s. Every
  rhythm gate that reads the timeline must read runs, which is why there is exactly one
  implementation of this.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import numpy as np

SCENE_THRESHOLD = 0.30


def detect_cuts(
    video: Path,
    *,
    threshold: float = SCENE_THRESHOLD,
    start: float | None = None,
    duration: float | None = None,
    scale_width: int | None = None,
) -> list[float]:
    """Timestamps of scene cuts, in seconds from the start of the decoded window."""
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-nostats"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if duration is not None:
        cmd += ["-t", str(duration)]
    vf = f"select='gt(scene,{threshold})',showinfo"
    if scale_width is not None:
        vf = f"scale={scale_width}:-2,{vf}"
    cmd += ["-i", str(video), "-vf", vf, "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    cuts: list[float] = []
    for line in proc.stderr.splitlines():
        if "showinfo" in line and "pts_time:" in line:
            try:
                cuts.append(float(line.split("pts_time:")[1].split()[0]))
            except (ValueError, IndexError):
                continue
    return cuts


def shot_lengths(cuts: list[float], duration: float) -> list[float]:
    """Cut timestamps -> shot durations, dropping sub-frame slivers."""
    edges = [0.0, *cuts, duration]
    return [b - a for a, b in zip(edges, edges[1:]) if b - a > 0.05]


def shot_stats(lengths: list[float], duration: float) -> dict[str, Any]:
    """Rhythm summary. `longtail_share` is the share of RUNTIME, not of shot count."""
    if not lengths:
        return {}
    s = sorted(lengths)
    total = sum(s)
    return {
        "shots": len(s),
        "cuts_per_min": round(60 * (len(s) - 1) / max(duration, 1e-6), 2),
        "shot_median_s": round(float(np.median(s)), 2),
        "shot_mean_s": round(float(np.mean(s)), 2),
        "shot_p10_s": round(float(np.percentile(s, 10)), 2),
        "shot_p90_s": round(float(np.percentile(s, 90)), 2),
        "shot_under_1_5s_pct": round(100.0 * sum(x < 1.5 for x in s) / len(s), 1),
        "shot_under_1s_pct": round(100.0 * sum(x < 1.0 for x in s) / len(s), 1),
        "shot_longest_s": round(s[-1], 2),
        "shot_over_8s_runtime_pct": round(
            100.0 * sum(x for x in s if x > 8.0) / max(total, 1e-6), 1
        ),
        "shot_over_12s_runtime_pct": round(
            100.0 * sum(x for x in s if x > 12.0) / max(total, 1e-6), 1
        ),
    }


def merged_runs(entries: list[Any]) -> list[dict[str, Any]]:
    """Fuse consecutive timeline entries that show the same panel into one seen shot.

    Accepts timeline entries as objects (`TimelineEntry`) or plain dicts, because the
    gates hold models and the measurement tool holds parsed JSON.
    """
    def get(e: Any, key: str) -> Any:
        return e.get(key) if isinstance(e, dict) else getattr(e, key)

    runs: list[dict[str, Any]] = []
    i = 0
    while i < len(entries):
        j = i
        while j + 1 < len(entries) and get(entries[j + 1], "panel_id") == get(entries[i], "panel_id"):
            j += 1
        members = entries[i : j + 1]
        runs.append(
            {
                "panel_id": get(entries[i], "panel_id"),
                "seconds": float(sum(float(get(e, "duration")) for e in members)),
                "entries": len(members),
                "beat_ids": [get(e, "beat_id") for e in members],
                "index": i,
            }
        )
        i = j + 1
    return runs
