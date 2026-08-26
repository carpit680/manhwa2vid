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


def test_multi_sentence_kokoro_chunks_are_subdivided():
    """Kokoro chunks on an internal token limit, not on sentences: one measured chunk
    carried nine sentences in 22 seconds, and single-chunk beats got no weighting at all
    (6 of 16 FP beats stayed uniform). Chunk-boundary seconds are exact; within a chunk,
    word count prorates."""
    from manhwa2vid.video.timeline import panel_weights_from_segments

    one_chunk = [{"text": "A short one. A much longer sentence that goes on for many more words than the first.", "seconds": 10.0}]
    weights = panel_weights_from_segments(one_chunk, 4)
    assert weights is not None, "a single multi-sentence chunk must still produce weights"
    assert len(set(round(w, 2) for w in weights)) > 1
    assert abs(sum(weights) - 10.0) < 1e-6


# --- fill-frame camera (2026-08-26: whole-panel fitting wasted half the screen) -------

def _art_panel(tmp_path: Path, w: int, h: int, name: str = "panel.png") -> Path:
    import numpy as np
    from PIL import Image as PILImage

    rng = np.random.default_rng(7)
    arr = rng.integers(60, 200, (h, w, 3), dtype=np.uint8)
    p = tmp_path / name
    PILImage.fromarray(arr).save(p)
    return p


def test_fill_frame_fills_the_frame_exactly(tmp_path: Path) -> None:
    from manhwa2vid.video.effects import render_fill_frame_frames

    p = _art_panel(tmp_path, 720, 1600)
    frames = render_fill_frame_frames(p, 480, 270, 60, {}, seed="t")
    assert len(frames) == 60
    assert all(f.size == (480, 270) for f in frames)


def test_fill_frame_tall_panel_pans_downward(tmp_path: Path) -> None:
    """A tall panel's first and last frames show different content, and the pan runs
    in reading order (top first)."""
    import numpy as np
    from PIL import Image as PILImage
    from manhwa2vid.video.effects import render_fill_frame_frames

    arr = np.zeros((1600, 720, 3), dtype=np.uint8)
    arr[:800] = (200, 60, 60)    # top half red-ish
    arr[800:] = (60, 60, 200)    # bottom half blue-ish
    rng = np.random.default_rng(3)
    arr = np.clip(arr.astype(int) + rng.integers(-40, 40, arr.shape), 0, 255).astype(np.uint8)
    p = tmp_path / "tall.png"
    PILImage.fromarray(arr).save(p)

    frames = render_fill_frame_frames(p, 480, 270, 120, {}, seed="t")
    first = np.asarray(frames[0]).astype(float)
    last = np.asarray(frames[-1]).astype(float)
    assert first[..., 0].mean() > first[..., 2].mean(), "starts at the TOP (red)"
    assert last[..., 2].mean() > last[..., 0].mean(), "ends toward the BOTTOM (blue)"


def test_fill_frame_long_dwell_gets_a_reframe_cut(tmp_path: Path) -> None:
    """A dwell over video.max_dwell_seconds becomes two shots — a hard discontinuity —
    instead of the audit's 14-18s frozen holds."""
    import numpy as np
    from PIL import Image as PILImage
    from manhwa2vid.video.effects import render_fill_frame_frames

    # Structured art (smooth bands), NOT noise: noise decorrelates adjacent frames so a
    # pan step and a hard cut measure the same. Real art is locally smooth.
    y = np.arange(2400)[:, None]
    x = np.arange(720)[None, :]
    arr = np.stack(
        [
            128 + 100 * np.sin(y / 90.0 + x / 240.0),
            128 + 100 * np.sin(y / 55.0) + 0.0 * x,
            128 + 100 * np.cos(y / 130.0 - x / 180.0),
        ],
        axis=-1,
    ).clip(0, 255).astype(np.uint8)
    p = tmp_path / "bands.png"
    PILImage.fromarray(arr).save(p)
    config = {"video": {"fps": 30, "max_dwell_seconds": 4.0}}
    frames = render_fill_frame_frames(p, 480, 270, 300, config, seed="t")  # 10s
    diffs = [
        float(np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)).mean())
        for a, b in zip(frames, frames[1:])
    ]
    peak = max(diffs)
    typical = sorted(diffs)[len(diffs) // 2]
    assert peak > max(6.0, 4 * typical), "no visible re-frame cut found in a long dwell"


def test_fill_frame_resting_frame_does_not_clip_a_bubble(tmp_path: Path) -> None:
    import numpy as np
    from PIL import Image as PILImage
    from manhwa2vid.video.effects import _bubble_boxes, _snap_offset

    # bubble occupying rows 500-700 of a 720x1600 panel
    arr = np.random.default_rng(5).integers(60, 200, (1600, 720, 3), dtype=np.uint8)
    arr[500:700, 100:500] = 250
    gray = np.asarray(PILImage.fromarray(arr).convert("L"))
    bubbles = _bubble_boxes(gray)
    assert bubbles, "fixture bubble must be detected"
    # a 405-tall window resting at offset 400 would slice the bubble at row 500+405=805? no:
    # window [400, 805) contains rows 500-700 fully -> ok; offset 550 slices it.
    snapped = _snap_offset(550, 405, bubbles, "y", 1195)
    lo, hi = snapped, snapped + 405
    bx, by, bw, bh = bubbles[0]
    assert not (by < lo < by + bh or by < hi < by + bh), "bubble still edge-clipped"


def test_tiny_panel_falls_back_to_letterbox(tmp_path: Path) -> None:
    """A panel too small to fill the frame legibly letterboxes instead of smearing."""
    from manhwa2vid.models import Panel, PanelBBox
    from manhwa2vid.video.effects import render_panel_motion_frames

    p = _art_panel(tmp_path, 200, 150, "tiny.png")
    panel = Panel(
        id="p0001_01", page_num=1,
        bbox=PanelBBox(x=0, y=0, width=200, height=150),
        image_path=str(p),
    )
    frames = render_panel_motion_frames(p, panel, 960, 540, 30, {})
    assert len(frames) == 30 and frames[0].size == (960, 540)
