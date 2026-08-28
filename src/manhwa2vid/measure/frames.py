"""Per-frame measurements on a rendered video.

Two detector families live here and they are NOT interchangeable:

* `lettering_area` / `lettering_boxes` — the VALIDATED geometric detector from
  `panels.regions`. Zero false positives across all 607 panels of both titles. This is
  the one that decides things.
* `bubble_stats` / `dead_width` — brightness-and-gradient proxies kept because their
  numbers appear in every historical report. They are recorded as DATA and must not gate:
  `bubble_stats` finds "large pale region", not "bubble" (it scored hospital bedding at
  76% of frame and a real speech bubble at 0.00), and `dead_width` reads low-detail
  columns, which manhwa art is full of by style.

Frame-level lettering is measured as AREA — the share of the SCREEN covered by lettering.
The panel-level `text_content_ratio` (lettering as a share of non-background CONTENT) is
deliberately not reused here: on a rendered frame the blurred pillarbox counts as content
and drags the ratio down, so a frame that is visibly half speech bubble reads 0.40.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

FRAME_W, FRAME_H, FRAME_FPS = 480, 270, 2.0


def iter_frames(
    video: Path,
    *,
    fps: float = FRAME_FPS,
    width: int = FRAME_W,
    height: int = FRAME_H,
    start: float | None = None,
    duration: float | None = None,
) -> Iterator[np.ndarray]:
    """Decode `video` to grayscale frames at `fps`, optionally only a window of it.

    `start`/`duration` seek before the input so profiling a 5-hour reference costs the
    window, not the file.
    """
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd += [
        "-i", str(video),
        "-vf", f"fps={fps},scale={width}:{height}",
        "-pix_fmt", "gray", "-f", "rawvideo", "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    size = width * height
    assert proc.stdout is not None
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(height, width)
    finally:
        proc.stdout.close()
        proc.wait()


def bubble_stats(frame: np.ndarray) -> tuple[float, bool]:
    """(largest bright blob as frame fraction, any such blob edge-clipped) — DATA ONLY.

    Kept so historical numbers stay comparable. Audited 2026-08-27: of the frames this
    flags, 64% carry a "bubble" over 40% of the frame — pale walls and bedding — while a
    frame holding a real "??" bubble scores 0.00. Use `lettering_area` to decide anything.
    """
    h, w = frame.shape[:2]
    bright = (frame > 232).astype(np.uint8)
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    count, _lbl, stats, _c = cv2.connectedComponentsWithStats(bright, 8)
    best, clipped = 0.0, False
    for i in range(1, count):
        x, y, bw, bh, area = (int(v) for v in stats[i])
        frac = area / (w * h)
        if frac < 0.02 or area / max(bw * bh, 1) < 0.45:
            continue
        box = frame[y : y + bh, x : x + bw]
        dark = float((box < 100).mean())
        if not (0.01 <= dark <= 0.30):
            continue  # no text inside: background, not a bubble
        best = max(best, frac)
        if (y <= 1 or y + bh >= h - 1 or x <= 1 or x + bw >= w - 1) and frac > 0.03:
            clipped = True
    return best, clipped


def dead_width(frame: np.ndarray) -> float:
    """Fraction of frame width carrying no horizontal detail — DATA ONLY.

    The reference channel's own edit scores worse on this than anything we ship.
    """
    gx = np.abs(np.diff(frame.astype(np.int16), axis=1)).mean(axis=0)
    thr = max(float(gx.max()) * 0.12, 1.0)
    return 1.0 - float((gx > thr).sum()) / frame.shape[1]


def lettering_masks(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(lettering mask, non-background mask) for one frame, at frame resolution."""
    from manhwa2vid.panels.regions import _text_and_content_masks, _text_norm

    text, content, _contained = _text_and_content_masks(_text_norm(frame))
    return text, content


def lettering_area(frame: np.ndarray) -> float:
    """Share of the SCREEN covered by lettering and the bubbles holding it."""
    text, _content = lettering_masks(frame)
    return float(text.mean())
