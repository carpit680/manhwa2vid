"""ffmpeg video rendering."""

from __future__ import annotations

import json
import os
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

from manhwa2vid.video.effects import render_panel_motion_frames

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
    upscale_map: dict[str, Path] | None = None,
    num_frames: int | None = None,
    prefer_art: bool = False,
) -> Path:
    panel_path = project_root / entry.panel_path
    upscaled = upscale_map.get(panel_path.name) if upscale_map else None
    if upscaled is not None:
        panel_path = upscaled
    if num_frames is None:
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
        panel_path, panel, width, height, num_frames, config, seed_salt=entry_index,
        prefer_art=prefer_art,
    )
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
    pad_seconds: float = 0.0,
) -> dict[str, Any]:
    audio_dir = project_root / "audio"
    beat_files: list[Path] = []
    seen: set[str] = set()
    for entry in timeline.entries:
        if entry.audio_file and entry.audio_file not in seen:
            seen.add(entry.audio_file)
            beat_files.append(project_root / entry.audio_file)

    if not beat_files:
        shutil.copy2(video_path, output)
        return {}

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
    bgm_files = sorted(bgm_dir.glob("*.mp3")) + sorted(bgm_dir.glob("*.wav"))

    # ONE graph, measured then rendered. Two-pass loudnorm only works if pass two
    # normalizes the signal pass one measured, and the old code measured the mixed MP4
    # after the fact — a different signal, already AAC-encoded, from a different filter
    # chain. See docs/audio-quality-spec.md §5 and video/master.py.
    from manhwa2vid.video import master

    target = float(get_nested(config, "export", "loudness_target", default=-14))
    lra = float(get_nested(config, "video", "loudness_range", default=7))

    inputs = ["-i", str(video_path), "-i", str(narration)]
    if bgm_files:
        inputs += ["-i", str(bgm_files[0])]

    def graph(loudnorm: str) -> str:
        return master.build_filter(
            config, pad_seconds=max(pad_seconds, 0.0),
            with_bed=bool(bgm_files), loudnorm=loudnorm,
        )

    probe = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", *inputs,
         "-filter_complex", graph(master.measure_pass(target, lra)),
         "-map", "[aout]", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    measured = _parse_loudnorm(probe.stderr)
    loudnorm = (
        master.render_pass(target, lra, measured) if measured
        else master.measure_pass(target, lra).replace(":print_format=json", "")
    )
    if not measured:
        console.print("[yellow]loudnorm measurement failed — falling back to single pass[/]")

    _run_ffmpeg([
        *inputs,
        "-filter_complex", graph(loudnorm),
        "-map", "0:v", "-map", "[aout]",
        # loudnorm resamples internally to 192 kHz; pin the rate or the output lands at
        # 96 kHz from 24 kHz sources.
        "-ar", "48000",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        # Without this the moov atom lands after mdat and several players refuse to start
        # until the whole file has downloaded.
        "-movflags", "+faststart",
        "-shortest", str(output),
    ])
    # Measure the duck against the STEM before it is deleted — this is the only moment
    # both signals exist, and the mix alone cannot recover it.
    from manhwa2vid.measure.audio import duck_depth_from_stem

    duck = duck_depth_from_stem(narration, output)
    narration.unlink(missing_ok=True)
    return {"duck_depth_db": duck} if duck is not None else {}


def _parse_loudnorm(text: str) -> dict[str, str] | None:
    """Pull the measured_* values out of a loudnorm print_format=json pass."""
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

    # Optional 2x anime upscale for the panels actually on screen (cached in
    # panels_2x/). Source art is 720-800px wide; the fill-frame camera magnifies
    # 2.4-2.7x at 1080p, and Lanczos alone is visibly soft at that zoom.
    from manhwa2vid.video.upscale import upscale_panels

    shown = []
    seen_paths: set[str] = set()
    for entry in timeline.entries:
        if entry.panel_path not in seen_paths:
            seen_paths.add(entry.panel_path)
            shown.append(paths["root"] / entry.panel_path)
    upscale_map = upscale_panels(shown, paths["root"], config)

    with tempfile.TemporaryDirectory(prefix="m2v_") as tmp:
        frames_dir = Path(tmp) / "frames"
        frames_dir.mkdir()
        clips: list[Path] = []

        # Frame accounting is CUMULATIVE: int(duration*fps) per entry truncates up to
        # one frame each, and across 252 shots that quietly shortened the video ~4s
        # while the narration stayed full length — a progressive A/V desync that grew
        # toward the end of every render (measured 2.0s short on a 128-shot cut).
        acc_time = 0.0
        acc_frames = 0
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
                acc_time += entry.duration
                target_frames = round(acc_time * fps)
                num_frames = max(target_frames - acc_frames, 1)
                acc_frames += num_frames
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
                    upscale_map,
                    # A viewer decides in the first ten seconds, so the opening shots are
                    # framed for artwork rather than for contrast. Judged on the shot's
                    # START: `acc_time` is already its END here, and testing that excluded
                    # the shot STRADDLING the boundary — which is precisely the one that
                    # kept Solo Leveling's opening failing, at 74% lettering on t=14.5s.
                    prefer_art=(acc_time - entry.duration) < opening_art_seconds,
                    num_frames=num_frames,
                )
                clips.append(clip)
                progress.advance(task)


        silent = Path(tmp) / "silent.mp4"
        _concat_clips(clips, silent, fps)
        # _mix_audio now masters and normalizes in one graph, so there is no separate
        # normalize step to undo it. The old shape mixed to an AAC intermediate and then
        # measured THAT, which is a different signal from the one being normalized.
        audio_extra = _mix_audio(timeline, paths["root"], silent, output, config,
                                 pad_seconds=0.0)

    if not final:
        shutil.copy2(output, paths["output"] / "preview.mp4")

    console.print(f"[green]Rendered[/] → {output}")

    # QA on the FINAL SURFACE — the pixels and samples that actually ship. Env wins
    # over config (like SCRIPT_ARCHITECTURE), so the pipeline tests — which drive real
    # renders of SYNTHETIC panels through the repo config — can opt out without
    # mutating the shared config.yaml.
    env_qa = os.getenv("MANHWA2VID_RENDER_QA")
    run_qa = (
        env_qa not in ("0", "false", "off")
        if env_qa is not None
        else bool(get_nested(config, "video", "render_qa", default=False))
    )
    if run_qa:
        from manhwa2vid.video.qa_visual import enforce_render_qa

        enforce_render_qa(output, paths, config, extra_metrics=audio_extra)
    return output
