"""crop_to_content handed back the margin it had just removed.

Reported as "blank spaces around the artwork taking up the viewport". The crop found
the right content box, then re-added `pad_frac` on all four sides — computed on the
ORIGINAL PANEL dimensions, so on a panel whose art fills a third of the page a "4% pad"
became a 14% band of white or black page.

Measured on the six worst Solo Leveling panels before the fix: 9-14% of every cropped
panel was still blank. On a fresh random 60, median blank went 9.8% -> 0.4% and panels
over 20% blank went 20 -> 1.

The lesson attached to this one: the numbers had already passed through `dead-space`,
which is report-only and hardwired to return pass. It took looking at the panels.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from manhwa2vid.video.effects import crop_to_content


def _panel(art_w: int, art_h: int, pad: int, bg: int = 255) -> Image.Image:
    """Art centred in a page-coloured margin — the shape of a real split panel."""
    canvas = np.full((art_h + 2 * pad, art_w + 2 * pad), bg, dtype=np.uint8)
    rng = np.random.default_rng(0)
    canvas[pad : pad + art_h, pad : pad + art_w] = rng.integers(0, 200, (art_h, art_w))
    return Image.fromarray(canvas, mode="L").convert("RGB")


def _blank_fraction(im: Image.Image) -> float:
    a = np.asarray(im.convert("L"))
    h, w = a.shape
    flat = lambda line: line.std() < 6 and (line.mean() > 235 or line.mean() < 20)  # noqa: E731
    top = 0
    while top < h and flat(a[top]):
        top += 1
    bot = 0
    while bot < h - top and flat(a[h - 1 - bot]):
        bot += 1
    left = 0
    while left < w and flat(a[:, left]):
        left += 1
    right = 0
    while right < w - left and flat(a[:, w - 1 - right]):
        right += 1
    return (top + bot) / h + (left + right) / w


class TestMarginIsActuallyRemoved:
    def test_a_heavily_margined_panel_comes_back_clean(self):
        """The reported case: art in a third of the page."""
        panel = _panel(240, 200, pad=120)
        assert _blank_fraction(panel) > 0.4, "fixture check: the panel really is margined"
        assert _blank_fraction(crop_to_content(panel)) < 0.05

    def test_a_dark_page_margin_is_removed_too(self):
        """Background is whatever the border says it is — the lesson `crop_to_content`
        already learned once, kept pinned."""
        panel = _panel(240, 200, pad=120, bg=0)
        assert _blank_fraction(crop_to_content(panel)) < 0.05

    def test_the_pad_scales_with_the_art_not_the_page(self):
        """A panel-relative pad hands back more margin the smaller the art is, which is
        backwards and is how a 4% pad became a 14% band."""
        small = crop_to_content(_panel(120, 100, pad=300))
        large = crop_to_content(_panel(600, 500, pad=40))
        assert small.width <= 130, f"tiny art got a page-scaled pad: {small.width}px"
        assert large.width <= 620


class TestItStillDoesNoHarm:
    def test_art_is_never_cut_into(self):
        panel = _panel(300, 240, pad=60)
        out = crop_to_content(panel)
        assert out.width >= 300 and out.height >= 240

    def test_a_full_bleed_panel_is_returned_untouched(self):
        rng = np.random.default_rng(1)
        panel = Image.fromarray(rng.integers(0, 200, (300, 400), dtype=np.uint8), "L").convert("RGB")
        out = crop_to_content(panel)
        assert out.size == panel.size

    def test_an_entirely_blank_panel_is_returned_rather_than_crashing(self):
        blank = Image.fromarray(np.full((100, 100), 255, np.uint8), "L").convert("RGB")
        assert crop_to_content(blank).size == (100, 100)


@pytest.mark.parametrize("pad", [0, 40, 150])
def test_output_is_never_larger_than_the_input(pad):
    panel = _panel(200, 160, pad=pad)
    out = crop_to_content(panel)
    assert out.width <= panel.width and out.height <= panel.height
