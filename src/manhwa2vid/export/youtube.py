"""YouTube export pack: captions, thumbnail, metadata."""

from __future__ import annotations

import re
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


#: Measured across 864 competitor videos on six channels (2026-08-29): every channel's
#: median title length is exactly this, which is where YouTube truncates in browse and
#: search. See reports/field_measurement_2026-08-29.md.
TITLE_MAX_CHARS = 70


def title_problems(title: str, series: str) -> list[str]:
    """Field conventions a title must satisfy, as measurable checks.

    Only two packaging findings survived a within-channel test, and both are
    categorical rather than correlational — which is exactly why they are trustworthy:
    NO competitor title names its source series (0 of 864), and every channel writes to
    a 70-character median. The reversal-clause and CAPS-density "formula" did not
    survive (0.76-1.37x with four of five channels below 1.0) and is not enforced here.
    """
    problems = []
    if len(title) > TITLE_MAX_CHARS:
        problems.append(f"{len(title)} chars, over the {TITLE_MAX_CHARS} truncation point")

    # A CONTIGUOUS RUN of two or more series words, not any single one. Single-word
    # matching flagged "He Was Frozen For 25 Years..." because "Frozen" also appears in
    # "Return of the Frozen Player" — but that title is describing the story, which is
    # exactly what the field's titles do. What no competitor does is print the series
    # NAME, and a name shows up as consecutive words.
    words = [w for w in re.split(r"[^A-Za-z0-9']+", series) if w]
    runs = [" ".join(words[i : i + 2]) for i in range(len(words) - 1)]
    runs = [r for r in runs if len(r.replace(" ", "")) > 6]
    hit = next((r for r in runs if re.search(rf"\b{re.escape(r)}\b", title, re.I)), None)
    if hit:
        problems.append(
            f"names the source series ({hit!r}) — no competitor title does this "
            f"(0 of 864); the name belongs in the pinned comment"
        )
    return problems


def write_metadata(meta: ProjectMeta, timeline: Timeline, path: Path) -> None:
    """Emit the upload pack in the shape the field actually uses.

    What changed on 2026-08-30, and why each is evidence and not taste:

    - The title no longer leads with the series name. Not one top title on any measured
      channel names its source; the name is released in a pinned comment, which is a
      deliberate engagement mechanic.
    - The hashtags are gone. None of the large channels use them; the one channel that
      did is the collapsed one.
    - `title` is emitted as a TEMPLATE to fill, not an invented logline. Writing the
      hook is an editorial act with real consequences for how the video is represented,
      and the pipeline has no basis for it beyond the narration — so it hands over the
      constraints and the material rather than fabricating a claim about the story.
    """
    hook = (getattr(meta, "hook", "") or "").strip()
    payload = {
        "title": hook or f"TODO — write the hook, max {TITLE_MAX_CHARS} chars, do not name the series",
        "title_rules": [
            f"max {TITLE_MAX_CHARS} characters (every measured channel's median)",
            "do not name the source series (0 of 864 competitor titles do)",
        ],
        "pinned_comment": f"Source: {meta.title}, chapters {meta.chapters}.",
        "description": (
            f"Chapters {meta.chapters}.\n\n"
            f"Duration: {timeline.total_duration / 60:.1f} minutes"
        ),
        "tags": ["manhwa", "recap", "webtoon"],
    }
    if hook:
        payload["title_problems"] = title_problems(hook, meta.title) or ["none"]
    path.write_text(yaml.dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _thumbnail_entry(timeline: Timeline):
    """Pick the thumbnail frame.

    Was unconditionally `entries[0]`, which is only safe while narration starts at the
    beginning of the chapter. A cold open starts on a LATE moment, so the thumbnail
    became a spoiler for the chapter's climax. Prefer the longest-dwelling panel among
    the opening stretch: dwell is proportional to how much narration a panel carries,
    so it is already the pipeline's own measure of "this panel matters".
    """
    if not timeline.entries:
        return None
    head = timeline.entries[: max(1, len(timeline.entries) // 5)]
    return max(head, key=lambda e: e.duration)


def write_thumbnail(meta: ProjectMeta, timeline: Timeline, project_root: Path, path: Path) -> None:
    first = _thumbnail_entry(timeline)
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
