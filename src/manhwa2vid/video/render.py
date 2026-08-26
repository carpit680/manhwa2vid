"""ffmpeg video rendering."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from rich.console import Console
from rich.progress import Progress

from manhwa2vid.config import find_repo_root, get_nested
from manhwa2vid.models import Panel, PanelBBox, ProjectMeta, Timeline, TimelineEntry, save_json
from manhwa2vid.panels.filter import load_story_panels
from manhwa2vid.video.effects import add_chapter_badge, render_panel_motion_frames

console = Console()


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def preview_output_path(output_dir: Path, *, when: datetime | None = None) -> Path:
    stamp = (when or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    return output_dir / f"preview_{stamp}.mp4"


def latest_preview_path(output_dir: Path) -> Path | None:
    """Most recent preview clip in output dir (dated name or legacy preview.mp4)."""
    if not output_dir.exists():
        return None
    dated = sorted(output_dir.glob("preview_*.mp4"), reverse=True)
    if dated:
        return dated[0]
    legacy = output_dir / "preview.mp4"
    return legacy if legacy.exists() else None


def _run_ffmpeg(args: list[str]) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    subprocess.run(cmd, check=True)


def _render_panel_clip(
    entry: TimelineEntry,
    panel: Panel,
    project_root: Path,
    frames_dir: Path,
    entry_index: int,
    width: int,
    height: int,
    fps: int,
    config: dict[str, Any],
    chapters: str,
    title: str,
    show_badge: bool,
) -> Path:
    panel_path = project_root / entry.panel_path
    num_frames = max(int(entry.duration * fps), 1)
    # Named by TIMELINE POSITION, not panel id. A panel may legitimately appear more
    # than once — a cold open replays a late moment, and a callback re-shows it — and
    # keying the clip on panel_id alone meant the second render OVERWROTE the first
    # with a different duration. Both slots in `clips` then pointed at one file, so
    # every entry after the reuse played the wrong length and the audio desynced for
    # the rest of the video. Silent, and worse the more the narration calls back.
    clip_path = frames_dir / f"{entry_index:05d}_{entry.panel_id}.mp4"
    clip_dir = frames_dir / f"{entry_index:05d}_{entry.panel_id}"
    clip_dir.mkdir(parents=True, exist_ok=True)

    motion_frames = render_panel_motion_frames(
        panel_path, panel, width, height, num_frames, config, seed_salt=entry_index
    )
    if show_badge and motion_frames:
        motion_frames[0] = add_chapter_badge(motion_frames[0], chapters, title)

    for i, frame in enumerate(motion_frames):
        frame.save(clip_dir / f"{i:05d}.png")

    _run_ffmpeg(
        [
            "-framerate",
            str(fps),
            "-i",
            str(clip_dir / "%05d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-t",
            str(entry.duration),
            str(clip_path),
        ]
    )
    shutil.rmtree(clip_dir, ignore_errors=True)
    return clip_path


def _concat_clips(clips: list[Path], output: Path, fps: int) -> None:
    list_file = output.with_suffix(".txt")
    list_file.write_text("\n".join(f"file '{c.resolve()}'" for c in clips), encoding="utf-8")
    _run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            str(output),
        ]
    )
    list_file.unlink(missing_ok=True)


def _mix_audio(
    timeline: Timeline,
    project_root: Path,
    video_path: Path,
    output: Path,
    config: dict[str, Any],
) -> None:
    audio_dir = project_root / "audio"
    beat_files: list[Path] = []
    seen: set[str] = set()
    for entry in timeline.entries:
        if entry.audio_file and entry.audio_file not in seen:
            seen.add(entry.audio_file)
            beat_files.append(project_root / entry.audio_file)

    if not beat_files:
        shutil.copy2(video_path, output)
        return

    concat_list = output.with_suffix(".audio.txt")
    concat_list.write_text("\n".join(f"file '{f.resolve()}'" for f in beat_files), encoding="utf-8")
    narration = output.with_suffix(".narration.wav")
    _run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c:a",
            "pcm_s16le",
            str(narration),
        ]
    )
    concat_list.unlink(missing_ok=True)

    root = find_repo_root()
    bgm_dir = root / "assets" / "bgm"
    bgm_files = list(bgm_dir.glob("*.mp3")) + list(bgm_dir.glob("*.wav"))
    bgm_volume = float(get_nested(config, "video", "bgm_volume", default=0.18))

    if bgm_files:
        bgm = bgm_files[0]
        _run_ffmpeg(
            [
                "-i",
                str(video_path),
                "-i",
                str(narration),
                "-i",
                str(bgm),
                "-filter_complex",
                f"[1:a]volume=1.0[narr];[2:a]volume={bgm_volume},aloop=loop=-1:size=2e+09[bgm];"
                f"[narr][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map",
                "0:v",
                "-map",
                "[aout]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(output),
            ]
        )
    else:
        _run_ffmpeg(
            [
                "-i",
                str(video_path),
                "-i",
                str(narration),
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(output),
            ]
        )
    narration.unlink(missing_ok=True)


def _measure_loudness(input_path: Path, target: float) -> dict[str, str] | None:
    """First loudnorm pass: measure only. Returns the measured_* values for pass two."""
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-i",
            str(input_path),
            "-af",
            f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    text = proc.stderr
    start = text.rfind("{")
    if start == -1:
        return None
    try:
        data = json.loads(text[start:])
    except ValueError:
        return None
    keys = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    if not all(k in data for k in keys):
        return None
    return {k: str(data[k]) for k in keys}


def _normalize_loudness(input_path: Path, output: Path, target: float) -> None:
    # Two-pass loudnorm: single-pass runs in dynamic mode and overshoots true peak —
    # both audited videos measured +0.30/+0.35 dBTP (clips on transcode) despite the
    # alimiter, which limits SAMPLE peaks and is blind to inter-sample ones. Pass one
    # measures; pass two applies linearly, which honors TP=-1.5.
    measured = _measure_loudness(input_path, target)
    if measured:
        loudnorm = (
            f"loudnorm=I={target}:TP=-1.5:LRA=11:linear=true"
            f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}"
        )
    else:
        loudnorm = f"loudnorm=I={target}:TP=-1.5:LRA=11"
    # loudnorm internally resamples to 192 kHz, so pin the rate afterwards or the output
    # lands at 96 kHz from 24 kHz sources. alimiter's `limit` takes a LINEAR value, not a
    # dB string — 0.89 is about -1 dBFS of headroom (kept as a last-resort backstop).
    _run_ffmpeg(
        [
            "-i",
            str(input_path),
            "-af",
            f"{loudnorm},alimiter=limit=0.89,aresample=48000",
            "-ar",
            "48000",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            # Without this the moov atom lands after mdat (ffmpeg's default for a
            # streamed write), which several players — including the one used to hand
            # previews back for review — refuse to start until the whole file has
            # downloaded. Costs nothing extra to write it here since output is already
            # a fresh file.
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def render_video(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    preview: bool = True,
    final: bool = False,
    force: bool = False,
) -> Path:
    if not _ffmpeg_available():
        raise RuntimeError("ffmpeg not found on PATH")

    timeline = Timeline.model_validate(json.loads(paths["timeline_json"].read_text()))
    width = int(get_nested(config, "video", "width", default=1920))
    height = int(get_nested(config, "video", "height", default=1080))
    fps = int(get_nested(config, "video", "fps", default=30))
    preview_scale = float(get_nested(config, "export", "preview_scale", default=0.5))

    if preview and not final:
        width = int(width * preview_scale)
        height = int(height * preview_scale)

    if final:
        output = paths["output"] / "final.mp4"
        if output.exists() and not force:
            console.print(f"[dim]Using existing render[/] → {output}")
            return output
    else:
        latest_preview = paths["output"] / "preview.mp4"
        if latest_preview.exists() and not force:
            # A cache hit is only valid if the preview is NEWER than the timeline it
            # was cut from. Render was the one stage that cached on its own output
            # without checking its input's age, and the gap shipped: a re-run script
            # regenerated audio and timeline, render printed a cache hit, and the user
            # was handed yesterday's video with today's metrics reported against it.
            if latest_preview.stat().st_mtime >= paths["timeline_json"].stat().st_mtime:
                console.print(f"[dim]Using existing render[/] → {latest_preview}")
                return latest_preview
            console.print(
                "[yellow]Existing preview is older than timeline.json — re-rendering[/]"
            )
        output = preview_output_path(paths["output"])

    paths["output"].mkdir(parents=True, exist_ok=True)
    panels = {p.id: p for p in load_story_panels(paths)}

    with tempfile.TemporaryDirectory(prefix="m2v_") as tmp:
        frames_dir = Path(tmp) / "frames"
        frames_dir.mkdir()
        clips: list[Path] = []

        with Progress() as progress:
            task = progress.add_task("Rendering panels", total=len(timeline.entries))
            for i, entry in enumerate(timeline.entries):
                panel = panels.get(entry.panel_id)
                if panel is None:
                    panel = Panel(
                        id=entry.panel_id,
                        page_num=0,
                        bbox=PanelBBox(x=0, y=0, width=1, height=1),
                        image_path=entry.panel_path,
                    )
                show_badge = i == 0
                clip = _render_panel_clip(
                    entry,
                    panel,
                    paths["root"],
                    frames_dir,
                    i,
                    width,
                    height,
                    fps,
                    config,
                    meta.chapters,
                    meta.title,
                    show_badge,
                )
                clips.append(clip)
                progress.advance(task)

        silent = Path(tmp) / "silent.mp4"
        _concat_clips(clips, silent, fps)
        mixed = Path(tmp) / "mixed.mp4"
        _mix_audio(timeline, paths["root"], silent, mixed, config)

        target_lufs = float(get_nested(config, "export", "loudness_target", default=-14))
        _normalize_loudness(mixed, output, target_lufs)

    if not final:
        shutil.copy2(output, paths["output"] / "preview.mp4")

    console.print(f"[green]Rendered[/] → {output}")
    return output
