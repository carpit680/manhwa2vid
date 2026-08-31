"""Collage region splitting — the 2D answer to gutter-only panel detection.

Every fixture reproduces a geometry measured on real pages in the 2026-08-26 defect
audit. The failure this guards: SL page 2's second gutter band (720x1633) contained
THREE story panels plus three speech bubbles, no full-width uniform row between any of
them — gutter detection found one cut in the whole page and the video opened on six
seconds of a speech bubble crawling past on black.
"""

from __future__ import annotations

from pathlib import Path

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

    # a dark field with thin slivers (the real p0005_08 / p0005_09 shape)
    #
    # 2026-08-31: since the detector judges the DOMINANT MASS, coverage is no longer
    # what catches this class — an isolated sliver crops tight and reads dense. The
    # ENTROPY signal carries it, which is what the class was always really about:
    # slivers and speed lines point one way, drawings point every way. Verified on the
    # real panels, which still measure content_free=True at coverage 0.22-0.44.
    #
    # The old fixture used `_paint_art` (uniform random noise) for the slivers, so
    # once isolated they had maximal entropy and read as art — it modelled the shape
    # of the class but not its texture.
    sparse = _canvas(300, 800, 12)
    for x in range(60, 700, 9):                 # oriented streaks, low entropy
        sparse[120:180, x : x + 2] = 210
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


# --- lettering on whole panels --------------------------------------------------------

def _panel(*rows: str, scale: int = 40) -> "np.ndarray":
    """Tiny painted panel: '.'=black ground, '#'=white, 'a'=mid-tone art."""
    import numpy as np

    tone = {".": 0, "#": 255, "a": 128}
    grid = np.array([[tone[c] for c in row] for row in rows], dtype=np.uint8)
    return np.repeat(np.repeat(grid, scale, 0), scale, 1)[:, :, None].repeat(3, 2)


def test_text_content_ratio_is_blind_to_ink_polarity():
    """The failure this detector exists for: `is_text_only_panel` needs a large BRIGHT
    region, so white type on a black field scored as art and 0 of Frozen Player's 100
    shown panels were ever flagged."""
    import cv2
    import numpy as np

    from manhwa2vid.panels.regions import is_text_only_panel, text_content_ratio

    # white lettering on black, the polarity the tonal rule cannot see
    img = np.zeros((240, 800, 3), np.uint8)
    for i in range(8):
        cv2.putText(img, "A", (60 + i * 80, 140), cv2.FONT_HERSHEY_SIMPLEX,
                    1.4, (255, 255, 255), 3)
    assert not is_text_only_panel(img), "precondition: the tonal rule misses this"
    assert text_content_ratio(img) > 0.5, "the geometric one must not"


def test_measured_extremes_bracket_the_threshold():
    """Real panels, labelled by eye 2026-08-27 across all 607 panels of both titles.

    Pinned as NUMBERS rather than a pass/fail so the margin itself is visible: the
    lowest true-text panel measured 0.853 and the highest true-art panel 0.778, and
    TEXT_DOMINANT sits between them. Moving the threshold into either class fails here
    instead of silently changing every video.
    """
    from manhwa2vid.panels.regions import TEXT_DOMINANT

    lowest_true_text = 0.853   # SL p0004_03, "NEVER." in a bubble on black
    highest_true_art = 0.778   # SL p0045_01, an aerial crowd scene with lettering on it
    assert highest_true_art < TEXT_DOMINANT < lowest_true_text


def test_a_bubble_with_art_beside_it_is_not_text_dominant():
    """The frames that must survive: a face WITH its speech bubble is a real shot."""
    import cv2
    import numpy as np

    from manhwa2vid.panels.regions import is_text_dominant_panel

    img = np.full((600, 800, 3), 128, np.uint8)          # a wall of mid-tone "art"
    cv2.circle(img, (400, 380), 170, (90, 60, 40), -1)   # a drawn shape
    cv2.ellipse(img, (400, 90), (220, 70), 0, 0, 360, (255, 255, 255), -1)
    for i in range(6):
        cv2.putText(img, "A", (250 + i * 55, 105), cv2.FONT_HERSHEY_SIMPLEX,
                    1.1, (0, 0, 0), 3)
    assert not is_text_dominant_panel(img)


def test_a_two_scene_blob_is_judged_on_its_dominant_mass():
    """Panel segmentation under-splits: one extracted "panel" holds two content masses
    with page background between them. Every predicate that asks "is there anything
    here" then measured the GUTTER as well as the art and answered no.

    Measured 2026-08-31 across both projects — flags that were WRONG when judged on the
    blob: visually_empty 42/60 (FP) and 31/48 (SL); content_free 30/65 and 13/35;
    text_dominant 14/27 and 5/13. Those panels never reached `fill_order`, the bounded
    fill starved, and unclaimed sentences held on one image for 16-22 seconds — which
    the renderer then chopped into alternating framings of the SAME picture. That is
    the "same frames show in succession" a viewer reports.

    The real p0014_04 is the case in hand: a shocked reaction face above a hospital
    scene, separated by white page, flagged visually_empty.
    """
    import numpy as np

    from manhwa2vid.panels.regions import dominant_mass

    page = _canvas(1400, 800, 255)
    _paint_art(page, 60, 40, 680, 420)          # upper scene
    _paint_art(page, 60, 940, 680, 400)         # lower scene, big white gutter between
    mass = dominant_mass(page)
    assert mass.shape[0] < 700, f"the gutter survived: {mass.shape}"
    assert mass.shape[0] > 300, f"the mass was destroyed: {mass.shape}"
    from manhwa2vid.panels.regions import is_content_free
    assert not is_content_free(page), "a two-scene page of real art read as void"


def test_a_single_mass_panel_is_returned_unchanged():
    """Applying the mass rule everywhere must be safe."""
    from manhwa2vid.panels.regions import dominant_mass

    art = _canvas(600, 600, 255)
    _paint_art(art, 20, 20, 560, 560)
    assert dominant_mass(art).shape[:2] == (560, 560) or dominant_mass(art).shape[0] >= 540


class TestTextCardsWithNoContainer:
    """A caption card whose interior IS the page ground — glowing system-message text on
    black — has no detectable container, so `text_content_ratio` counts only the glyph
    pixels and reads ~0.30 against a 0.82 threshold. Frozen Player closed on one for
    18.3 seconds and `closing-shot-is-art` passed, because the panel is not "text
    dominant" by that measure.

    The working question is "erase the lettering and its glow — is anything left?".
    Measured on the real panels: cards leave 0.000-0.061 of their content, art leaves
    0.216-0.498.
    """

    def _card(self, w=800, h=420, lines=1):
        """Light type on a dark ground, inside a thin outlined box — no filled
        container, which is exactly what defeats the ratio test.

        The dark margin around the box is load-bearing: `background_level` samples the
        image border, so a box touching the edge makes the bright OUTLINE the
        background and inverts the whole measurement. The real p0024_01 has that
        margin; a fixture without it tests nothing.
        """
        import cv2

        img = _canvas(h, w, 8)
        cv2.rectangle(img, (110, 120), (w - 110, h - 190), (120, 200, 210), 2)
        for li in range(lines):
            y = 175 + li * 55
            for i in range(9):
                x = 150 + i * 55
                cv2.putText(img, "A", (x, y), cv2.FONT_HERSHEY_SIMPLEX, 1.2,
                            (235, 245, 250), 3)
        return img

    def test_a_glowing_system_message_card_is_excluded(self):
        from manhwa2vid.panels.regions import is_text_dominant_panel

        assert is_text_dominant_panel(self._card())

    def test_detailed_art_is_not_mistaken_for_a_card(self):
        """The residual rule ALONE dropped 29 panels across both projects, and 5 of 6
        sampled were real art — a statue, a tunnel, a crowd. The glyph finder fires on
        texture (900-1400 "glyphs"), so the erase swallows the panel. A real card is a
        line or three of type, hence the glyph ceiling."""
        from manhwa2vid.panels.regions import is_text_dominant_panel

        rng = np.random.default_rng(7)
        art = _canvas(700, 900, 255)
        art[:] = rng.integers(30, 220, art.shape, dtype=np.uint8)   # dense texture
        assert not is_text_dominant_panel(art)

    def test_the_real_closing_card_and_the_real_art_beside_it(self):
        """p0024_01 closed Frozen Player for 18.3s; p0014_04 and p0015_01 are the art
        the same sweep must keep."""
        import cv2
        import pytest

        P = Path("projects/return-of-the-frozen-player-ch1-2/panels")
        if not P.exists():
            pytest.skip("project artifacts not present")
        from manhwa2vid.panels.regions import is_text_dominant_panel

        assert is_text_dominant_panel(cv2.imread(str(P / "p0024_01.png")))
        assert not is_text_dominant_panel(cv2.imread(str(P / "p0014_04.png")))
        assert not is_text_dominant_panel(cv2.imread(str(P / "p0015_01.png")))
