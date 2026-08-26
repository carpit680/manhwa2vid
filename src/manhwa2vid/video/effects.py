"""Video effects helpers."""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from manhwa2vid.config import get_nested
from manhwa2vid.models import Panel


def cosine_ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return (1.0 - math.cos(math.pi * t)) / 2.0


def crop_to_content(panel: Image.Image, pad_frac: float = 0.04) -> Image.Image:
    """Crop away white margins so the frame is filled with art, not paper.

    Measured need: ~48 shown panels across the two real projects carry their content in
    under 60% of their area, and `letterbox_panel` fit the WHOLE png — margins included —
    so their art rendered at barely half the size the screen allowed. A 4% pad keeps
    the crop from feeling clinical.

    Known limit, recorded where the decision is made: this cannot tell art ink from
    speech-bubble ink (no bubble geometry exists — OCR boxes are empty on both real
    projects), so a bubble-heavy panel stays bubble-heavy. Bubble avoidance needs a
    white-blob detector or OCR-with-boxes; separate work.
    """
    gray = panel.convert("L")
    mask = gray.point(lambda v: 255 if v < 240 else 0)
    box = mask.getbbox()
    if box is None:
        return panel
    x0, y0, x1, y1 = box
    if (x1 - x0) * (y1 - y0) >= 0.95 * panel.width * panel.height:
        return panel  # nothing worth cropping
    pad_x = int(panel.width * pad_frac)
    pad_y = int(panel.height * pad_frac)
    return panel.crop(
        (
            max(0, x0 - pad_x),
            max(0, y0 - pad_y),
            min(panel.width, x1 + pad_x),
            min(panel.height, y1 + pad_y),
        )
    )


def letterbox_panel(panel_path: Path, width: int, height: int, blur_bg: bool = True) -> Image.Image:
    panel = crop_to_content(Image.open(panel_path).convert("RGB"))
    canvas = Image.new("RGB", (width, height), (0, 0, 0))

    if blur_bg:
        bg = panel.copy().resize((width, height), Image.Resampling.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=20))
        canvas.paste(bg, (0, 0))

    scale = min(width / panel.width, height / panel.height)
    new_w = int(panel.width * scale)
    new_h = int(panel.height * scale)
    resized = panel.resize((new_w, new_h), Image.Resampling.LANCZOS)
    x = (width - new_w) // 2
    y = (height - new_h) // 2
    canvas.paste(resized, (x, y))
    return canvas


def choose_camera_mode(panel: Panel, config: dict[str, Any]) -> str:
    hint = (panel.camera_hint or "auto").lower()
    if hint in ("scroll", "ken_burns"):
        return hint

    threshold = float(get_nested(config, "video", "strip_scroll_aspect", default=2.0))
    aspect = panel.aspect_ratio
    if aspect is None and panel.bbox.width:
        aspect = panel.bbox.height / panel.bbox.width
    if panel.split_method == "strip":
        return "scroll"
    if aspect is not None and aspect >= threshold:
        return "scroll"
    return "ken_burns"


def ken_burns_params(seed: str) -> tuple[float, float]:
    rng = random.Random(seed)
    zoom_start = 1.0 + rng.uniform(0.0, 0.02)
    zoom_end = zoom_start + rng.uniform(0.04, 0.10)
    return zoom_start, zoom_end


def render_vertical_scroll_frames(
    panel_path: Path,
    width: int,
    height: int,
    num_frames: int,
    config: dict[str, Any],
) -> list[Image.Image]:
    supersample = int(get_nested(config, "video", "motion_supersample", default=2))
    out_w = width * supersample
    out_h = height * supersample

    # Crop margins first so the scroll traverses ART, not the blank lead-in and
    # tail a webtoon strip carries; the camera previously spent readable seconds on
    # empty paper at both ends of every tall panel.
    panel = crop_to_content(Image.open(panel_path).convert("RGB"))
    scale = out_w / panel.width
    scaled_h = max(int(panel.height * scale), out_h)
    scaled = panel.resize((out_w, scaled_h), Image.Resampling.LANCZOS)

    max_y = max(0, scaled_h - out_h)

    # Cap scroll speed. Travel is otherwise panel_height/dwell, which on a tall strip with a
    # short beat reaches thousands of px/s — an unreadable vertical smear. When the full panel
    # cannot be traversed at a readable speed, show the top portion instead of racing through it.
    fps = int(get_nested(config, "video", "fps", default=30))
    max_px_per_sec = float(get_nested(config, "video", "max_scroll_px_per_sec", default=600.0))
    start_y = 0
    if max_px_per_sec > 0 and fps > 0:
        duration = num_frames / fps
        allowed_travel = int(max_px_per_sec * duration * supersample)
        if allowed_travel < max_y:
            # Cannot traverse the whole strip at a readable speed. Previously the camera
            # pinned to the TOP and the bottom of the strip simply never appeared —
            # arbitrary with respect to content. Center the reachable window instead.
            start_y = (max_y - allowed_travel) // 2
            max_y = allowed_travel

    frames: list[Image.Image] = []
    for i in range(num_frames):
        t = i / max(num_frames - 1, 1)
        y = start_y + int(max_y * cosine_ease(t))
        crop = scaled.crop((0, y, out_w, y + out_h))
        frames.append(crop.resize((width, height), Image.Resampling.LANCZOS))
    return frames


def render_ken_burns_frames(
    base: Image.Image,
    num_frames: int,
    zoom_start: float,
    zoom_end: float,
    config: dict[str, Any],
    *,
    width: int,
    height: int,
) -> list[Image.Image]:
    supersample = int(get_nested(config, "video", "motion_supersample", default=2))
    pan_amount = float(get_nested(config, "video", "ken_burns_pan_amount", default=0.02))

    out_w = width * supersample
    out_h = height * supersample
    base_ss = base.resize((out_w, out_h), Image.Resampling.LANCZOS)

    rng = random.Random(str(zoom_start) + str(zoom_end))
    pan_axis = rng.choice(["x", "y", "none"])
    direction = rng.choice([-1.0, 1.0])

    frames: list[Image.Image] = []
    for i in range(num_frames):
        t = i / max(num_frames - 1, 1)
        ease = cosine_ease(t)
        zoom = zoom_start + (zoom_end - zoom_start) * ease

        crop_w = out_w / zoom
        crop_h = out_h / zoom
        cx = out_w / 2.0
        cy = out_h / 2.0

        if pan_axis == "x" and pan_amount > 0:
            cx += direction * out_w * pan_amount * ease
        elif pan_axis == "y" and pan_amount > 0:
            cy += direction * out_h * pan_amount * ease

        left = int(round(cx - crop_w / 2.0))
        top = int(round(cy - crop_h / 2.0))
        right = int(round(left + crop_w))
        bottom = int(round(top + crop_h))

        left = max(0, min(out_w - 1, left))
        top = max(0, min(out_h - 1, top))
        right = max(left + 1, min(out_w, right))
        bottom = max(top + 1, min(out_h, bottom))

        cropped = base_ss.crop((left, top, right, bottom))
        frames.append(cropped.resize((width, height), Image.Resampling.LANCZOS))
    return frames


# --- fill-frame camera ---------------------------------------------------------------
#
# The camera lives INSIDE the panel: every shot is a 16:9 window over the art, chosen by
# salience, panned in reading order. Decision measured and taken with the user
# (2026-08-26 audit): fitting whole panels left 51-52% of runtime-weighted screen area
# as blurred bars — SL spends 89% of its runtime on panels taller than the frame.


def _bubble_boxes(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Solid near-white blobs — speech bubbles and captions.

    Same detector the audit used to count bubble-dominant frames: brightness > 232,
    closed, components that are big enough and mostly filled. Boxes are used two ways:
    to down-weight bubbles in salience (art outranks text) and to keep a resting frame
    from slicing a bubble at the frame edge (46% of audited frames had clipped text).
    """
    bright = (gray > 232).astype(np.uint8)
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    count, _lbl, stats, _c = cv2.connectedComponentsWithStats(bright, 8)
    h, w = gray.shape[:2]
    boxes = []
    for i in range(1, count):
        x, y, bw, bh, area = (int(v) for v in stats[i])
        if area < 0.01 * h * w:
            continue
        if area / max(bw * bh, 1) < 0.45:
            continue
        boxes.append((x, y, bw, bh))
    return boxes


def _salience(gray: np.ndarray, bubbles: list[tuple[int, int, int, int]], *, bubble_weight: float = 0.15) -> np.ndarray:
    """Where the art is: local gradient energy, bubbles down-weighted.

    Flat background scores zero by construction; a bubble is full of high-contrast text
    edges, which is exactly why raw gradient energy loved them — hence the explicit
    down-weight rather than a smarter operator.
    """
    g = gray.astype(np.float32)
    energy = np.zeros_like(g)
    energy[:, :-1] += np.abs(np.diff(g, axis=1))
    energy[:-1, :] += np.abs(np.diff(g, axis=0))
    energy = cv2.blur(energy, (15, 15))
    for x, y, w, h in bubbles:
        energy[y : y + h, x : x + w] *= bubble_weight
    return energy


def _window_geometry(pw: int, ph: int, frame_w: int, frame_h: int) -> tuple[int, int, str, int]:
    """Largest frame-shaped window inside the panel: (win_w, win_h, free_axis, span)."""
    ar = frame_w / frame_h
    win_w = min(pw, int(round(ph * ar)))
    win_h = min(ph, int(round(win_w / ar)))
    win_w = min(pw, int(round(win_h * ar)))
    if ph - win_h >= pw - win_w:
        return win_w, win_h, "y", ph - win_h
    return win_w, win_h, "x", pw - win_w


def _offset_profile(sal: np.ndarray, axis: str, win_len: int) -> np.ndarray:
    """Total salience captured by the window at each offset along the free axis."""
    line = sal.sum(axis=1) if axis == "y" else sal.sum(axis=0)
    span = len(line) - win_len
    if span <= 0:
        return np.array([line.sum()])
    csum = np.concatenate([[0.0], np.cumsum(line)])
    return csum[win_len:] - csum[:-win_len]


def _snap_offset(
    offset: int,
    win_len: int,
    bubbles: list[tuple[int, int, int, int]],
    axis: str,
    max_offset: int,
) -> int:
    """Nudge a resting offset so no bubble is sliced by the window edge.

    Tries small shifts either side; a bubble must end up fully inside or fully outside.
    If no clean position exists within the search range the original offset stands —
    a clipped bubble beats losing the salient art entirely.
    """
    def clips(o: int) -> bool:
        lo, hi = o, o + win_len
        for bx, by, bw, bh in bubbles:
            b0 = by if axis == "y" else bx
            b1 = b0 + (bh if axis == "y" else bw)
            if b0 < lo < b1 or b0 < hi < b1:
                return True
        return False

    if not clips(offset):
        return offset
    reach = max(4, int(win_len * 0.15))
    for delta in range(1, reach):
        for cand in (offset - delta, offset + delta):
            if 0 <= cand <= max_offset and not clips(cand):
                return cand
    return offset


def render_fill_frame_frames(
    panel_path: Path,
    width: int,
    height: int,
    num_frames: int,
    config: dict[str, Any],
    *,
    seed: str = "",
) -> list[Image.Image]:
    """Salience-framed fill-frame camera: static, pan, or pan-with-reframe-cut.

    - The window is the largest 16:9 rect inside the panel; the free axis is walked in
      reading order (down, or left-to-right), speed-capped like the scroll path.
    - Resting frames snap so bubbles are never edge-clipped.
    - A dwell over `video.max_dwell_seconds` becomes TWO shots on the same panel — a
      hard mid-cut to a later segment (or a closer window when there is nowhere left to
      go). This replaces the audit's 14-18s frozen holds without touching the timeline:
      frame count, and therefore A/V lock, is unchanged.
    """
    fps = int(get_nested(config, "video", "fps", default=30))
    max_px_per_sec = float(get_nested(config, "video", "max_scroll_px_per_sec", default=600.0))
    max_dwell = float(get_nested(config, "video", "max_dwell_seconds", default=7.0))
    bubble_weight = float(get_nested(config, "video", "bubble_salience_weight", default=0.15))

    panel = crop_to_content(Image.open(panel_path).convert("RGB"))
    arr = np.asarray(panel)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    bubbles = _bubble_boxes(gray)
    sal = _salience(gray, bubbles, bubble_weight=bubble_weight)

    win_w, win_h, axis, span = _window_geometry(panel.width, panel.height, width, height)
    profile = _offset_profile(sal, axis, win_h if axis == "y" else win_w)
    win_len = win_h if axis == "y" else win_w
    max_offset = max(0, span)

    duration = num_frames / max(fps, 1)
    travel_cap = int(max_px_per_sec * duration)

    # Choose the traversal segment(s). Reading order is forward-only on the free axis.
    legs: list[tuple[int, int]] = []  # (start_offset, end_offset)
    if span <= max(8, int(0.08 * win_len)):
        best = int(np.argmax(profile))
        best = _snap_offset(best, win_len, bubbles, axis, max_offset)
        legs = [(best, best)]
    else:
        travel = min(span, travel_cap)
        if travel < span:
            # Cannot cover the whole panel at a readable speed: pick the segment of
            # length travel+win_len that captures the most salience.
            seg = np.concatenate([[0.0], np.cumsum(profile)])
            n = len(profile) - travel
            start = int(np.argmax(seg[travel:] - seg[:-travel])) if n > 0 else 0
        else:
            start = 0
        start = _snap_offset(start, win_len, bubbles, axis, max_offset)
        end = _snap_offset(min(start + travel, max_offset), win_len, bubbles, axis, max_offset)
        legs = [(start, max(start, end))]

    # Re-frame cut for long dwells: split into two forward legs, or push in closer.
    zoom_in_leg = False
    if duration > max_dwell and num_frames >= 2 * fps:
        (start, end) = legs[0]
        mid = (start + end) // 2
        jump = mid + win_len // 2
        if jump < end:
            # Enough travel left after the midpoint for a real cut: jump half a window
            # forward so the second shot opens on visibly new content.
            legs = [(start, mid), (jump, end)]
        else:
            legs = [(start, end), (end, end)]
            zoom_in_leg = True

    z0, z1 = ken_burns_params(seed or str(panel_path))
    frames: list[Image.Image] = []
    per_leg = [num_frames // len(legs)] * len(legs)
    per_leg[-1] += num_frames - sum(per_leg)
    for leg_idx, ((o0, o1), leg_frames) in enumerate(zip(legs, per_leg)):
        closer = zoom_in_leg and leg_idx == len(legs) - 1
        for i in range(leg_frames):
            t = i / max(leg_frames - 1, 1)
            offset = o0 + (o1 - o0) * cosine_ease(t)
            zoom = z0 + (z1 - z0) * t
            if closer:
                zoom = 1.30 + 0.05 * t  # push-in accent on the same window
            cw, ch = win_w / zoom, win_h / zoom
            if axis == "y":
                cx = panel.width / 2.0
                cy = offset + win_h / 2.0
            else:
                cx = offset + win_w / 2.0
                cy = panel.height / 2.0
            left = max(0.0, min(panel.width - cw, cx - cw / 2.0))
            top = max(0.0, min(panel.height - ch, cy - ch / 2.0))
            crop = panel.crop((int(left), int(top), int(left + cw), int(top + ch)))
            frames.append(crop.resize((width, height), Image.Resampling.LANCZOS))
    return frames


def render_panel_motion_frames(
    panel_path: Path,
    panel: Panel,
    width: int,
    height: int,
    num_frames: int,
    config: dict[str, Any],
    *,
    seed_salt: int | None = None,
) -> list[Image.Image]:
    mode = choose_camera_mode(panel, config)
    if mode == "scroll" and panel.split_method == "strip":
        # A genuine continuous strip: the classic full-width crawl reads best.
        return render_vertical_scroll_frames(panel_path, width, height, num_frames, config)

    # `seed_salt` is the panel's position in the timeline, so a panel shown twice gets
    # two different camera moves instead of a byte-identical repeat the eye reads as a
    # glitch. Omitted (None) keeps the original panel-id-only seed, so existing
    # single-appearance renders are unchanged.
    seed = panel.id if seed_salt is None else f"{panel.id}:{seed_salt}"

    # Fill-frame guard: a panel so small that filling the frame would over-magnify it
    # falls back to the whole-panel letterbox (blur bars) rather than a soft smear.
    max_fill_zoom = float(get_nested(config, "video", "max_fill_zoom", default=3.2))
    try:
        with Image.open(panel_path) as probe:
            pw, ph = probe.size
    except OSError:
        pw, ph = panel.bbox.width, panel.bbox.height
    win_w, _win_h, _axis, _span = _window_geometry(max(pw, 1), max(ph, 1), width, height)
    if width / max(win_w, 1) > max_fill_zoom:
        z0, z1 = ken_burns_params(seed)
        base = letterbox_panel(panel_path, width, height)
        return render_ken_burns_frames(
            base, num_frames, z0, z1, config, width=width, height=height
        )

    return render_fill_frame_frames(
        panel_path, width, height, num_frames, config, seed=seed
    )


def add_chapter_badge(frame: Image.Image, chapters: str, title: str) -> Image.Image:
    img = frame.copy()
    draw = ImageDraw.Draw(img)
    badge = f"Ch. {chapters}  •  {title}"
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    padding = 16
    bbox = draw.textbbox((0, 0), badge, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = 40, 40
    draw.rectangle([x - padding, y - padding, x + tw + padding, y + th + padding], fill=(0, 0, 0))
    draw.text((x, y), badge, fill=(255, 255, 255), font=font)
    return img
