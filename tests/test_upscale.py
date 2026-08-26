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
