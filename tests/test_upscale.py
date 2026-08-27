"""Optional panel upscaling: never a dependency, never fatal."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from manhwa2vid.video.upscale import upscale_panels


def test_disabled_by_default_and_returns_nothing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MANHWA2VID_UPSCALE", raising=False)  # test the CODE default
    p = tmp_path / "a.png"
    Image.new("RGB", (64, 64)).save(p)
    assert upscale_panels([p], tmp_path, {}) == {}
    assert upscale_panels([p], tmp_path, {"video": {"upscale": {"enabled": False}}}) == {}


def test_env_off_switch_beats_config(tmp_path: Path) -> None:
    """conftest sets MANHWA2VID_UPSCALE=0 suite-wide; config cannot override it."""
    p = tmp_path / "a.png"
    Image.new("RGB", (64, 64)).save(p)
    assert upscale_panels([p], tmp_path, {"video": {"upscale": {"enabled": True}}}) == {}


def test_existing_outputs_are_reused_without_a_model(tmp_path: Path, monkeypatch) -> None:
    """Cache hits must not require spandrel/weights at all."""
    monkeypatch.setenv("MANHWA2VID_UPSCALE", "1")
    p = tmp_path / "a.png"
    Image.new("RGB", (64, 64)).save(p)
    out_dir = tmp_path / "panels_2x"
    out_dir.mkdir()
    Image.new("RGB", (128, 128)).save(out_dir / "a.png")
    mapping = upscale_panels([p], tmp_path, {"video": {"upscale": {"enabled": True}}})
    assert mapping == {"a.png": out_dir / "a.png"}


def test_a_cached_upscale_is_rejected_when_its_panel_changed(tmp_path):
    """Panel ids are POSITIONAL, so re-splitting reassigns them.

    Caching on file presence alone meant that after Frozen Player was re-split on
    2026-08-26, 64 of 172 cached upscales held a completely different picture from the
    panel of the same name — and four renders composited the old image while the
    timeline named the new one. Everything downstream stayed self-consistent, so only
    opening a frame and comparing it to its panel revealed it.
    """
    import os
    import time

    from PIL import Image

    from manhwa2vid.video.upscale import _cache_is_fresh

    panel = tmp_path / "p0001_01.png"
    cached = tmp_path / "cached.png"
    Image.new("RGB", (40, 30), (10, 20, 30)).save(panel)
    Image.new("RGB", (80, 60), (200, 100, 50)).save(cached)   # right SIZE, wrong picture
    assert _cache_is_fresh(panel, cached, 2), "a cache newer than its panel is usable"

    time.sleep(0.01)
    Image.new("RGB", (40, 30), (99, 99, 99)).save(panel)
    os.utime(panel, None)
    assert not _cache_is_fresh(panel, cached, 2), "a re-split panel must invalidate it"


def test_a_cached_upscale_of_the_wrong_size_is_rejected(tmp_path):
    """The second, mtime-independent check: a 2x cache is exactly twice its source, so a
    re-split that produced an older-but-different panel is still caught."""
    from PIL import Image

    from manhwa2vid.video.upscale import _cache_is_fresh

    panel = tmp_path / "p0001_01.png"
    Image.new("RGB", (40, 30)).save(panel)
    for size, ok in [((80, 60), True), ((123, 45), False), ((40, 30), False)]:
        cached = tmp_path / f"c{size[0]}.png"
        Image.new("RGB", size).save(cached)
        assert _cache_is_fresh(panel, cached, 2) is ok, f"size {size}"


def test_stale_cache_entries_are_dropped_from_the_mapping(tmp_path, monkeypatch):
    """With the model unavailable, a stale entry must be ABSENT rather than served."""
    import os
    import time

    from PIL import Image

    import manhwa2vid.video.upscale as up

    monkeypatch.setenv("MANHWA2VID_UPSCALE", "1")
    monkeypatch.setattr(up, "_load_model", lambda: (_ for _ in ()).throw(RuntimeError("no weights")))
    panels = tmp_path / "panels"
    panels.mkdir()
    panel = panels / "p0001_01.png"
    Image.new("RGB", (40, 30)).save(panel)
    cache = up.upscaled_panels_dir(tmp_path)
    cache.mkdir()
    Image.new("RGB", (80, 60)).save(cache / "p0001_01.png")
    time.sleep(0.01)
    Image.new("RGB", (40, 30), (9, 9, 9)).save(panel)
    os.utime(panel, None)
    assert up.upscale_panels([panel], tmp_path, {}) == {}, "stale cache was served"
