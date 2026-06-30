"""YouTube export pack: captions, thumbnail, metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageDraw, ImageFont
from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.models import ProjectMeta, Timeline, TimelineEntry

console = Console()


def _format_srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(timeline: Timeline, path: Path) -> None:
    lines: list[str] = []
    idx = 1
    for entry in timeline.entries:
        if not entry.subtitle_text.strip():
            continue
        lines.extend(
            [
                str(idx),
                f"{_format_srt_time(entry.start)} --> {_format_srt_time(entry.end)}",
                entry.subtitle_text,
                "",
            ]
        )
        idx += 1
    path.write_text("\n".join(lines), encoding="utf-8")


def write_metadata(meta: ProjectMeta, timeline: Timeline, path: Path) -> None:
    payload = {
        "title": f"{meta.title} Chapters {meta.chapters} | Manhwa Recap",
        "description": (
            f"Recap of {meta.title} chapters {meta.chapters}.\n\n"
            f"Duration: {timeline.total_duration / 60:.1f} minutes\n"
            "#manhwa #recap #webtoon"
        ),
        "tags": ["manhwa", "recap", "webtoon", meta.title.lower()],
    }
    path.write_text(yaml.dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def write_thumbnail(meta: ProjectMeta, timeline: Timeline, project_root: Path, path: Path) -> None:
    first = timeline.entries[0] if timeline.entries else None
    if first:
        panel = project_root / first.panel_path
        if panel.exists():
            base = Image.open(panel).convert("RGB")
        else:
            base = Image.new("RGB", (1280, 720), (20, 20, 30))
    else:
        base = Image.new("RGB", (1280, 720), (20, 20, 30))

    base = base.resize((1280, 720), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(base)
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
    except OSError:
        font_title = ImageFont.load_default()
        font_sub = font_title

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle([0, 520, 1280, 720], fill=(0, 0, 0, 180))
    base = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(base)
    draw.text((40, 540), meta.title, fill=(255, 255, 255), font=font_title)
    draw.text((40, 620), f"Chapters {meta.chapters}", fill=(255, 220, 80), font=font_sub)
    path.parent.mkdir(parents=True, exist_ok=True)
    base.save(path)


def export_youtube_pack(meta: ProjectMeta, paths: dict[str, Path], config: dict[str, Any]) -> None:
    timeline = Timeline.model_validate(json.loads(paths["timeline_json"].read_text()))
    out_dir = paths["output"]
    out_dir.mkdir(parents=True, exist_ok=True)

    srt = out_dir / "final.srt"
    write_srt(timeline, srt)
    write_metadata(meta, timeline, out_dir / "metadata.yaml")
    write_thumbnail(meta, timeline, paths["root"], out_dir / "thumbnail.png")

    final = out_dir / "final.mp4"
    if not final.exists() and (out_dir / "preview.mp4").exists():
        console.print("[yellow]Only preview.mp4 exists — export uses preview for metadata[/]")

    console.print(f"[green]Export pack written[/] → {out_dir}")
