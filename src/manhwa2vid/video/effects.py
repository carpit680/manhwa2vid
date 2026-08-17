"""Video effects helpers."""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from manhwa2vid.config import get_nested
from manhwa2vid.models import Panel


def cosine_ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return (1.0 - math.cos(math.pi * t)) / 2.0


def letterbox_panel(panel_path: Path, width: int, height: int, blur_bg: bool = True) -> Image.Image:
    panel = Image.open(panel_path).convert("RGB")
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

    panel = Image.open(panel_path).convert("RGB")
    scale = out_w / panel.width
    scaled_h = max(int(panel.height * scale), out_h)
    scaled = panel.resize((out_w, scaled_h), Image.Resampling.LANCZOS)

    max_y = max(0, scaled_h - out_h)

    # Cap scroll speed. Travel is otherwise panel_height/dwell, which on a tall strip with a
    # short beat reaches thousands of px/s — an unreadable vertical smear. When the full panel
    # cannot be traversed at a readable speed, show the top portion instead of racing through it.
    fps = int(get_nested(config, "video", "fps", default=30))
    max_px_per_sec = float(get_nested(config, "video", "max_scroll_px_per_sec", default=600.0))
    if max_px_per_sec > 0 and fps > 0:
        duration = num_frames / fps
        allowed_travel = max_px_per_sec * duration * supersample
        max_y = min(max_y, int(allowed_travel))

    frames: list[Image.Image] = []
    for i in range(num_frames):
        t = i / max(num_frames - 1, 1)
        y = int(max_y * cosine_ease(t))
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


def render_panel_motion_frames(
    panel_path: Path,
    panel: Panel,
    width: int,
    height: int,
    num_frames: int,
    config: dict[str, Any],
) -> list[Image.Image]:
    mode = choose_camera_mode(panel, config)
    if mode == "scroll":
        return render_vertical_scroll_frames(panel_path, width, height, num_frames, config)

    z0, z1 = ken_burns_params(panel.id)
    base = letterbox_panel(panel_path, width, height)
    return render_ken_burns_frames(
        base, num_frames, z0, z1, config, width=width, height=height
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
