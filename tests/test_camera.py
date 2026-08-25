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


def test_budget_keeps_key_panels_when_salience_is_unavailable():
    """key_panel_ids were silently discarded whenever scene cards were absent.

    tts/engine.py wraps salience loading in a bare except, so any project without
    enriched cards fell to this branch — a blind positional stride that ignores the
    writer's "this panel is load-bearing" marking entirely. The story-first
    architecture has no scene cards at all, making this the only path.
    """
    from manhwa2vid.video.timeline import budget_panels_for_beat

    panels = [f"p0001_{i:02d}" for i in range(1, 11)]
    key = ["p0001_09"]  # late panel a stride would never pick
    # 6s of audio at a 2s floor affords 3 panels.
    kept = budget_panels_for_beat(panels, 6.0, 2.0, key)
    assert len(kept) == 3
    assert "p0001_09" in kept
    assert kept == [p for p in panels if p in kept], "beat order must be preserved"

    # Without keys, behaviour is the original stride.
    assert budget_panels_for_beat(panels, 6.0, 2.0) == ["p0001_01", "p0001_05", "p0001_10"]
    # A single affordable slot goes to the key panel, not blindly to the first.
    assert budget_panels_for_beat(panels, 2.0, 2.0, key) == ["p0001_09"]
    # No budget pressure means nothing is dropped.
    assert budget_panels_for_beat(panels, 100.0, 2.0, key) == panels


def test_budget_preserves_narration_order_not_reading_order():
    """A cold open lists late panels first; budgeting must not re-sort them."""
    from manhwa2vid.video.timeline import budget_panels_for_beat

    out_of_reading_order = ["p0020_01", "p0020_02", "p0001_01", "p0001_02"]
    kept = budget_panels_for_beat(out_of_reading_order, 4.0, 2.0, ["p0001_01"])
    assert kept == [p for p in out_of_reading_order if p in kept]
    assert kept[0].startswith("p0020"), "page-20 panels must stay ahead of page-1 panels"


def test_weighted_split_follows_narration_and_keeps_av_lock():
    """Dwell must follow what the narration is saying, not a metronome.

    Before weights existed, 16/16 FP beats and 34/38 SL beats gave every panel a
    byte-identical dwell — the picture never lingered on what was being said.
    """
    from manhwa2vid.video.timeline import panel_weights_from_segments, split_beat_durations

    segments = [
        {"text": "Long sentence about the fight.", "seconds": 6.0},
        {"text": "Short.", "seconds": 1.0},
        {"text": "Another long one describing the aftermath.", "seconds": 5.0},
    ]
    weights = panel_weights_from_segments(segments, 6)
    durations = split_beat_durations(12.0, 6, min_sec=1.5, max_sec=5.0, weights=weights)
    assert abs(sum(durations) - 12.0) < 1e-6, "A/V lock is non-negotiable"
    assert len(set(round(d, 2) for d in durations)) > 1, "dwell must vary with the narration"
    # The short sentence's panel is the shortest on screen (floored at min_sec).
    assert min(durations) == durations[3]

    # No sidecar -> None -> today's even split, so old projects behave identically.
    assert panel_weights_from_segments([], 6) is None
    assert split_beat_durations(12.0, 6, min_sec=1.5, max_sec=5.0) == [2.0] * 6
    # A single sentence has nothing to weight; even split IS the right answer.
    assert panel_weights_from_segments([{"seconds": 5.0}], 4) is None


def test_tiny_sentence_rides_its_boundary_panel():
    """A sentence too short to own a panel must not vanish from the weight mass."""
    from manhwa2vid.video.timeline import panel_weights_from_segments

    segments = [
        {"seconds": 10.0},
        {"seconds": 0.2},   # rounds to an empty panel run
        {"seconds": 10.0},
    ]
    weights = panel_weights_from_segments(segments, 4)
    assert weights is not None
    assert abs(sum(weights) - 20.2) < 1e-6, "no seconds may be lost"


def test_crop_to_content_fills_the_frame_with_art():
    """Margins must not eat the screen: measured, ~48 shown panels carried their art in
    under 60% of their area and the whole PNG — margins included — was fit to frame."""
    from PIL import Image

    from manhwa2vid.video.effects import crop_to_content

    # Art in the center 40% of a mostly-white image.
    img = Image.new("RGB", (800, 600), (255, 255, 255))
    for x in range(240, 560):
        for y in range(180, 420):
            img.putpixel((x, y), (30, 30, 30))
    cropped = crop_to_content(img)
    assert cropped.width < 800 * 0.6 and cropped.height < 600 * 0.6
    # Pure-art image is untouched.
    art = Image.new("RGB", (400, 300), (40, 40, 40))
    assert crop_to_content(art).size == (400, 300)
    # All-white image cannot crash.
    blank = Image.new("RGB", (100, 100), (255, 255, 255))
    assert crop_to_content(blank).size == (100, 100)


def test_visually_empty_rule_matches_the_measured_fixtures():
    """Calibrated on the 34 real offenders; these synthetic twins pin the shape.

    The global blank gate (ink<=0.30) cannot catch these — a small dense blob clears a
    global threshold while the frame is visually nothing.
    """
    import numpy as np

    from manhwa2vid.panels.split import is_visually_empty

    white = np.full((300, 800), 255, dtype=np.uint8)

    # Small dense text blob in a white field (the p0009_02 / p0076_02 shape).
    blob = white.copy(); blob[130:160, 300:500] = 0
    assert is_visually_empty(blob)

    # Big but faint content box (the p0020_03 / p0146_01 shape): a large sparse scatter.
    sparse = white.copy(); sparse[::4, ::4] = 200
    assert is_visually_empty(sparse)

    # Real art: >30% of the frame is genuinely dark.
    art = white.copy(); art[30:270, 100:700] = 60
    assert not is_visually_empty(art)

    # A dark panel is never empty regardless of box shape.
    dark = np.full((300, 800), 40, dtype=np.uint8)
    assert not is_visually_empty(dark)
