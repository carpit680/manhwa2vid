"""Camera mode and motion frame tests."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from manhwa2vid.models import Panel, PanelBBox
from manhwa2vid.video.effects import choose_camera_mode, cosine_ease, render_vertical_scroll_frames


def _panel(**kwargs) -> Panel:
    defaults = {
        "id": "p0001_01",
        "page_num": 1,
        "bbox": PanelBBox(x=0, y=0, width=1080, height=4500),
        "image_path": "panels/p0001_01.png",
        "split_method": "strip",
        "aspect_ratio": 4.17,
        "camera_hint": "auto",
    }
    defaults.update(kwargs)
    return Panel(**defaults)


def test_cosine_ease_endpoints() -> None:
    assert cosine_ease(0.0) == 0.0
    assert cosine_ease(1.0) == 1.0


def test_choose_camera_mode_strip() -> None:
    panel = _panel(split_method="strip", aspect_ratio=4.0)
    assert choose_camera_mode(panel, {"video": {"strip_scroll_aspect": 2.0}}) == "scroll"


def test_choose_camera_mode_tall_aspect() -> None:
    panel = _panel(split_method="gutter", aspect_ratio=2.5)
    assert choose_camera_mode(panel, {"video": {"strip_scroll_aspect": 2.0}}) == "scroll"


def test_choose_camera_mode_normal() -> None:
    panel = _panel(split_method="gutter", aspect_ratio=1.2, camera_hint="auto")
    assert choose_camera_mode(panel, {"video": {"strip_scroll_aspect": 2.0}}) == "ken_burns"


def test_vertical_scroll_produces_frames(tmp_path: Path) -> None:
    img = Image.new("RGB", (1080, 3000), color=(200, 100, 50))
    panel_path = tmp_path / "tall.png"
    img.save(panel_path)

    frames = render_vertical_scroll_frames(
        panel_path,
        width=320,
        height=180,
        num_frames=10,
        config={"video": {"motion_supersample": 2}},
    )
    assert len(frames) == 10
    assert frames[0].size == (320, 180)
    assert frames[-1].size == (320, 180)
