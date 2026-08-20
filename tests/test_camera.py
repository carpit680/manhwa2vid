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


def test_select_panels_importance_first():
    """Key panels are always shown, even past the pace budget; fills come by salience;
    reading order is preserved; a beat never empties."""
    from manhwa2vid.video.timeline import select_panels_for_beat

    panels = [f"p0001_{i:02d}" for i in range(1, 11)]  # 10 panels
    salience = {p: 0.0 for p in panels}
    salience["p0001_05"] = 3.0  # dialogue panel

    # 5s audio at 2.5s target -> 2 affordable; 4 keys must ALL survive anyway
    keys = ["p0001_02", "p0001_04", "p0001_07", "p0001_09"]
    out = select_panels_for_beat(panels, keys, salience, 5.0, 2.5, 1.0)
    assert [p for p in out if p in keys] == keys
    assert out == sorted(out, key=panels.index)  # reading order

    # no keys: best-salience panel is chosen, plus budget fill
    out2 = select_panels_for_beat(panels, [], salience, 5.0, 2.5, 1.0)
    assert "p0001_05" in out2
    assert 1 <= len(out2) <= 2

    # never empty, even with absurd budgets
    out3 = select_panels_for_beat(panels, [], salience, 0.4, 2.5, 1.0)
    assert len(out3) >= 1


def test_select_panels_keeps_the_last_panel_when_asked():
    """The closer's final panel carries the chapter's reveal by construction."""
    from manhwa2vid.video.timeline import select_panels_for_beat

    panels = [f"p0002_{i:02d}" for i in range(1, 7)]
    out = select_panels_for_beat(panels, [], {}, 5.0, 2.5, 1.0, keep_last=True)
    assert panels[-1] in out


def test_panel_salience_prefers_dialogue_then_people():
    from manhwa2vid.models import SceneCard
    from manhwa2vid.video.timeline import panel_salience

    cards = [
        SceneCard(panel_ids=["p1"], source_text='A: "HI."', action=""),
        SceneCard(panel_ids=["p2"], source_text="", action="scenery"),
    ]
    attribution = [
        {"panel_id": "p1", "people": [{"ref": "a"}]},
        {"panel_id": "p2", "people": []},
    ]
    s = panel_salience(cards, attribution)
    assert s["p1"] > s["p2"]
