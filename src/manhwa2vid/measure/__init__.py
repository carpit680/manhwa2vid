"""Measurement primitives shared by the QA gates and `tools/measure_render.py`.

One detector, one implementation. The 2026-08-27 work established that comparing numbers
produced by different detectors is worthless — it inverted a verdict on a real render once
(the opening-shot gate read pale hair as a speech bubble and failed a frame that had
improved). Everything that measures a rendered video now lives here, so the gate that
blocks a render and the tool that profiles the reference channel cannot drift apart.

Nothing in this package may read `reference/` — callers pass paths in
(`tests/test_series_agnostic.py` enforces that on all of `src/`). Reference-derived
constants are promoted into gate modules as documented literals with their provenance.
"""

from manhwa2vid.measure.frames import (
    FRAME_FPS,
    FRAME_H,
    FRAME_W,
    bubble_stats,
    dead_width,
    iter_frames,
    lettering_area,
)
from manhwa2vid.measure.shots import detect_cuts, merged_runs, shot_stats

__all__ = [
    "FRAME_FPS",
    "FRAME_H",
    "FRAME_W",
    "bubble_stats",
    "dead_width",
    "detect_cuts",
    "iter_frames",
    "lettering_area",
    "merged_runs",
    "shot_stats",
]
