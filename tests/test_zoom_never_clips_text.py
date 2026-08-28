"""The Ken Burns zoom must not re-clip a bubble `_snap_offset` just protected.

Solo Leveling's 2026-08-28 preview held a four-second shot of "IF ANYTHING, I'M
CONFIDENT IN MY OWN SPEED." with the last line cut off along the bottom edge for the
entire shot, worsening as the push-in progressed. `_snap_offset` had done its job: it
positions the WINDOW so no bubble is sliced. The frame loop then crops `win/zoom` inside
that window, and a zoom of 1.12 takes ~5.5% off every edge.

Both render QA gates passed it — `bubble-dominance` and `clipped-text` are report-only
because the reference channel scores worse on them than we do.

The repair shifts the crop rather than shrinking the zoom: capping zoom until every box
fits left 57% of Solo Leveling's shots with neither pan nor zoom, stiller than the
reference, whose static shots still zoom.
"""

from __future__ import annotations

from manhwa2vid.video.effects import (
    _crop_rect,
    _max_unclipped_zoom,
    _protected_boxes,
)


def _clips(rect, b):
    l, t, r, bt = rect
    bx, by, bw, bh = b
    overlaps = bx < r and bx + bw > l and by < bt and by + bh > t
    whole = l <= bx and t <= by and bx + bw <= r and by + bh <= bt
    return overlaps and not whole


# A 1000x1000 panel, 16:9 window 1000x562 free on y, resting at offset 200.
WIN_W, WIN_H, PANEL = 1000, 562, 1000
LEGS = [(200, 200)]


def _prot(boxes, legs=None):
    return _protected_boxes(boxes, legs or LEGS, "y", WIN_W, WIN_H, PANEL, PANEL)


def test_the_observed_defect_a_zoom_that_slices_a_protected_bubble():
    bubble = (60, 210, 880, 540)  # y 210..750; the window at offset 200 covers 200..762
    protect = _prot([bubble])
    assert protect, "the window holds it whole at rest, so it must be protected"
    assert _clips(_crop_rect(200, 1.12, "y", WIN_W, WIN_H, PANEL, PANEL), bubble), \
        "fixture check: the uncapped, uncentred crop really does slice it"
    z = _max_unclipped_zoom(protect, WIN_W, WIN_H, 1.12)
    rect = _crop_rect(200, z, "y", WIN_W, WIN_H, PANEL, PANEL, protect)
    assert not _clips(rect, bubble), "still sliced after capping and recentring"


def test_a_panel_with_no_lettering_keeps_the_full_camera_move():
    """The fix must not flatten every shot into a static frame."""
    assert _max_unclipped_zoom([], WIN_W, WIN_H, 1.12) == 1.12


def test_a_bubble_with_room_to_spare_keeps_the_full_zoom():
    """Shifting beats shrinking: a box that FITS costs the shot no motion at all."""
    small = (450, 380, 90, 60)
    assert _max_unclipped_zoom(_prot([small]), WIN_W, WIN_H, 1.12) == 1.12


def test_a_bubble_the_window_already_cuts_is_not_protected():
    """`_snap_offset`'s fallback deliberately leaves some bubbles clipped — "a clipped
    bubble beats losing the salient art entirely". Chasing those would move the camera
    off the art for nothing."""
    straddling = (60, 700, 880, 300)  # already extends past the window bottom (762)
    assert _prot([straddling]) == []
    assert _max_unclipped_zoom(_prot([straddling]), WIN_W, WIN_H, 1.12) == 1.12


def test_the_box_stays_whole_across_the_whole_move_not_just_its_endpoints():
    """Offset eases between leg endpoints, so every position must hold."""
    bubble = (60, 300, 880, 430)
    legs = [(0, 400)]
    protect = _prot([bubble], legs)
    z = _max_unclipped_zoom(protect, WIN_W, WIN_H, 1.12)
    for off in (0, 100, 200, 300, 400):
        rect = _crop_rect(off, z, "y", WIN_W, WIN_H, PANEL, PANEL, protect)
        assert not _clips(rect, bubble), f"sliced at offset {off}"


class TestSnapFallbackPicksTheLeastBad:
    """`_snap_offset` returned the original offset when no clean position existed — and
    the original could be strictly the worst option available.

    Solo Leveling's p0009_01: a 1440px panel, 1262px window (span 178), captions at
    x91-1003 and x592-1439. Offset 0 holds the first caption whole, offset 177 holds the
    second, and the salience anchor at 144 cuts BOTH. The shipped video showed two half
    captions where one could have been whole.
    """

    WIN, SPAN = 1262, 178
    BOXES = [(91, 59, 912, 221), (592, 567, 847, 142)]

    def _clipped(self, offset):
        lo, hi = offset, offset + self.WIN
        return sum(1 for bx, _, bw, _ in self.BOXES if bx < lo < bx + bw or bx < hi < bx + bw)

    def test_the_anchor_that_cuts_both_captions_is_not_what_ships(self):
        from manhwa2vid.video.effects import _snap_offset

        assert self._clipped(144) == 2, "fixture check: the anchor really does cut both"
        chosen = _snap_offset(144, self.WIN, self.BOXES, "x", self.SPAN)
        assert self._clipped(chosen) < 2, f"offset {chosen} still cuts both captions"

    def test_a_clean_offset_still_wins_outright(self):
        from manhwa2vid.video.effects import _snap_offset

        boxes = [(300, 0, 200, 100)]
        chosen = _snap_offset(250, 400, boxes, "x", 900)
        lo, hi = chosen, chosen + 400
        assert not (300 < lo < 500 or 300 < hi < 500)

    def test_an_already_clean_offset_is_returned_untouched(self):
        """Ties break toward the anchor: the camera must not wander when it costs
        nothing to stay."""
        from manhwa2vid.video.effects import _snap_offset

        assert _snap_offset(144, self.WIN, [], "x", self.SPAN) == 144
