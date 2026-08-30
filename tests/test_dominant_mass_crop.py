"""Interior page background: the banner class that three margin-crop fixes couldn't fix.

Reported from watching, three times: "thick white banners or black banners on top and
bottom when the bubbles are partly in those areas". Manual inspection of the offending
panels found the real shape: one extracted "panel" holding SEVERAL content masses with
page background between them — a framed panel + a floating bubble + a borderless dark
scene as one png (FP p0009_01), art above typeset page text (SL p0049_03). A margin
crop cannot help; the content bbox legitimately spans everything, and the letterbox
bars (a blurred copy of the panel) inherit the interior white/black.

`_dominant_mass_crop` cuts to the dominant content mass. These tests also pin two
destructive failure modes found while building it: a near-black MOOD panel with one
faint glow must not collapse to the glow (800x712 became 29x27 — a defect that predates
every 2026-08-30 revision), and a "dominant" mass that is a sliver means background-
dominated art, not a collage.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from manhwa2vid.video.effects import crop_to_content


def _img(a: np.ndarray) -> Image.Image:
    return Image.fromarray(a, mode="L").convert("RGB")


def _white(w, h):
    return np.full((h, w), 255, dtype=np.uint8)


def test_two_masses_split_by_white_page_keep_only_the_dominant():
    """The p0009_01 shape: rich art, a wide white gap, then a smaller mass."""
    a = _white(600, 900)
    rng = np.random.default_rng(1)
    a[40:400, 30:570] = (rng.random((360, 540)) * 160).astype(np.uint8)   # big art mass
    a[700:860, 200:400] = 90                                              # small mass
    out = crop_to_content(_img(a))
    assert out.height < 500, f"the white interior survived: {out.size}"
    arr = np.asarray(out.convert("L"))
    assert arr.mean() < 200, "kept the page, not the art"


def test_art_beats_a_lettering_mass_even_when_lettering_is_larger():
    """The p0049_03 shape: art above, page-typeset text below a white gap. The narrator
    is already speaking; the screen should carry the moment."""
    a = _white(600, 700)
    rng = np.random.default_rng(2)
    a[20:300, 20:580] = (rng.random((280, 560)) * 150).astype(np.uint8)   # art
    for row in range(520, 660, 14):                                       # text lines
        a[row:row + 7, 60:540] = 10
    out = crop_to_content(_img(a))
    assert out.height <= 340, f"kept both masses: {out.size}"
    assert np.asarray(out.convert("L")).std() > 30, "kept the text strip, not the art"


def test_a_mood_panel_is_never_collapsed_to_its_glow():
    """FP p0015_04: near-black with one faint speck. The FIELD is the content."""
    a = np.full((700, 800), 4, dtype=np.uint8)
    a[640:690, 720:790] = 70
    out = crop_to_content(_img(a))
    assert out.size == (800, 700), f"mood panel collapsed to {out.size}"


def test_a_single_mass_panel_is_untouched_by_the_mass_logic():
    a = _white(500, 400)
    a[20:380, 20:480] = 100
    out = crop_to_content(_img(a))
    assert out.width >= 440 and out.height >= 340


def test_thin_interior_gaps_do_not_split():
    """Art is full of quiet strips; only LONG background runs separate masses."""
    a = _white(500, 400)
    a[20:190, 20:480] = 100
    a[205:380, 20:480] = 100          # 15px gap on 400 height: under the 6% separator
    out = crop_to_content(_img(a))
    assert out.height >= 340, f"split on a thin gap: {out.size}"


def test_dark_page_blob_cuts_toward_the_bright_content():
    """The p0006_02 shape, black page around framed art (background_level is border-
    aware, so bg is black here)."""
    a = np.full((900, 600), 3, dtype=np.uint8)
    rng = np.random.default_rng(3)
    a[300:640, 100:500] = (rng.random((340, 400)) * 180 + 60).astype(np.uint8)
    out = crop_to_content(_img(a))
    assert out.height < 760, f"kept the whole black page: {out.size}"


@pytest.mark.parametrize("size", [(40, 40), (600, 30)])
def test_degenerate_sizes_do_not_raise(size):
    crop_to_content(_img(_white(*size)))
