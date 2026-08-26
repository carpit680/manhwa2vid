"""Collage region splitting — the 2D answer to gutter-only panel detection.

Every fixture reproduces a geometry measured on real pages in the 2026-08-26 defect
audit. The failure this guards: SL page 2's second gutter band (720x1633) contained
THREE story panels plus three speech bubbles, no full-width uniform row between any of
them — gutter detection found one cut in the whole page and the video opened on six
seconds of a speech bubble crawling past on black.
"""

from __future__ import annotations

import numpy as np
import pytest

from manhwa2vid.panels.regions import (
    absorb_bubble_regions,
    background_level,
    bubble_fraction,
    detect_content_regions,
    merge_small_regions,
    split_collage_regions,
)


def _canvas(h: int, w: int, value: int) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


def _paint_art(img: np.ndarray, x: int, y: int, w: int, h: int) -> None:
    """A textured mid-tone block — art has variance, unlike background or bubbles."""
    rng = np.random.default_rng(42)
    img[y : y + h, x : x + w] = rng.integers(60, 200, (h, w, 3), dtype=np.uint8)


def _paint_bubble(img: np.ndarray, x: int, y: int, w: int, h: int) -> None:
    """A solid near-white blob with a few dark 'text' rows."""
    img[y : y + h, x : x + w] = 250
    img[y + h // 3 : y + h // 3 + 4, x + 8 : x + w - 8] = 20


# --- the measured geometries ---------------------------------------------------------

def test_staggered_insets_on_black_split_and_bubble_absorbed():
    """SL p0002_02: bubble + two insets staggered diagonally on black -> 2 panels,
    the bubble folded into the nearest inset, reading order kept."""
    img = _canvas(1600, 720, 0)
    _paint_bubble(img, 75, 185, 390, 230)   # name bubble
    _paint_art(img, 360, 480, 330, 560)     # hand inset (upper right)
    _paint_art(img, 30, 903, 300, 600)      # blade inset (lower left; y-overlaps the
    # hand like the real page — the insets stagger diagonally and never touch

    regions = split_collage_regions(img, min_height=120)
    assert regions is not None and len(regions) == 2
    # first region contains the bubble AND the hand inset (union)
    x, y, w, h = regions[0]
    assert y <= 200 and y + h >= 1000, "bubble absorbed upward into the first art region"
    # regions come in reading order
    assert regions[0][1] < regions[1][1]


def test_two_scenes_joined_diagonally_split():
    """FP p0004_03: two full-width scenes overlapping in y but disconnected -> 2."""
    img = _canvas(2800, 800, 0)
    _paint_art(img, 0, 30, 800, 1000)
    _paint_art(img, 0, 1100, 800, 1650)

    regions = split_collage_regions(img, min_height=120)
    assert regions is not None and len(regions) == 2


def test_continuous_strip_is_left_whole():
    """FP p0005_14: one connected illustration -> None (caller keeps the strip)."""
    img = _canvas(2000, 800, 0)
    _paint_art(img, 0, 0, 800, 2000)
    assert split_collage_regions(img, min_height=120) is None


def test_side_by_side_panels_split():
    """Two panels separated by a VERTICAL gutter — invisible to row-based splitting."""
    img = _canvas(600, 800, 255)
    _paint_art(img, 20, 50, 350, 500)
    _paint_art(img, 430, 50, 350, 500)
    regions = split_collage_regions(img, min_height=120)
    assert regions is not None and len(regions) == 2
    assert regions[0][0] < regions[1][0]


# --- component behaviours ------------------------------------------------------------

def test_background_level_reads_the_border_not_the_content():
    img = _canvas(400, 400, 0)
    _paint_art(img, 50, 50, 300, 300)  # bright content, dark border
    gray = img.mean(axis=2).astype(np.uint8)
    assert background_level(gray) == 0

    img_white = _canvas(400, 400, 255)
    _paint_art(img_white, 50, 50, 300, 300)
    gray_w = img_white.mean(axis=2).astype(np.uint8)
    assert gray_w[0, 0] == 255 and background_level(gray_w) == 255


def test_bubble_fraction_separates_bubbles_from_art():
    bubble = _canvas(200, 300, 0)
    _paint_bubble(bubble, 0, 0, 300, 200)
    art = _canvas(200, 300, 0)
    _paint_art(art, 0, 0, 300, 200)
    assert bubble_fraction(bubble[0:200, 0:300]) > 0.45
    assert bubble_fraction(art[0:200, 0:300]) < 0.45


def test_all_bubbles_page_stays_whole():
    """A band that is ONLY bubbles must not vanish or split — it stays one panel."""
    img = _canvas(800, 720, 0)
    _paint_bubble(img, 100, 100, 400, 200)
    _paint_bubble(img, 150, 450, 400, 200)
    assert split_collage_regions(img, min_height=120) is None


def test_bare_bubble_never_becomes_its_own_panel():
    img = _canvas(1200, 720, 0)
    _paint_bubble(img, 60, 60, 350, 200)
    _paint_art(img, 100, 400, 500, 600)
    regions = split_collage_regions(img, min_height=120)
    # bubble + one art region -> after absorption only ONE region remains -> no split
    assert regions is None


def test_small_stray_folded_not_kept():
    """A tiny SFX scrap under min_height folds into a neighbour instead of becoming
    a sub-minimum panel."""
    img = _canvas(1600, 720, 0)
    _paint_art(img, 50, 50, 600, 700)
    _paint_art(img, 200, 850, 100, 60)   # stray scrap, below min_height
    _paint_art(img, 50, 1000, 600, 550)
    regions = split_collage_regions(img, min_height=120)
    assert regions is not None
    assert all(h >= 120 for _x, _y, _w, h in regions)


def test_narrow_stray_folded_too():
    """Width matters as much as height: FP page 5 shipped a 58x104 'panel' when only
    height was enforced."""
    img = _canvas(1600, 720, 0)
    _paint_art(img, 50, 50, 600, 700)
    _paint_art(img, 600, 850, 58, 300)   # tall enough, far too narrow
    _paint_art(img, 50, 1250, 600, 300)
    regions = split_collage_regions(img, min_height=120)
    assert regions is not None
    assert all(w >= 120 and h >= 120 for _x, _y, w, h in regions)


def test_merge_small_regions_caps_count_and_keeps_order():
    regions = [(0, 0, 100, 100), (0, 200, 10, 10), (0, 400, 100, 100)]
    merged = merge_small_regions(regions, 2)
    assert len(merged) == 2
    assert merged[0][1] <= merged[1][1]


def test_absorb_requires_art_to_exist():
    img = _canvas(600, 600, 0)
    _paint_bubble(img, 50, 50, 300, 150)
    _paint_bubble(img, 50, 350, 300, 150)
    regions = detect_content_regions(img)
    assert absorb_bubble_regions(img, regions) == regions


def test_disabled_flag_passes_bands_through():
    """panels.regions.enabled: false keeps the old one-band-one-panel behaviour."""
    from manhwa2vid.panels.split import _expand_region_bboxes

    img = _canvas(1600, 720, 0)
    _paint_bubble(img, 75, 185, 390, 230)
    _paint_art(img, 308, 480, 380, 560)
    _paint_art(img, 30, 903, 500, 600)
    config = {"panels": {"regions": {"enabled": False}}}
    boxes = _expand_region_bboxes(img, [(0, 1600)], config)
    assert boxes == [(0, 0, 720, 1600, False)]


def test_expand_region_bboxes_maps_band_offsets_to_page_coords():
    from manhwa2vid.panels.split import _expand_region_bboxes

    img = _canvas(2000, 720, 0)
    # band 1 (rows 0-400): continuous
    _paint_art(img, 0, 0, 720, 400)
    # band 2 (rows 500-2000): collage of two insets
    _paint_art(img, 30, 550, 400, 600)
    _paint_art(img, 300, 1300, 400, 600)
    boxes = _expand_region_bboxes(img, [(0, 400), (500, 1500)], {})
    assert boxes[0] == (0, 0, 720, 400, False)
    collage = [b for b in boxes if b[4]]
    assert len(collage) == 2
    assert all(y >= 500 for _x, y, _w, _h, _f in collage), "region y is in PAGE coords"


def test_text_only_panel_detector():
    """Bare bubbles / SFX-on-white are text-only; art panels are not — validated by eye
    on the 63 FP panels the rule selects (all bubbles/SFX/blank, no art)."""
    from manhwa2vid.panels.regions import is_text_only_panel

    bubble = _canvas(400, 700, 0)
    _paint_bubble(bubble, 150, 100, 400, 200)
    assert is_text_only_panel(bubble)

    sfx_on_white = _canvas(400, 700, 255)
    sfx_on_white[100:300, 200:210] = 20        # a few calligraphy strokes
    assert is_text_only_panel(sfx_on_white)

    art = _canvas(400, 700, 0)
    _paint_art(art, 50, 50, 600, 300)
    assert not is_text_only_panel(art)

    bright_room_with_art = _canvas(400, 700, 250)
    _paint_art(bright_room_with_art, 100, 50, 400, 300)
    assert not is_text_only_panel(bright_room_with_art)


def test_text_only_band_merges_into_its_art_neighbour():
    """A gutter band containing only a bubble must not become its own panel — shown
    alone it is a wall of text on the page background (a measured 4-second one in
    Frozen Player). It joins whichever neighbour carries more ink."""
    from manhwa2vid.panels.split import _merge_text_only_bands

    img = _canvas(1800, 720, 0)
    _paint_art(img, 40, 40, 640, 500)        # band 1: art (rows 0-600)
    _paint_bubble(img, 120, 700, 480, 200)   # band 2: bubble only (rows 600-1000)
    _paint_art(img, 40, 1100, 640, 600)      # band 3: art (rows 1000-1800)
    bands = [(0, 600), (600, 400), (1000, 800)]
    merged = _merge_text_only_bands(img, bands, {})
    assert len(merged) == 2, f"the bubble band should be gone: {merged}"
    covered = [(y, y + h) for y, h in merged]
    assert any(y <= 700 and end >= 900 for y, end in covered), "bubble rows still covered"


def test_all_text_page_is_left_alone():
    """Every band a bubble: nothing to merge into, so the page survives unchanged."""
    from manhwa2vid.panels.split import _merge_text_only_bands

    img = _canvas(1200, 720, 0)
    _paint_bubble(img, 100, 100, 400, 200)
    _paint_bubble(img, 150, 700, 400, 200)
    bands = [(0, 600), (600, 600)]
    assert len(_merge_text_only_bands(img, bands, {})) >= 1


def test_merge_respects_the_disable_flag():
    from manhwa2vid.panels.split import _merge_text_only_bands

    img = _canvas(1200, 720, 0)
    _paint_art(img, 40, 40, 640, 500)
    _paint_bubble(img, 120, 700, 480, 200)
    bands = [(0, 600), (600, 600)]
    cfg = {"panels": {"regions": {"enabled": False}}}
    assert _merge_text_only_bands(img, bands, cfg) == bands


def test_wide_sliver_band_merges_into_its_neighbour():
    """A band flatter than 5:1 is a split fragment or a system-message banner. Measured:
    an 800x108 crop of the bottom arc of a speech bubble held the screen for six
    seconds. min_panel_height is an absolute floor (89px on an 800-wide page) so a
    108px sliver clears it — the signal is the SHAPE."""
    from manhwa2vid.panels.split import _merge_text_only_bands

    img = _canvas(1400, 800, 0)
    _paint_art(img, 40, 40, 720, 560)         # band 1: art (rows 0-620)
    _paint_art(img, 0, 640, 800, 108)         # band 2: 7.4:1 sliver (rows 620-760)
    _paint_art(img, 40, 800, 720, 560)        # band 3: art (rows 760-1400)
    bands = [(0, 620), (620, 140), (760, 640)]
    merged = _merge_text_only_bands(img, bands, {})
    assert len(merged) == 2, f"the sliver should be gone: {merged}"
    assert all(h / 800 >= 0.20 for _y, h in merged), "no sliver survives"


def test_a_normal_wide_panel_is_not_a_sliver():
    """A cinematic 3:1 establishing panel is a real panel and must survive."""
    from manhwa2vid.panels.split import _merge_text_only_bands

    img = _canvas(1200, 800, 0)
    _paint_art(img, 20, 20, 760, 240)     # 800x280 band -> aspect 0.35, above the floor
    _paint_art(img, 20, 340, 760, 800)
    bands = [(0, 300), (300, 900)]
    assert len(_merge_text_only_bands(img, bands, {})) == 2


def test_content_free_catches_the_four_measured_classes():
    """The user found all four in a finished render: blade slivers on a dark field, a
    blown-up SFX glyph, speed lines, and flat colour bands. None are blank and none are
    text, so no existing filter saw them."""
    from manhwa2vid.panels.regions import is_content_free

    # speed lines: every edge points the same way (measured entropy 0.28)
    lines = _canvas(400, 700, 255)
    lines[:, ::7] = 10
    assert is_content_free(lines)

    # a dark field with a couple of thin slivers (measured coverage 0.08)
    sparse = _canvas(300, 800, 12)
    _paint_art(sparse, 60, 120, 90, 22)
    _paint_art(sparse, 400, 160, 70, 18)
    assert is_content_free(sparse)

    # a flat colour band
    band = _canvas(200, 800, 250)
    band[80:120] = (60, 90, 160)
    assert is_content_free(band)

    # ...and real art is NOT flagged (measured coverage 0.32-0.85, entropy 0.865+)
    art = _canvas(700, 700, 255)
    _paint_art(art, 40, 40, 620, 620)
    assert not is_content_free(art)


def test_content_free_keeps_sparse_but_real_art():
    """The thresholds sit far below the weakest measured real art, not beside it."""
    from manhwa2vid.panels.regions import is_content_free

    img = _canvas(700, 700, 250)
    _paint_art(img, 120, 120, 400, 400)   # coverage ~0.33, varied orientations
    assert not is_content_free(img)
