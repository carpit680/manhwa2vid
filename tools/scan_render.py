"""Post-render verification the gates cannot do: scan the actual video.

Born 2026-08-30 from the watching round. Two checks:

- BANDS: uniform white/black strips at the frame edges — the on-screen symptom of
  interior page background (under-split panels), bad crops, or fill regressions.
- ORDER: reading-order inversions and non-adjacent repeats measured from timeline.json,
  the artifact the render was built from.

Usage:
    python tools/scan_render.py projects/<slug> [video_path]

Video defaults to the newest output/preview_*.mp4. Exit code 1 if any check fires, so
this can guard a release step.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np


def scan_bands(video: Path, step_s: int = 5) -> list[tuple[int, int, int, int, int]]:
    dur = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video)]))
    hits = []
    for t in range(2, int(dur) - 2, step_s):
        raw = subprocess.check_output(
            ["ffmpeg", "-loglevel", "error", "-ss", str(t), "-i", str(video),
             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"])
        side = int((len(raw) // (540 * 960)) ** 0.5) or 1
        a = np.frombuffer(raw, dtype=np.uint8)
        if a.size != 540 * 960:
            continue
        a = a.reshape(540, 960).astype(np.float32)

        def band(rows: np.ndarray) -> int:
            u = (rows.std(axis=1) < 5) & ((rows.mean(axis=1) > 235) | (rows.mean(axis=1) < 18))
            return int(u.sum())

        top, bot = band(a[:120]), band(a[-120:])
        lef = int(((a[:, :40].std(axis=0) < 5)
                   & ((a[:, :40].mean(axis=0) > 235) | (a[:, :40].mean(axis=0) < 18))).sum())
        rig = int(((a[:, -40:].std(axis=0) < 5)
                   & ((a[:, -40:].mean(axis=0) > 235) | (a[:, -40:].mean(axis=0) < 18))).sum())
        if top > 25 or bot > 25 or lef > 3 or rig > 3:
            hits.append((t, top, bot, lef, rig))
    return hits


def scan_order(project: Path) -> tuple[list[str], dict[str, int]]:
    from manhwa2vid.measure.shots import merged_runs

    tl = json.loads((project / "timeline.json").read_text())["entries"]
    order = {p["id"]: i for i, p in
             enumerate(json.loads((project / "panels.story.json").read_text()))}
    from manhwa2vid.script.match import SCENE_RADIUS

    # Same rule as the reading-order gate: a backward step of up to SCENE_RADIUS from
    # the HIGH-WATER position is same-scene editing (close-up, then the establishing
    # shot). Only longer rewinds are inversions. Keeping this tool on the old strict
    # rule made it report 22 "inversions" on a render the gate passed.
    runs = merged_runs(tl)
    inversions, clock, high = [], 0.0, -1
    for prev, run in zip(runs, runs[1:]):
        clock += prev["seconds"]
        a, b = order.get(prev["panel_id"]), order.get(run["panel_id"])
        if a is not None:
            high = max(high, a)
        if a is not None and b is not None and b < high - SCENE_RADIUS and b < a:
            inversions.append(f"{prev['panel_id']}(#{a}) -> {run['panel_id']}(#{b}) at {clock:.1f}s")
    repeats = {k: v for k, v in Counter(r["panel_id"] for r in runs).items() if v > 1}
    return inversions, repeats


def main() -> int:
    project = Path(sys.argv[1])
    if len(sys.argv) > 2:
        video = Path(sys.argv[2])
    else:
        video = max((project / "output").glob("preview_*.mp4"), key=lambda p: p.stat().st_mtime)
    print(f"video: {video.name}")

    inversions, repeats = scan_order(project)
    print(f"order: {len(inversions)} inversion(s), {len(repeats)} repeated panel(s)")
    for line in inversions[:10]:
        print(f"  {line}")
    for pid, n in list(repeats.items())[:10]:
        print(f"  {pid} x{n}")

    hits = scan_bands(video)
    print(f"bands: {len(hits)} frame(s) with edge banding")
    for t, top, bot, lef, rig in hits[:12]:
        print(f"  t={t:>4}s top={top} bot={bot} L={lef} R={rig}")

    return 1 if (inversions or repeats or hits) else 0


if __name__ == "__main__":
    raise SystemExit(main())
