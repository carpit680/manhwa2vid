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
    max_width: int | None = None,
    jpeg_quality: int = 80,
) -> tuple[str, str]:
    """Return (media_type, base64_data) suitable for data-URL embedding.

    max_side defaults to config scene.vision_max_side — image tokens scale with area,
    so this is the main lever on vision token spend (512px ≈ 0.44x the tokens of 768px).

    `max_width` constrains WIDTH ONLY and must be used for whole PAGES. Capping the
    longest side is correct for panel crops, which are roughly square, and catastrophic
    for a webtoon strip: a Frozen Player page is 800x10060, so a 512 longest-side cap
    produced a 40x512 sliver — 6 KB from a 3.5 MB page, with every caption and system
    message reduced to noise. The story-first stages read pages, and they silently read
    illegible ones until this was measured (the 76-hour time marker, printed on the page,
    was simply invisible).
    """
    if max_side is None and max_width is None:
        from manhwa2vid.config import get_nested, load_config

        max_side = int(get_nested(load_config(), "scene", "vision_max_side", default=768))
    with Image.open(path) as img:
        rgb = img.convert("RGB")
        width, height = rgb.size
        if max_width is not None:
            if width > max_width:
                scale = max_width / width
                rgb = rgb.resize(
                    (max_width, max(1, int(height * scale))), Image.Resampling.LANCZOS
                )
        elif max(width, height) > max_side:
            scale = max_side / max(width, height)
            rgb = rgb.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.Resampling.LANCZOS,
            )
        buffer = io.BytesIO()
        rgb.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
        data = base64.b64encode(buffer.getvalue()).decode("ascii")
        return "image/jpeg", data


def page_max_width(config: dict | None = None) -> int:
    """Width cap for whole-PAGE vision calls.

    Separate from `scene.vision_max_side` because that value (512) is tuned for panel
    CROPS and is measured harmful on pages: a webtoon strip is ~800x10000, so a
    longest-side cap scales it to a 40px-wide sliver and every caption, speech bubble
    and system message becomes unreadable. Width is the dimension that determines
    whether text can be read; height should be left alone.
    """
    from manhwa2vid.config import get_nested, load_config

    return int(get_nested(config or load_config(), "read", "page_max_width", default=1024))
