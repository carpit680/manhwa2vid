"""The Ken Burns zoom must not re-clip a bubble `_snap_offset` just protected.

Solo Leveling's 2026-08-28 preview held a four-second shot of "IF ANYTHING, I'M
CONFIDENT IN MY OWN SPEED." with the last line cut off along the bottom edge for the
entire shot, worsening as the push-in progressed. `_snap_offset` had done its job: it
positions the WINDOW so no bubble is sliced. The frame loop then crops `win/zoom` inside
that window, and a zoom of 1.12 takes ~5.5% off every edge.

Both render QA gates passed it — `bubble-dominance` and `clipped-text` are report-only
because the reference channel scores worse on them than we do.
"""

from __future__ import annotations

from manhwa2vid.video.effects import _crop_rect, _max_unclipped_zoom


def _clips(rect, b):
    l, t, r, bt = rect
    bx, by, bw, bh = b
    overlaps = bx < r and bx + bw > l and by < bt and by + bh > t
    whole = l <= bx and t <= by and bx + bw <= r and by + bh <= bt
    return overlaps and not whole


# A 1000x1000 panel, 16:9 window 1000x562 free on y, bubble filling most of the window.
WIN_W, WIN_H, PANEL = 1000, 562, 1000
LEGS = [(200, 200)]


def test_the_observed_defect_a_zoom_that_slices_a_protected_bubble():
    """Bubble sits fully inside the resting window with only ~10px of margin, so any
    meaningful zoom cuts it."""
    bubble = (60, 210, 880, 540)  # y 210..750, window at offset 200 covers 200..762
    z = _max_unclipped_zoom([bubble], LEGS, "y", WIN_W, WIN_H, PANEL, PANEL, 1.12)
    assert z < 1.12, "the uncapped zoom would slice it"
    rect = _crop_rect(200, z, "y", WIN_W, WIN_H, PANEL, PANEL)
    assert not _clips(rect, bubble), "the capped zoom still slices it"


def test_a_panel_with_no_lettering_keeps_the_full_camera_move():
    """The fix must not flatten every shot into a static frame."""
    assert _max_unclipped_zoom([], LEGS, "y", WIN_W, WIN_H, PANEL, PANEL, 1.12) == 1.12


def test_a_bubble_with_room_to_spare_keeps_the_full_zoom():
    small = (450, 380, 90, 60)  # dead centre, tiny
    assert _max_unclipped_zoom([small], LEGS, "y", WIN_W, WIN_H, PANEL, PANEL, 1.12) == 1.12


def test_a_bubble_the_window_already_cuts_does_not_cost_the_camera_its_move():
    """`_snap_offset`'s fallback deliberately leaves some bubbles clipped — 'a clipped
    bubble beats losing the salient art entirely'. Protecting those too would trade the
    move away for no gain."""
    straddling = (60, 700, 880, 300)  # extends past the window bottom (762) already
    assert _max_unclipped_zoom(
        [straddling], LEGS, "y", WIN_W, WIN_H, PANEL, PANEL, 1.12
    ) == 1.12


def test_the_cap_holds_across_the_whole_move_not_just_its_endpoints():
    """Offset eases between leg endpoints, so a mid-move position is sampled too."""
    bubble = (60, 300, 880, 430)
    legs = [(0, 400)]
    z = _max_unclipped_zoom([bubble], legs, "y", WIN_W, WIN_H, PANEL, PANEL, 1.12)
    for off in (0, 100, 200, 300, 400):
        rect = _crop_rect(off, z, "y", WIN_W, WIN_H, PANEL, PANEL)
        if any(rect[1] <= bubble[1] and bubble[1] + bubble[3] <= rect[3] for _ in [0]):
            assert not _clips(rect, bubble), f"sliced at offset {off}"
