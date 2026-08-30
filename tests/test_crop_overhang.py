"""A speech bubble overhanging the panel border dragged the crop into the page margin.

Reported from watching: "blank spaces around the artwork taking up the viewport", and
attributed at the time to "text bubbles that are partly outside the artwork area". That
attribution was correct. `getbbox()` returns the extent of ANY ink, so on Frozen Player
p0023_08 — art and border ending at x=345, the "AH, SHIT." bubble's outline reaching
x=364 — the crop kept 19 columns of white page and rendered them as a band down the
right of the frame.

An earlier investigation rejected bubble overhang after measuring 27 Solo Leveling
panels where removing lettering moved the bbox 0.0%. That sample had no overhanging
bubbles.

The first version of the fix trimmed any nearly-empty edge and destroyed sparse panels —
p0006_01 went 558x282 to 2x2, because on a uniformly faint panel EVERY column is under
the overhang threshold. These pin both the fix and that failure.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from manhwa2vid.video.effects import crop_to_content


def _panel(w: int, h: int) -> np.ndarray:
    return np.full((h, w), 255, dtype=np.uint8)


def _img(a: np.ndarray) -> Image.Image:
    return Image.fromarray(a, mode="L").convert("RGB")


def test_a_bubble_overhanging_the_border_is_not_kept():
    """The shape of p0023_08: solid art to a hard border, then a thin arc of bubble
    outline out in the margin.

    Proportions matter and are taken from the real panel — a 19 px overhang on a 355 px
    box, i.e. 5.4% of the side. An overhang larger than `_MAX_TRIM_FRAC` is deliberately
    NOT trimmed: at that size the walk can no longer tell an overhang from the artwork.
    """
    a = _panel(400, 400)
    a[20:380, 20:300] = 60          # art
    a[20:380, 298:300] = 0          # the border line — a full-height edge
    a[190:210, 300:315] = 0         # bubble outline overhanging into the margin
    out = crop_to_content(_img(a))
    assert out.width <= 290, f"kept the overhang: width {out.width}"
    assert out.width >= 270, f"over-cropped into the art: width {out.width}"


def test_a_panel_with_no_overhang_is_untouched():
    a = _panel(200, 400)
    a[20:380, 20:180] = 60
    plain = crop_to_content(_img(a))
    a2 = a.copy()
    assert crop_to_content(_img(a2)).size == plain.size


def test_a_uniformly_faint_panel_is_not_eaten():
    """p0006_01: 558x282 became 2x2. Every column sits under the overhang threshold, so
    a walk with no landing requirement consumes the whole panel."""
    a = _panel(300, 200)
    rng = np.random.default_rng(0)
    sparse = rng.random((200, 300)) < 0.02        # ~2% coverage everywhere
    a[sparse] = 0
    out = crop_to_content(_img(a))
    assert out.width > 150 and out.height > 100, f"faint panel eaten: {out.size}"


def test_a_thin_strip_panel_keeps_its_height():
    """p0016_18: a 377x17 box became 377x3 when the trim budget was scaled by the
    coverage span (the width) instead of the side being walked."""
    a = _panel(400, 30)
    a[8:24, 10:390] = 70
    out = crop_to_content(_img(a))
    assert out.height >= 12, f"thin strip crushed: {out.size}"


def test_the_trim_is_bounded_on_every_side():
    """An overhang is thin by definition; the walk may never travel far."""
    a = _panel(300, 300)
    a[10:290, 10:290] = 90
    a[10:290, 10:12] = 0
    before = crop_to_content(_img(a))
    a2 = a.copy()
    a2[140:160, 290:299] = 0        # a long overhang on the right
    after = crop_to_content(_img(a2))
    assert after.width <= before.width + 4
    assert after.width >= before.width * 0.85, "trim exceeded its bound"


@pytest.mark.parametrize("size", [(4, 4), (1, 50), (50, 1)])
def test_degenerate_panels_do_not_raise(size):
    crop_to_content(_img(_panel(*size)))


def test_real_panel_loses_the_white_band():
    """The reported case, measured on the shipped artifact."""
    from pathlib import Path

    p = Path("projects/return-of-the-frozen-player-ch1-2/panels/p0023_08.png")
    if not p.exists():
        pytest.skip("project artifact not present")
    im = Image.open(p).convert("RGB")
    out = crop_to_content(im)
    arr = np.asarray(out.convert("L"))
    right = arr[:, -8:]
    assert not (right.mean() > 245 and right.std() < 8), "white band still on the right edge"
