"""Resize/compress panel images before sending to vision APIs."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image


def encode_image_for_api(
    path: Path,
    *,
    max_side: int | None = None,
    jpeg_quality: int = 80,
) -> tuple[str, str]:
    """Return (media_type, base64_data) suitable for data-URL embedding.

    max_side defaults to config scene.vision_max_side — image tokens scale with area,
    so this is the main lever on vision token spend (512px ≈ 0.44x the tokens of 768px).
    """
    if max_side is None:
        from manhwa2vid.config import get_nested, load_config

        max_side = int(get_nested(load_config(), "scene", "vision_max_side", default=768))
    with Image.open(path) as img:
        rgb = img.convert("RGB")
        width, height = rgb.size
        longest = max(width, height)
        if longest > max_side:
            scale = max_side / longest
            rgb = rgb.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.Resampling.LANCZOS,
            )
        buffer = io.BytesIO()
        rgb.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
        data = base64.b64encode(buffer.getvalue()).decode("ascii")
        return "image/jpeg", data
