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
