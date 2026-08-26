"""Measure a recap video's real shot behaviour: cut times, shot lengths, motion.

The style profile measured Mamoru's WORDS (237 WPM, 3.2s of airtime per sentence); this
measures his PICTURE. YouTube auto-captions carry no cut information (rolling two-line
windows overlapping ~50%), so the only source of his editing rhythm is the video itself.

A recap video is a slideshow with camera moves: hard cuts between panels separated by
stretches of pan/zoom. ffmpeg's scene detector scores inter-frame difference, so the
threshold separates "new panel" from "camera drift". Rather than trusting one number,
this samples frames around candidate cuts at several thresholds so the choice can be
eyeballed once and recorded.

Usage:
    PYTHONPATH= .venv/bin/python tools/profile_shots.py reference/frozen_player/mamoru_fp_video.mp4 \
        --start 300 --duration 1200 --threshold 0.30 --out reference/mamoru_shot_profile.md
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import subprocess
from pathlib import Path


def detect_cuts(video: Path, start: float, duration: float, threshold: float) -> list[float]:
    """Timestamps (relative to --start) where the scene score exceeds threshold."""
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-ss", str(start), "-t", str(duration), "-i", str(video),
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
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
    edges = [0.0, *cuts, duration]
    return [b - a for a, b in zip(edges, edges[1:]) if b - a > 0.05]


def describe(lengths: list[float]) -> dict:
    lengths = sorted(lengths)
    n = len(lengths)
    if not n:
        return {}
    q = lambda p: lengths[min(n - 1, int(p * n))]
    return {
        "shots": n,
        "median_s": round(st.median(lengths), 2),
        "mean_s": round(st.mean(lengths), 2),
        "p10_s": round(q(0.10), 2),
        "p90_s": round(q(0.90), 2),
        "under_1_5s_pct": round(100 * sum(1 for x in lengths if x < 1.5) / n, 1),
        "under_1s_pct": round(100 * sum(1 for x in lengths if x < 1.0) / n, 1),
        "over_6s_pct": round(100 * sum(1 for x in lengths if x > 6.0) / n, 1),
        "longest_s": round(lengths[-1], 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--start", type=float, default=300.0)
    ap.add_argument("--duration", type=float, default=1200.0)
    ap.add_argument("--threshold", type=float, default=None,
                    help="single threshold; omit to sweep 0.20/0.30/0.40")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    thresholds = [args.threshold] if args.threshold else [0.20, 0.30, 0.40]
    results = {}
    for th in thresholds:
        cuts = detect_cuts(args.video, args.start, args.duration, th)
        stats = describe(shot_lengths(cuts, args.duration))
        stats["cuts_per_min"] = round(60 * len(cuts) / args.duration, 2)
        results[th] = stats
        print(f"threshold {th}: {json.dumps(stats)}")

    if args.out:
        lines = [
            "# Mamoru Manhwa — measured shot behaviour",
            "",
            f"Source: `{args.video.name}`, window {args.start:.0f}s + {args.duration:.0f}s.",
            "Scene-cut detection via ffmpeg `select='gt(scene,T)'`; a recap video is a",
            "slideshow with pan/zoom, so T separates panel changes from camera drift.",
            "",
            "| threshold | shots | cuts/min | median | mean | p10 | p90 | <1.5s | <1s | >6s | longest |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for th, s in results.items():
            lines.append(
                f"| {th} | {s.get('shots')} | {s.get('cuts_per_min')} | {s.get('median_s')}s "
                f"| {s.get('mean_s')}s | {s.get('p10_s')}s | {s.get('p90_s')}s "
                f"| {s.get('under_1_5s_pct')}% | {s.get('under_1s_pct')}% "
                f"| {s.get('over_6s_pct')}% | {s.get('longest_s')}s |"
            )
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"-> {args.out}")


if __name__ == "__main__":
    main()
