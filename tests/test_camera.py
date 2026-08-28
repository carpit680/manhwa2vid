"""Camera mode and motion frame tests."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from manhwa2vid.models import Panel, PanelBBox
from manhwa2vid.video.effects import cosine_ease, render_vertical_scroll_frames


def _panel(**kwargs) -> Panel:
    defaults = {
        "id": "p0001_01",
        "page_num": 1,
        "bbox": PanelBBox(x=0, y=0, width=1080, height=4500),
        "image_path": "panels/p0001_01.png",
        "split_method": "strip",
        "aspect_ratio": 4.17,
    }
    defaults.update(kwargs)
    return Panel(**defaults)


def test_cosine_ease_endpoints() -> None:
    assert cosine_ease(0.0) == 0.0
    assert cosine_ease(1.0) == 1.0








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


def test_fill_frame_drifts_it_does_not_traverse(tmp_path: Path) -> None:
    """The camera DRIFTS a capped amount; it never scrolls down a tall panel.

    Measured on the reference channel's own edit: 0% of its shots travel more than 0.25
    frame-heights (p90 0.201). The first fill-frame camera panned on 93% of shots, 47%
    of them past 0.25 — the user's report was that the whole video read as scrolling.
    """
    import numpy as np
    from PIL import Image as PILImage
    from manhwa2vid.video.effects import render_fill_frame_frames

    y = np.arange(3000)[:, None]
    x = np.arange(720)[None, :]
    arr = np.stack(
        [
            128 + 100 * np.sin(y / 90.0 + x / 240.0),
            128 + 100 * np.sin(y / 55.0) + 0.0 * x,
            128 + 100 * np.cos(y / 130.0 - x / 180.0),
        ],
        axis=-1,
    ).clip(0, 255).astype(np.uint8)
    p = tmp_path / "verytall.png"
    PILImage.fromarray(arr).save(p)

    config = {"video": {"fps": 30, "max_pan_frame_fraction": 0.20, "max_dwell_seconds": 99}}
    frames = render_fill_frame_frames(p, 480, 270, 150, config, seed="t")  # 5s
    first = np.asarray(frames[0].convert("L")).astype(np.float32)
    last = np.asarray(frames[-1].convert("L")).astype(np.float32)
    import cv2

    win = cv2.createHanningWindow((first.shape[1], first.shape[0]), cv2.CV_32F)
    (_dx, dy), _ = cv2.phaseCorrelate(first, last, win)
    travel = abs(dy) / first.shape[0]
    assert travel <= 0.30, f"camera traversed {travel:.2f} frame-heights — that is scrolling"


def test_short_shots_hold_still(tmp_path: Path) -> None:
    """Fast AND moving is the jarring combination: below video.pan_min_seconds a shot
    does not drift at all."""
    import numpy as np
    import cv2
    from PIL import Image as PILImage
    from manhwa2vid.video.effects import render_fill_frame_frames

    # Structured bands, not noise: phase correlation needs a trackable peak (measured
    # response 0.04 on pure noise — the reading is meaningless there).
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
    p = tmp_path / "tallbands.png"
    PILImage.fromarray(arr).save(p)
    config = {"video": {"fps": 30, "pan_min_seconds": 1.8, "max_dwell_seconds": 99}}
    frames = render_fill_frame_frames(p, 480, 270, 24, config, seed="t")  # 0.8s
    a = np.asarray(frames[0].convert("L")).astype(np.float32)
    b = np.asarray(frames[-1].convert("L")).astype(np.float32)
    win = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
    (_dx, dy), _ = cv2.phaseCorrelate(a, b, win)
    assert abs(dy) / a.shape[0] < 0.05, "a sub-2s shot must not pan"


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
    """A resting window must not slice a bubble at the frame edge.

    The fixture now contains real LETTERING, because the camera's bubble finder is no
    longer a brightness test: a blank white rectangle is not a bubble, and the previous
    fixture (a plain 250-valued block) was exactly the "large pale region" the old
    detector confused with one.
    """
    import cv2
    import numpy as np
    from manhwa2vid.video.effects import _text_boxes, _snap_offset

    # a bubble with type in it, occupying rows 500-700 of a 720x1600 panel
    arr = np.random.default_rng(5).integers(60, 200, (1600, 720, 3), dtype=np.uint8)
    cv2.ellipse(arr, (300, 600), (200, 100), 0, 0, 360, (250, 250, 250), -1)
    for i in range(6):
        cv2.putText(arr, "A", (170 + i * 45, 615), cv2.FONT_HERSHEY_SIMPLEX,
                    1.1, (0, 0, 0), 3)

    bubbles = _text_boxes(arr)
    assert bubbles, "fixture bubble must be detected"
    by, bh = bubbles[0][1], bubbles[0][3]
    snapped = _snap_offset(by + bh // 2, 405, bubbles, "y", 1195)
    lo, hi = snapped, snapped + 405
    assert not (by < lo < by + bh or by < hi < by + bh), "bubble still edge-clipped"


def test_a_blank_pale_block_is_not_treated_as_a_bubble(tmp_path: Path) -> None:
    """The regression that motivated the swap: the old brightness test called any large
    pale region a bubble, so the camera steered away from walls, snow and bedding."""
    import numpy as np
    from manhwa2vid.video.effects import _text_boxes

    import cv2

    # Smoothed, not per-pixel noise: drawn art has strokes and flats, and adaptive
    # thresholding on white noise invents glyph-sized specks that no real panel has.
    rng = np.random.default_rng(5).integers(60, 200, (1600, 720, 3), dtype=np.uint8)
    arr = cv2.blur(rng, (25, 25))
    arr[500:700, 100:500] = 250          # a plain bright block: a wall, not a bubble
    assert _text_boxes(arr) == []


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


def test_no_title_badge_or_end_card_is_added() -> None:
    """The video opens on artwork and ends on artwork — no furniture at either end.

    A 3s chapter badge and a 4.5s black end card were added as "production furniture"
    after an audit found the videos starting and stopping bluntly. On review they read
    as bolted-on: the closing ask now lives INSIDE the narration (`script/outro.py`), so
    the card only repeated in text what the narrator had just said. Pinned as absence
    because a removed feature is the easiest kind to reintroduce by habit.
    """
    import inspect

    from manhwa2vid.video import effects, render

    assert not hasattr(effects, "add_chapter_badge")
    assert not hasattr(effects, "make_end_card")
    src = inspect.getsource(render)
    assert "badge" not in src and "end_card" not in src, "render grew furniture again"


def test_tall_panel_is_shown_whole_with_bars_not_cropped(tmp_path: Path) -> None:
    """Whole-panel-with-blurred-bars is the DEFAULT, not a fallback.

    Measured on the reference channel: its sharp centre band is 0.50 of frame width at
    the median, bars present on 70% of frames. Filling the frame on every shot measured
    0.84 — further from the reference than the reference is. It also answers the
    scrolling complaint: a whole panel has nothing left to pan across.
    """
    import numpy as np
    from manhwa2vid.models import Panel, PanelBBox
    from manhwa2vid.video.effects import render_panel_motion_frames

    p = _art_panel(tmp_path, 700, 900, "portrait.png")   # aspect 1.29 -> 0.44 of width
    panel = Panel(id="p0001_01", page_num=1,
                  bbox=PanelBBox(x=0, y=0, width=700, height=900), image_path=str(p))
    frames = render_panel_motion_frames(p, panel, 480, 270, 30, {}, seed_salt=0)
    f = np.asarray(frames[len(frames) // 2].convert("L")).astype(np.float32)
    # the sharp band must be a CENTRE STRIPE, not the whole width
    d2 = np.abs(np.diff(f, n=2, axis=1)).mean(axis=0)
    live = np.flatnonzero(d2 > max(d2.max() * 0.25, 0.5))
    frac = (live[-1] - live[0] + 1) / f.shape[1]
    assert 0.25 <= frac <= 0.80, f"expected blurred bars, sharp band was {frac:.2f} of width"


def test_frame_shaped_panel_still_fills_the_frame(tmp_path: Path) -> None:
    """A panel that already fits 16:9 gains nothing from bars."""
    import numpy as np
    from manhwa2vid.models import Panel, PanelBBox
    from manhwa2vid.video.effects import render_panel_motion_frames

    p = _art_panel(tmp_path, 960, 540, "wide.png")
    panel = Panel(id="p0001_02", page_num=1,
                  bbox=PanelBBox(x=0, y=0, width=960, height=540), image_path=str(p))
    frames = render_panel_motion_frames(p, panel, 480, 270, 30, {}, seed_salt=0)
    f = np.asarray(frames[0].convert("L")).astype(np.float32)
    d2 = np.abs(np.diff(f, n=2, axis=1)).mean(axis=0)
    live = np.flatnonzero(d2 > max(d2.max() * 0.25, 0.5))
    assert (live[-1] - live[0] + 1) / f.shape[1] > 0.85


def test_extreme_strip_does_not_letterbox_into_a_ribbon(tmp_path: Path) -> None:
    """A 4:1 strip shown whole would be 14% of frame width — unreadable. Those still
    go to the fill camera, which covers them with cuts rather than a long scroll."""
    from manhwa2vid.models import Panel, PanelBBox
    from manhwa2vid.video.effects import render_panel_motion_frames

    p = _art_panel(tmp_path, 700, 2800, "strip.png")
    panel = Panel(id="p0001_03", page_num=1,
                  bbox=PanelBBox(x=0, y=0, width=700, height=2800), image_path=str(p))
    frames = render_panel_motion_frames(p, panel, 480, 270, 30, {}, seed_salt=0)
    assert len(frames) == 30 and frames[0].size == (480, 270)


def test_only_true_strips_get_the_scrolling_camera(tmp_path: Path) -> None:
    """Routing is `split_method == "strip"`, nothing else.

    It used to go through choose_camera_mode(), which was inert: it returned "scroll"
    whenever split_method was "strip" and the caller then AND-ed with that same
    condition, so its aspect threshold and Panel.camera_hint could not change any
    decision. This pins the rule that actually runs — a tall GUTTER panel must reach the
    letterbox/fill camera, not the crawl.
    """
    import numpy as np
    from manhwa2vid.models import Panel, PanelBBox
    from manhwa2vid.video.effects import render_panel_motion_frames

    tall = _art_panel(tmp_path, 700, 2800, "tall.png")

    strip = Panel(id="p0001_01", page_num=1, split_method="strip",
                  bbox=PanelBBox(x=0, y=0, width=700, height=2800), image_path=str(tall))
    gutter = Panel(id="p0001_02", page_num=1, split_method="gutter",
                   bbox=PanelBBox(x=0, y=0, width=700, height=2800), image_path=str(tall))

    cfg = {"video": {"fps": 30, "motion_supersample": 1}}
    a = render_panel_motion_frames(tall, strip, 480, 270, 30, cfg, seed_salt=0)
    b = render_panel_motion_frames(tall, gutter, 480, 270, 30, cfg, seed_salt=0)
    assert len(a) == len(b) == 30
    # Same image, same seed: identical output would mean the split_method was ignored.
    assert not np.array_equal(np.asarray(a[0]), np.asarray(b[0])), (
        "strip and gutter panels took the same camera path"
    )


def test_opening_framing_prefers_art_over_contrast(tmp_path: Path) -> None:
    """Gradient energy cannot tell a face from a wall of lettering — the spiky edges of a
    speech bubble are exactly the contrast it rewards. Solo Leveling opened on
    "E-RANK HUNTER." on black at t=6s because of it, and the panel behind that frame is
    NOT text-dominant (0.231), so no panel-level rule could have caught it: the defect is
    which window the camera chose.

    The fixture has to earn that: a HIGH-contrast starburst bubble against LOW-contrast
    art. An earlier version used blurred noise for the art, which already beats a flat
    ellipse on gradient energy, so both cameras picked the same window and the test proved
    nothing. Measured on the real panel p0002_03: lettering 0.210 -> 0.031.
    """
    import cv2
    import numpy as np
    from PIL import Image as PILImage

    from manhwa2vid.panels.regions import _text_and_content_masks, _text_norm
    from manhwa2vid.video.effects import render_fill_frame_frames

    arr = np.zeros((1600, 720, 3), np.uint8)
    # Top: a jagged white bubble full of lettering — maximal local contrast.
    pts = []
    for k in range(40):
        ang = 2 * np.pi * k / 40
        r = 260 if k % 2 == 0 else 170
        pts.append([int(360 + r * np.cos(ang)), int(300 + r * 0.7 * np.sin(ang))])
    cv2.fillPoly(arr, [np.array(pts, np.int32)], (255, 255, 255))
    for i in range(6):
        cv2.putText(arr, "A", (185 + i * 62, 320), cv2.FONT_HERSHEY_SIMPLEX,
                    1.5, (0, 0, 0), 4)
    # Bottom: smooth art — plenty of CONTENT, very little gradient energy.
    grad = np.linspace(60, 200, 600, dtype=np.uint8)
    arr[900:1500, 60:660] = np.repeat(grad[:, None], 600, axis=1)[:, :, None]
    cv2.circle(arr, (360, 1200), 190, (120, 90, 70), -1)

    path = tmp_path / "panel.png"
    PILImage.fromarray(arr).save(path)

    def lettering_of(frames):
        g = cv2.cvtColor(np.asarray(frames[2]), cv2.COLOR_RGB2GRAY)
        text, _content, _c = _text_and_content_masks(_text_norm(g))
        return float(text.mean())

    cfg = {"video": {"fps": 30}}
    normal = render_fill_frame_frames(path, 1920, 1080, 6, cfg, seed="s")
    art = render_fill_frame_frames(path, 1920, 1080, 6, cfg, seed="s", prefer_art=True)
    assert lettering_of(art) < lettering_of(normal), (
        "the opening camera must move off the lettering, not toward it"
    )
