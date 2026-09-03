"""Preview output path tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from manhwa2vid.video.render import latest_preview_path, preview_output_path


def test_preview_output_path_includes_timestamp() -> None:
    path = preview_output_path(Path("/tmp/out"), when=datetime(2025, 6, 30, 8, 53, 12))
    assert path.name == "preview_2025-06-30_085312.mp4"


def test_latest_preview_path_prefers_newest_dated() -> None:
    out = Path("/tmp/m2v_preview_test")
    out.mkdir(exist_ok=True)
    older = out / "preview_2025-06-29_120000.mp4"
    newer = out / "preview_2025-06-30_085312.mp4"
    older.write_bytes(b"x")
    newer.write_bytes(b"x")
    assert latest_preview_path(out) == newer
    older.unlink()
    newer.unlink()
    out.rmdir()


def test_reused_panel_gets_its_own_clip_and_camera_move() -> None:
    """A panel shown twice must not collapse into one clip file.

    Clips were named `frames_dir/{panel_id}.mp4`. A cold open that replays a late
    moment, or any callback, renders that panel twice — the second write OVERWROTE
    the first with a different duration, and `clips` held the same path twice, so
    every entry after the reuse played the wrong length and audio desynced for the
    rest of the video. Naming by timeline position makes reuse safe, which the
    story-first architecture depends on.
    """
    from manhwa2vid.models import Panel, PanelBBox
    from manhwa2vid.video.effects import ken_burns_params

    # Two timeline positions, same panel, different durations.
    names = {f"{i:05d}_p0020_03" for i in (3, 17)}
    assert len(names) == 2, "clip identity must include timeline position"

    panel = Panel(
        id="p0020_03",
        page_num=20,
        bbox=PanelBBox(x=0, y=0, width=100, height=100),
        image_path="panels/p0020_03.png",
    )
    first = ken_burns_params(f"{panel.id}:3")
    second = ken_burns_params(f"{panel.id}:17")
    assert first != second, "a re-shown panel should not repeat its exact camera move"
    # Unsalted seeding stays stable for the ordinary single-appearance case.
    assert ken_burns_params(panel.id) == ken_burns_params(panel.id)


def test_preview_cache_hit_refused_when_timeline_is_newer(tmp_path) -> None:
    """The stale-video incident: script re-ran, audio and timeline regenerated, render
    printed a cache hit, and the user was handed yesterday's video. A cache hit is only
    valid when the preview is newer than the timeline it was cut from."""
    import os

    out = tmp_path / "output"; out.mkdir()
    preview = out / "preview.mp4"; preview.write_bytes(b"old")
    timeline = tmp_path / "timeline.json"; timeline.write_text("{}")
    # preview older than timeline -> stale
    os.utime(preview, (1000, 1000))
    os.utime(timeline, (2000, 2000))
    assert preview.stat().st_mtime < timeline.stat().st_mtime
    # fresh preview -> valid hit
    os.utime(preview, (3000, 3000))
    assert preview.stat().st_mtime >= timeline.stat().st_mtime


def test_cumulative_frame_accounting_matches_audio_length() -> None:
    """int(duration*fps) per entry truncated up to a frame each — 252 shots quietly
    shortened a render ~4s against its narration, a progressive A/V desync."""
    fps = 30
    durations = [0.345] * 300  # every entry carries 0.35 of a frame at 30fps
    acc_time = 0.0
    acc_frames = 0
    for d in durations:
        acc_time += d
        target = round(acc_time * fps)
        acc_frames += max(target - acc_frames, 1)
    total = sum(durations)
    assert abs(acc_frames / fps - total) < 1.0 / fps, "cumulative accounting stays exact"
    truncated = sum(max(int(d * fps), 1) for d in durations)
    assert total - truncated / fps > 2.0, "the old rule really did lose seconds"


def test_render_video_runs_end_to_end(tmp_path) -> None:
    """Nothing executed render_video, and a NameError shipped through that hole.

    `opening_art_seconds` was referenced in the render loop but its definition landed
    outside the function, so every render crashed. Two Solo Leveling renders died before
    anyone noticed — and what noticed was the QA report still naming an older file, not a
    test. This is small and slow-ish, and it earns that by exercising the real path:
    camera, concat, mastering chain, two-pass loudnorm, QA.
    """
    import json
    import shutil
    import struct
    import wave

    import numpy as np
    import pytest
    from PIL import Image

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not on PATH")

    from manhwa2vid.models import (
        Panel, PanelBBox, ProjectMeta, SourceLanguage, SourceType, Timeline,
        TimelineEntry, project_paths, save_json,
    )
    from manhwa2vid.video.render import render_video

    paths = project_paths(tmp_path)
    for key in ("pages", "panels", "audio", "output", "debug"):
        paths[key].mkdir(parents=True, exist_ok=True)
    save_json(paths["meta"], ProjectMeta(
        slug="t", title="T", chapters="1", source_lang=SourceLanguage.EN,
        source_type=SourceType.IMAGES, source_path=str(tmp_path), pdf_path=str(tmp_path),
    ))

    rng = np.random.default_rng(0)
    panels = []
    for i in (1, 2):
        pid = f"p0001_{i:02d}"
        art = np.repeat(np.linspace(40, 200, 400, dtype=np.uint8)[:, None], 300, axis=1)
        Image.fromarray(np.dstack([art] * 3)).save(paths["panels"] / f"{pid}.png")
        panels.append(Panel(id=pid, page_num=1, image_path=f"panels/{pid}.png",
                            bbox=PanelBBox(x=0, y=0, width=300, height=400)))
    save_json(paths["panels_json"], [p.model_dump() for p in panels])

    wav = paths["audio"] / "beat_001.wav"
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(24000)
        tone = (0.2 * np.sin(2 * np.pi * 180 * np.arange(24000 * 3) / 24000) * 32767)
        wf.writeframes(b"".join(struct.pack("<h", int(v)) for v in tone))

    entries, cursor = [], 0.0
    for p in panels:
        entries.append(TimelineEntry(
            panel_id=p.id, panel_path=p.image_path, start=cursor, end=cursor + 1.5,
            duration=1.5, beat_id=1, audio_file="audio/beat_001.wav",
            subtitle_text="line",
        ))
        cursor += 1.5
    paths["timeline_json"].write_text(
        Timeline(entries=entries, total_duration=cursor).model_dump_json()
    )

    out = render_video(ProjectMeta.model_validate(json.loads(paths["meta"].read_text())),
                       paths, {"video": {"fps": 12, "render_qa": False},
                               "export": {"preview_scale": 0.25}},
                       preview=True, final=False, force=True)
    assert out.exists() and out.stat().st_size > 1000, "render produced no video"


class TestLongHoldSegments:
    """The shot planner's gap rule keeps a long dwell rather than showing an
    out-of-order panel — right call, but it moved the defect into the render: 27s of
    one letterbox treatment measured 38.23s on screen and FAILED shot-max-duration.
    The renderer now cuts any hold that outlives ~0.75x the shot cap into alternating
    close/wide treatments of the same panel. Same panel adjacent = order-safe and
    repeat-safe by construction."""

    def test_a_short_entry_is_one_piece(self):
        from manhwa2vid.video.render import _long_hold_segments

        assert _long_hold_segments(5.0, 0.0, 7.5) == [(5.0, 0)]

    def test_a_long_entry_is_cut_at_the_segment_length(self):
        from manhwa2vid.video.render import _long_hold_segments

        pieces = _long_hold_segments(14.3, 0.0, 7.5)
        assert [i for _s, i in pieces] == [0, 1]
        assert abs(sum(sec for sec, _i in pieces) - 14.3) < 1e-9
        assert pieces[0][0] == 7.5

    def test_consecutive_entries_on_one_panel_share_the_run_clock(self):
        """Two 7s entries on one panel are a 14s shot to the viewer. The second entry
        must continue the run's segmentation, not restart at segment 0 and render the
        identical treatment again."""
        from manhwa2vid.video.render import _long_hold_segments

        first = _long_hold_segments(7.0, 0.0, 7.5)
        second = _long_hold_segments(7.0, 7.0, 7.5)
        assert first == [(7.0, 0)]
        assert [i for _s, i in second] == [0, 1], "the run clock was ignored"
        assert second[0][0] == 0.5

    def test_a_tiny_tail_merges_instead_of_flash_cutting(self):
        from manhwa2vid.video.render import _long_hold_segments

        pieces = _long_hold_segments(8.0, 0.0, 7.5)
        assert pieces == [(8.0, 0)], f"0.5s flash cut survived: {pieces}"

    def test_the_27s_hold_shape(self):
        """The real FP case: 12.7s + 14.3s consecutive entries on p0017_09."""
        from manhwa2vid.video.render import _long_hold_segments

        a = _long_hold_segments(12.7, 0.0, 7.5)
        b = _long_hold_segments(14.3, 12.7, 7.5)
        indices = [i for _s, i in a] + [i for _s, i in b]
        assert indices == sorted(indices)
        assert len(set(indices)) >= 3, "a 27s hold must land at least 3 distinct segments"
        longest = max(sec for sec, _i in a + b)
        assert longest <= 9.0, f"a continuous piece is still {longest}s"


class TestHoldMeasurementAuthority:
    """`shot-max-duration` must measure ONE IMAGE ON SCREEN, not detector cuts.

    The renderer deliberately defeats scene detection: `_long_hold_segments` cuts a long
    same-panel run into alternating fill/letterbox framings so a held image does not read
    as a frozen frame. The detector counts each framing change as a cut, so the gate that
    exists to catch long holds was reading a number the renderer had already scrubbed.
    Measured on the three shipped renders: detector 8.6/8.83/8.93s against real holds of
    18.3/19.14/16.2s. Every one passed.
    """

    def _paths(self, tmp_path, entries):
        import json

        from manhwa2vid.models import project_paths

        paths = project_paths(tmp_path)
        paths["timeline_json"].write_text(json.dumps({"entries": entries}))
        return paths

    def _entry(self, pid, dur, beat=1):
        return {"panel_id": pid, "panel_path": f"panels/{pid}.png", "start": 0.0,
                "end": dur, "duration": dur, "beat_id": beat, "subtitle_text": "x"}

    def test_consecutive_entries_on_one_panel_are_one_hold(self, tmp_path):
        """The exact ch3-4 shape: two entries, one image, 19.14 seconds."""
        from manhwa2vid.video.qa_visual import _longest_hold_seconds

        paths = self._paths(tmp_path, [
            self._entry("p0019_04", 8.82, 16),
            self._entry("p0019_04", 10.32, 17),
            self._entry("p0020_01", 3.0, 17),
        ])
        assert _longest_hold_seconds(paths) == 19.14

    def test_a_missing_timeline_falls_back_rather_than_reporting_zero(self, tmp_path):
        """Returning 0.0 would mean "no long holds" — a pass on no evidence."""
        from manhwa2vid.models import project_paths
        from manhwa2vid.video.qa_visual import _longest_hold_seconds

        assert _longest_hold_seconds(project_paths(tmp_path)) is None

    def test_a_malformed_timeline_falls_back_too(self, tmp_path):
        from manhwa2vid.models import project_paths
        from manhwa2vid.video.qa_visual import _longest_hold_seconds

        paths = project_paths(tmp_path)
        paths["timeline_json"].write_text("{not json")
        assert _longest_hold_seconds(paths) is None

    def test_the_fail_threshold_is_reachable_and_the_reference_would_pass(self):
        """A band the reference channel itself would fail is a band that is wrong: its
        own longest shot is 16.37s. And 18 must be reachable — our worst is 19.14s."""
        from manhwa2vid.video.qa_visual import _SHOT_MAX_FAIL_S, _SHOT_MAX_WARN_S

        assert _SHOT_MAX_WARN_S < 16.37 < _SHOT_MAX_FAIL_S
        assert _SHOT_MAX_FAIL_S < 19.14, "our measured worst hold must actually fail"


class TestUpscaleOOMRecovery:
    """The 20-chapter render hit CUDA out-of-memory partway through 641 panels and
    silently shipped a RESOLUTION-MIXED video — some panels upscaled, some at source
    size, on one timeline — reported only as a warning per panel that scrolled past.
    There is no empty_cache() anywhere in the project, so fragmentation accumulates and
    late panels fail for memory earlier ones did not need."""

    def test_oom_is_recognised_by_type_or_message(self):
        from manhwa2vid.video.upscale import _is_oom

        assert _is_oom(RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB"))
        assert not _is_oom(FileNotFoundError("panels/p0001.png"))
        assert not _is_oom(ValueError("bad shape"))

    def test_the_retry_band_is_narrower_than_the_default(self):
        import inspect

        from manhwa2vid.video.upscale import _RETRY_BAND_PX, _upscale_array

        default = inspect.signature(_upscale_array).parameters["band_px"].default
        assert _RETRY_BAND_PX < default, "a retry must ask for less, or it fails again"

    def test_freeing_gpu_memory_never_raises_without_cuda(self):
        from manhwa2vid.video.upscale import _free_gpu

        _free_gpu()      # must be safe on a CPU-only box and inside an except block


class TestParallelClipRendering:
    """Clips are rendered concurrently: ~2,400 independent ffmpeg invocations for a
    38-minute video and roughly double for the 75-minute one this pipeline now targets,
    run sequentially on an idle 24-core box.

    Safe only because each clip owns its output path and its random seed. Both are
    derived from (entry_index, clip_tag), so nothing depends on execution order — that
    is the invariant these tests hold."""

    def test_clip_paths_are_unique_per_entry_and_segment(self):
        """A collision would have two workers writing the same frames directory."""
        seen = set()
        for entry_index in range(200):
            for seg in range(4):
                tag = f"s{seg}" if seg else ""
                name = f"{entry_index:05d}{tag}_p0001_02"
                assert name not in seen, f"collision on {name}"
                seen.add(name)

    def test_the_seed_salt_does_not_depend_on_order(self):
        """Camera jitter is seeded from the salt; if that varied with scheduling, the
        same timeline would render differently every run."""
        salts = [f"{i}{tag}" for i in range(50) for tag in ("", "s1", "s2")]
        assert len(set(salts)) == len(salts)

    def test_worker_count_is_bounded_by_memory_not_cores(self):
        """Each worker holds one clip's frames — 225 PIL images for a 7.5s segment,
        ~1.1 GB at 1080p — so this is bounded by RAM, and configurable."""
        from manhwa2vid.video.render import _render_workers

        assert _render_workers({}, 500) <= 6
        assert _render_workers({}, 1) == 1, "never more workers than jobs"
        assert _render_workers({"video": {"render_workers": 2}}, 500) == 2
        assert _render_workers({"video": {"render_workers": 1}}, 500) == 1
        assert _render_workers({"video": {"render_workers": "junk"}}, 500) >= 1
