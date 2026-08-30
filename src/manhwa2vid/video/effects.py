"""Video effects helpers."""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageFilter

from manhwa2vid.config import get_nested
from manhwa2vid.models import Panel


def cosine_ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return (1.0 - math.cos(math.pi * t)) / 2.0


#: An edge line of a panel border covers essentially its whole side; a speech bubble
#: poking out past that border covers a few percent. On the panels where this defect is
#: visible the overhang columns run 2.4-5.2% and the border column runs ~100%.
_OVERHANG_MAX_FRAC = 0.08
#: What the walk must land ON for the trim to be believed: a real edge, not more sparse
#: ink. Without this the walk eats faint panels whole — it took p0006_01 from 558x282 to
#: 2x2, because on a uniformly faint panel EVERY column is under the overhang threshold.
_EDGE_MIN_FRAC = 0.40
#: And it may never travel far, because an overhang is thin by definition.
_MAX_TRIM_FRAC = 0.12


def _tighten_to_sustained(content: "np.ndarray", box: tuple[int, int, int, int]):
    """Pull each edge of `box` in past a THIN overhang, but only onto a real edge.

    `getbbox()` returns the extent of ANY ink, so one thin thing sticking out past the
    artwork sets the edge. On this material that thing is usually a SPEECH BUBBLE
    overhanging the panel border into the page margin — reported from watching as
    "blank spaces around the artwork taking up the viewport", and correctly attributed
    to the bubbles at the time.

    Frozen Player p0023_08 is the worked example: art and border end at x=345, the
    "AH, SHIT." bubble's outline reaches x=364, and the crop kept all 19 columns of white
    page between them. On screen that was a white band down the right of the frame.

    An earlier investigation rejected bubble overhang as a cause after measuring 27 Solo
    Leveling panels, where removing lettering changed the bbox by 0.0%. That sample had
    no overhanging bubbles; the conclusion was drawn too widely.

    Three conditions, all required, because the first version of this had only the first
    and destroyed sparse panels:
      1. the columns being removed are nearly empty (`_OVERHANG_MAX_FRAC`),
      2. the walk STOPS on a substantial edge (`_EDGE_MIN_FRAC`) — otherwise there was
         no border there and the sparseness is the art itself, so the edge is reverted,
      3. it travels no further than `_MAX_TRIM_FRAC` of the side, an overhang being thin.
    """
    x0, y0, x1, y1 = box
    cols = content[y0:y1, :].sum(axis=0)
    rows = content[:, x0:x1].sum(axis=1)
    h, w = max(1, y1 - y0), max(1, x1 - x0)

    def walk(lo, hi, cover, span, from_high):
        limit = max(1, int((hi - lo) * _MAX_TRIM_FRAC))
        moved, a, b = 0, lo, hi
        while moved < limit and b - a > 2:
            idx = b - 1 if from_high else a
            if cover[idx] >= _OVERHANG_MAX_FRAC * span:
                break
            b, a = (b - 1, a) if from_high else (b, a + 1)
            moved += 1
        if not moved:
            return lo, hi
        landed = cover[b - 1 if from_high else a]
        if landed < _EDGE_MIN_FRAC * span:
            return lo, hi  # no border here — the sparse ink IS the art
        return a, b

    x0, x1 = walk(x0, x1, cols, h, from_high=True)
    x0, x1 = walk(x0, x1, cols, h, from_high=False)
    y0, y1 = walk(y0, y1, rows, w, from_high=True)
    y0, y1 = walk(y0, y1, rows, w, from_high=False)
    return x0, y0, x1, y1


def _dominant_mass_crop(panel: Image.Image) -> Image.Image:
    """Cut a multi-mass panel down to its dominant content mass.

    A "mass" is a maximal run of rows (then, within it, columns) whose content coverage
    clears a floor; runs below it are page background. Interior background runs must be
    LONG (>= 6% of the dimension, >= 24 px) to count as separators — panel art is full
    of thin quiet strips that mean nothing.

    Selection is by content pixels, with one correction: when the winner is a lettering
    mass (a floating bubble or typeset page text) and a substantial art mass exists,
    the art wins — the narrator is already speaking; the screen should carry the moment.

    A panel with one mass, or whose masses this cannot separate, returns unchanged, so
    applying this everywhere is safe. The uniformly-faint panel that an earlier crop
    revision ate to 2x2 stays whole here by construction: its rows all clear the
    coverage floor, so it is a single mass.
    """
    from manhwa2vid.panels.regions import background_level

    for _axis_pass in range(2):
        arr = np.asarray(panel.convert("L"))
        bg = background_level(arr)
        content = np.abs(arr.astype(np.int16) - int(bg)) > 18
        h, w = content.shape
        if h < 48 or w < 48:
            return panel
        changed = False
        for axis, span, dim in ((1, w, h), (0, h, w)):
            cov = content.sum(axis=axis)
            floor = max(2.0, 0.015 * span)
            is_bg = cov < floor
            min_sep = max(24, int(0.06 * dim))
            # runs of background rows/cols
            runs, start = [], None
            for i, b in enumerate(is_bg):
                if b and start is None:
                    start = i
                elif not b and start is not None:
                    runs.append((start, i)); start = None
            if start is not None:
                runs.append((start, len(is_bg)))
            separators = [r for r in runs if r[1] - r[0] >= min_sep]
            if not separators:
                continue
            # masses = complement of separator runs
            masses, pos = [], 0
            for a, b in separators:
                if a > pos:
                    masses.append((pos, a))
                pos = b
            if pos < len(is_bg):
                masses.append((pos, len(is_bg)))
            masses = [m for m in masses if m[1] - m[0] >= 8]
            if len(masses) < 2:
                continue

            def _mass_pixels(m):
                a, b = m
                return int(content[a:b, :].sum() if axis == 1 else content[:, a:b].sum())

            ranked = sorted(masses, key=_mass_pixels, reverse=True)
            winner = ranked[0]
            if len(ranked) > 1 and _mass_pixels(ranked[1]) >= 0.4 * _mass_pixels(winner):
                try:
                    import cv2

                    from manhwa2vid.panels.regions import is_text_dominant_panel

                    def _crop_of(m):
                        a, b = m
                        return (panel.crop((0, a, w, b)) if axis == 1
                                else panel.crop((a, 0, b, h)))

                    def _texty(m):
                        img = cv2.cvtColor(np.array(_crop_of(m)), cv2.COLOR_RGB2BGR)
                        return is_text_dominant_panel(img)

                    if _texty(winner) and not _texty(ranked[1]):
                        winner = ranked[1]
                except Exception:  # noqa: BLE001 — tie-break is best-effort
                    pass
            a, b = winner
            if (b - a) < 0.10 * dim:
                # The "dominant" mass is a sliver of the panel: this is background-
                # dominated mood art with incidental marks, not a collage. Keep it.
                continue
            panel = panel.crop((0, a, w, b)) if axis == 1 else panel.crop((a, 0, b, h))
            changed = True
            break  # re-derive bg/content for the new crop before the other axis
        if not changed:
            break
    return panel


def crop_to_content(panel: Image.Image, pad_frac: float = 0.004) -> Image.Image:
    """Crop away white margins so the frame is filled with art, not paper.

    Measured need: ~48 shown panels across the two real projects carry their content in
    under 60% of their area, and `letterbox_panel` fit the WHOLE png — margins included —
    so their art rendered at barely half the size the screen allowed.

    The pad was 0.04 and that WAS the blank-margin defect the user reported on
    2026-08-30 as "blank spaces around the artwork taking up the viewport". The crop
    found the right box and then handed the margin straight back: 4% of the ORIGINAL
    panel dimensions, re-added on all four sides. Measured on the six worst Solo
    Leveling panels — blank fraction vertical/horizontal after cropping:

        pad 0.04 (old)   9-14% still blank on every panel
        pad 0.004        0% on every panel, art reaching the frame edge

    Confirmed by eye on those panels, not only by the numbers — the numbers had already
    passed once through `dead-space`, which is report-only and hardwired to pass.

    Scale of the defect: 155 of 400 Solo Leveling panels carried >20% blank margins,
    and on screen that was 79 panels / 258 s = 34% of runtime.

    The pad is a fraction of the DETECTED BOX now, not of the panel: on a panel whose
    art occupies a third of the page, a panel-relative pad is three times the intended
    breathing room, which is how a "4% pad" became a 14% band.

    Background-aware, and that is load-bearing: the first version defined content as
    `v < 240`, i.e. "anything not white". On a DARK page every pixel satisfies that, so
    the mask covered the whole image and nothing was ever cropped — 39 of Frozen
    Player's shown panels kept their black top/bottom bands, and the camera then panned
    through the emptiness. Same lesson `_find_gutter_rows` and `panels/regions.py`
    already learned: the background is whatever the border says it is.

    Known limit, recorded where the decision is made: this cannot tell art ink from
    speech-bubble ink (no bubble geometry exists — OCR boxes are empty on both real
    projects), so a bubble-heavy panel stays bubble-heavy. Bubble avoidance needs a
    white-blob detector or OCR-with-boxes; separate work.
    """
    from manhwa2vid.panels.regions import background_level

    arr = np.asarray(panel.convert("L"))
    bg = background_level(arr)
    mask_arr = (np.abs(arr.astype(np.int16) - int(bg)) > 18).astype(np.uint8) * 255
    # A panel that is nearly all background is a MOOD panel — a black beat with a
    # faint glow, a pale sky. The field is the content; cropping toward the one bright
    # speck turns 800x712 into 29x27 and the render into a blur. This destruction
    # predates every 2026-08-30 crop revision (the bbox mask has always found only the
    # speck) and was caught by the mass-crop sweep, not by any gate.
    if float((mask_arr > 0).mean()) < 0.02:
        return panel
    mask = Image.fromarray(mask_arr, mode="L")
    box = mask.getbbox()
    if box is None:
        return panel
    content = mask_arr > 0
    x0, y0, x1, y1 = _tighten_to_sustained(content, box)
    if (x1 - x0) * (y1 - y0) < 0.99 * panel.width * panel.height:
        # 0.99, not 0.95: at 0.95 a panel whose art already fills it kept a 5% band of
        # page, and the bail fired on roughly a quarter of panels. There is no cost to
        # cropping a nearly-full panel — the crop is a no-op by construction — so the
        # bail only needs to catch "the mask found everything", not "almost everything".
        #
        # Pad relative to the DETECTED BOX — panel-relative padding scales with the
        # page — and per SIDE: a side whose edge landed on a real border gets no pad
        # at all. Re-adding 1-3 px of page beyond a border the tighten walk just found
        # is the "really thin white lines on the sides" reported 2026-08-30.
        h_span, w_span = max(1, y1 - y0), max(1, x1 - x0)
        col_cov = content[y0:y1, :].sum(axis=0)
        row_cov = content[:, x0:x1].sum(axis=1)
        def _pad(edge_cov: float, span_frac: int, base: int) -> int:
            return 0 if edge_cov >= _EDGE_MIN_FRAC * span_frac else base
        pad_x, pad_y = int(w_span * pad_frac), int(h_span * pad_frac)
        panel = panel.crop(
            (
                max(0, x0 - _pad(col_cov[x0], h_span, pad_x)),
                max(0, y0 - _pad(row_cov[y0], w_span, pad_y)),
                min(panel.width, x1 + _pad(col_cov[x1 - 1], h_span, pad_x)),
                min(panel.height, y1 + _pad(row_cov[y1 - 1], w_span, pad_y)),
            )
        )

    # Interior page background. Everything above trims MARGINS; it cannot help when
    # the "panel" is really several content masses with page background BETWEEN them —
    # a framed panel, a floating bubble and a borderless dark scene extracted as one
    # png (FP p0009_01), or art above typeset page text (SL p0049_03). Framing such a
    # blob renders its interior background as the white/black banners reported on
    # 2026-08-30, and the letterbox bars (a blurred copy of the panel) inherit them.
    # Cut to the dominant content mass instead; segmentation itself is revisited
    # separately, before the 20-chapter run.
    return _dominant_mass_crop(panel)






def ken_burns_params(seed: str) -> tuple[float, float]:
    rng = random.Random(seed)
    zoom_start = 1.0 + rng.uniform(0.0, 0.02)
    zoom_end = zoom_start + rng.uniform(0.04, 0.10)
    return zoom_start, zoom_end


def render_vertical_scroll_frames(
    panel_path: Path,
    width: int,
    height: int,
    num_frames: int,
    config: dict[str, Any],
) -> list[Image.Image]:
    supersample = int(get_nested(config, "video", "motion_supersample", default=2))
    out_w = width * supersample
    out_h = height * supersample

    # Crop margins first so the scroll traverses ART, not the blank lead-in and
    # tail a webtoon strip carries; the camera previously spent readable seconds on
    # empty paper at both ends of every tall panel.
    panel = crop_to_content(Image.open(panel_path).convert("RGB"))
    scale = out_w / panel.width
    scaled_h = max(int(panel.height * scale), out_h)
    scaled = panel.resize((out_w, scaled_h), Image.Resampling.LANCZOS)

    max_y = max(0, scaled_h - out_h)

    # Cap scroll speed. Travel is otherwise panel_height/dwell, which on a tall strip with a
    # short beat reaches thousands of px/s — an unreadable vertical smear. When the full panel
    # cannot be traversed at a readable speed, show the top portion instead of racing through it.
    fps = int(get_nested(config, "video", "fps", default=30))
    max_px_per_sec = float(get_nested(config, "video", "max_scroll_px_per_sec", default=600.0))
    start_y = 0
    if max_px_per_sec > 0 and fps > 0:
        duration = num_frames / fps
        allowed_travel = int(max_px_per_sec * duration * supersample)
        if allowed_travel < max_y:
            # Cannot traverse the whole strip at a readable speed. Previously the camera
            # pinned to the TOP and the bottom of the strip simply never appeared —
            # arbitrary with respect to content. Center the reachable window instead.
            start_y = (max_y - allowed_travel) // 2
            max_y = allowed_travel

    frames: list[Image.Image] = []
    for i in range(num_frames):
        t = i / max(num_frames - 1, 1)
        # Float, and resize(box=...) — same reason as the fill-frame path above: an
        # integer y makes a slow scroll advance in whole-pixel steps, which reads as
        # judder rather than movement.
        y = start_y + max_y * cosine_ease(t)
        frames.append(
            scaled.resize(
                (width, height),
                Image.Resampling.LANCZOS,
                box=(0.0, y, float(out_w), y + out_h),
            )
        )
    return frames




# --- fill-frame camera ---------------------------------------------------------------
#
# The camera lives INSIDE the panel: every shot is a 16:9 window over the art, chosen by
# salience, panned in reading order. Decision measured and taken with the user
# (2026-08-26 audit): fitting whole panels left 51-52% of runtime-weighted screen area
# as blurred bars — SL spends 89% of its runtime on panels taller than the frame.


def _text_boxes(rgb: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Lettering, and the bubbles holding it. Used two ways by the camera: to down-weight
    text in salience (art outranks type) and to keep a resting frame from slicing a
    bubble at the frame edge.

    This replaced a local brightness test (`> 232`, closed, mostly filled). That test
    found "large pale region", not "bubble": it missed a jagged "WHAT?!" starburst
    entirely — which, being full of high-contrast spikes, then ATTRACTED the window
    instead of repelling it — while flagging white walls and hospital bedding as bubbles
    and steering the camera off real art.

    `panels.regions.text_regions` is the validated detector: geometric, polarity-blind,
    zero false positives across all 607 panels of both titles. Measured on FP's 42
    fill-frame panels before the swap, counting windows where lettering covers more than
    30% of the screen: 16 before, 10 after.
    """
    from manhwa2vid.panels.regions import text_regions

    return text_regions(rgb)


def _salience(gray: np.ndarray, bubbles: list[tuple[int, int, int, int]], *, bubble_weight: float = 0.40) -> np.ndarray:
    """Where the art is: local gradient energy, bubbles down-weighted.

    Flat background scores zero by construction; a bubble is full of high-contrast text
    edges, which is exactly why raw gradient energy loved them — hence the explicit
    down-weight rather than a smarter operator.

    0.40, not the original 0.15. That near-total suppression was harmless only while the
    detector rarely found real lettering; once it did, SOUND EFFECTS became the problem.
    SFX is painted ON the art and sits exactly where the action is, so shoving the camera
    off it walks away from the subject — Frozen Player's opening reframed from its only
    character onto an empty door. Measured over FP's 42 fill-frame panels, counting
    windows where lettering covers more than 30% of the screen: 21 with no down-weight,
    10 at 0.15 (and a broken opening), 14 at 0.40, 18 at 0.55.
    """
    g = gray.astype(np.float32)
    energy = np.zeros_like(g)
    energy[:, :-1] += np.abs(np.diff(g, axis=1))
    energy[:-1, :] += np.abs(np.diff(g, axis=0))
    energy = cv2.blur(energy, (15, 15))
    for x, y, w, h in bubbles:
        energy[y : y + h, x : x + w] *= bubble_weight
    return energy


def _window_geometry(pw: int, ph: int, frame_w: int, frame_h: int) -> tuple[int, int, str, int]:
    """Largest frame-shaped window inside the panel: (win_w, win_h, free_axis, span)."""
    ar = frame_w / frame_h
    win_w = min(pw, int(round(ph * ar)))
    win_h = min(ph, int(round(win_w / ar)))
    win_w = min(pw, int(round(win_h * ar)))
    if ph - win_h >= pw - win_w:
        return win_w, win_h, "y", ph - win_h
    return win_w, win_h, "x", pw - win_w


def _offset_profile(sal: np.ndarray, axis: str, win_len: int) -> np.ndarray:
    """Total salience captured by the window at each offset along the free axis."""
    line = sal.sum(axis=1) if axis == "y" else sal.sum(axis=0)
    span = len(line) - win_len
    if span <= 0:
        return np.array([line.sum()])
    csum = np.concatenate([[0.0], np.cumsum(line)])
    return csum[win_len:] - csum[:-win_len]


def _snap_offset(
    offset: int,
    win_len: int,
    bubbles: list[tuple[int, int, int, int]],
    axis: str,
    max_offset: int,
) -> int:
    """Nudge a resting offset so no bubble is sliced by the window edge.

    Tries small shifts either side; a bubble must end up fully inside or fully outside.
    When two boxes make conflicting demands no offset satisfies both, and the fallback
    then picks the one slicing the FEWEST — because returning the original unchanged
    could be strictly the worst choice available.

    Solo Leveling's p0009_01 is the case that showed it: a 1440px panel with a 1262px
    window (span 178) and captions at x91-1003 and x592-1439. Offset 0 holds the first
    whole, offset 177 holds the second, and the salience anchor at 144 cuts BOTH. The
    old fallback shipped 144 and the viewer saw two half-captions where one could have
    been whole.

    Ties break toward the original offset, so the camera still rests on the most salient
    window whenever the choice costs nothing — a clipped bubble beats losing the salient
    art entirely, but a clipped bubble does not beat an unclipped one.
    """
    def clip_count(o: int) -> int:
        lo, hi = o, o + win_len
        n = 0
        for bx, by, bw, bh in bubbles:
            b0 = by if axis == "y" else bx
            b1 = b0 + (bh if axis == "y" else bw)
            if b0 < lo < b1 or b0 < hi < b1:
                n += 1
        return n

    if clip_count(offset) == 0:
        return offset
    reach = max(4, int(win_len * 0.15))
    best = (clip_count(offset), 0, offset)
    for delta in range(1, reach):
        for cand in (offset - delta, offset + delta):
            if not 0 <= cand <= max_offset:
                continue
            n = clip_count(cand)
            if n == 0:
                return cand
            if (n, delta) < best[:2]:
                best = (n, delta, cand)
    return best[2]


def _contain(left: float, top: float, cw: float, ch: float,
             protect: list[tuple[int, int, int, int]],
             panel_w: int, panel_h: int) -> tuple[float, float]:
    """Shift a crop minimally so the boxes it can hold, it holds WHOLE.

    Shifting beats shrinking. Capping the zoom until a bubble fits leaves the shot
    frozen — on Solo Leveling's panels that was 57% of shots with neither pan nor zoom,
    stiller than the reference channel, whose static shots still zoom. Moving the crop a
    few dozen pixels keeps both the motion and the readable line.

    Largest box first, so when two boxes make incompatible demands the one carrying more
    text wins. Boxes too big for the crop are skipped rather than chased.
    """
    for bx, by, bw, bh in sorted(protect, key=lambda b: -b[2] * b[3]):
        if bw > cw or bh > ch:
            continue
        if bx < left:
            left = float(bx)
        elif bx + bw > left + cw:
            left = bx + bw - cw
        if by < top:
            top = float(by)
        elif by + bh > top + ch:
            top = by + bh - ch
    return (max(0.0, min(panel_w - cw, left)), max(0.0, min(panel_h - ch, top)))


def _crop_rect(offset: int, zoom: float, axis: str, win_w: int, win_h: int,
               panel_w: int, panel_h: int,
               protect: list[tuple[int, int, int, int]] | None = None,
               ) -> tuple[float, float, float, float]:
    """The rect the frame loop actually crops, for a given offset and zoom."""
    cw, ch = win_w / zoom, win_h / zoom
    if axis == "y":
        cx, cy = panel_w / 2.0, offset + win_h / 2.0
    else:
        cx, cy = offset + win_w / 2.0, panel_h / 2.0
    left = max(0.0, min(panel_w - cw, cx - cw / 2.0))
    top = max(0.0, min(panel_h - ch, cy - ch / 2.0))
    if protect:
        left, top = _contain(left, top, cw, ch, protect, panel_w, panel_h)
    return left, top, left + cw, top + ch


def _protected_boxes(
    bubbles: list[tuple[int, int, int, int]],
    legs: list[tuple[int, int]],
    axis: str,
    win_w: int,
    win_h: int,
    panel_w: int,
    panel_h: int,
) -> list[tuple[int, int, int, int]]:
    """Boxes the resting window holds whole — the ones the zoom must not take away.

    `_snap_offset` positions the WINDOW so no bubble is sliced by its edge, and the frame
    loop then crops `win/zoom` INSIDE that window: at zoom 1.12 that is ~5.5% off every
    edge, and it re-clips the bubble the snap just saved. Solo Leveling shipped a
    four-second shot of "IF ANYTHING, I'M CONFIDENT IN MY OWN SPEED." with the last line
    cut off for the whole shot, worsening as the push-in progressed. A later pass undoing
    an earlier pass's work, which is this project's dominant defect class.

    A box already half outside the window is skipped: `_snap_offset`'s fallback left it
    there on purpose, and chasing it would move the camera off the art for nothing.
    """
    def held(rect, b):
        l, t, r, bt = rect
        bx, by, bw, bh = b
        return l <= bx and t <= by and bx + bw <= r and by + bh <= bt

    offsets = sorted({o for leg in legs for o in (leg[0], (leg[0] + leg[1]) // 2, leg[1])})
    return [
        b for b in bubbles
        if any(held(_crop_rect(o, 1.0, axis, win_w, win_h, panel_w, panel_h), b)
               for o in offsets)
    ]


def _max_unclipped_zoom(
    protect: list[tuple[int, int, int, int]], win_w: int, win_h: int, z_hi: float
) -> float:
    """Largest zoom <= `z_hi` at which every protected box still FITS in the crop.

    Only fit is required, not position: `_contain` shifts the crop to hold the box. So
    the zoom is surrendered only when a box is physically too big for the zoomed frame,
    which is rare — the common case keeps its full camera move.
    """
    if not protect or z_hi <= 1.0:
        return z_hi
    fit = min(min(win_w / max(bw, 1), win_h / max(bh, 1)) for _, _, bw, bh in protect)
    return max(1.0, min(z_hi, fit))


def render_fill_frame_frames(
    panel_path: Path,
    width: int,
    height: int,
    num_frames: int,
    config: dict[str, Any],
    *,
    seed: str = "",
    prefer_art: bool = False,
) -> list[Image.Image]:
    """Salience-framed fill-frame camera: static, pan, or pan-with-reframe-cut.

    `prefer_art` picks the window carrying the most ARTWORK rather than the most gradient
    energy. It exists for the opening: gradient energy cannot tell a face from a wall of
    lettering — the spiky edges of a speech bubble are exactly the kind of contrast it
    rewards — and Solo Leveling opened on "E-RANK HUNTER." on black at t=6s because of it.
    The panel behind that frame is not text-dominant (0.231), so no panel-level rule could
    have caught it; the defect is which window the camera chose.

    - The window is the largest 16:9 rect inside the panel; the free axis is walked in
      reading order (down, or left-to-right), speed-capped like the scroll path.
    - Resting frames snap so bubbles are never edge-clipped.
    - A dwell over `video.max_dwell_seconds` becomes TWO shots on the same panel — a
      hard mid-cut to a later segment (or a closer window when there is nowhere left to
      go). This replaces the audit's 14-18s frozen holds without touching the timeline:
      frame count, and therefore A/V lock, is unchanged.
    """
    fps = int(get_nested(config, "video", "fps", default=30))
    max_px_per_sec = float(get_nested(config, "video", "max_scroll_px_per_sec", default=600.0))
    max_dwell = float(get_nested(config, "video", "max_dwell_seconds", default=7.0))
    bubble_weight = float(get_nested(config, "video", "bubble_salience_weight", default=0.40))

    panel = crop_to_content(Image.open(panel_path).convert("RGB"))
    arr = np.asarray(panel)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    bubbles = _text_boxes(arr)
    if prefer_art:
        # Content that is not lettering, measured at panel resolution where the detector
        # is validated. Blurred a little so a window is scored by the region it covers
        # rather than by individual strokes.
        from manhwa2vid.panels.regions import _text_and_content_masks, _text_norm

        text_n, content_n, _ = _text_and_content_masks(_text_norm(gray))
        art = cv2.resize((content_n & ~text_n).astype(np.float32),
                         (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR)
        sal = cv2.blur(art, (15, 15))
    else:
        sal = _salience(gray, bubbles, bubble_weight=bubble_weight)

    win_w, win_h, axis, span = _window_geometry(panel.width, panel.height, width, height)
    profile = _offset_profile(sal, axis, win_h if axis == "y" else win_w)
    win_len = win_h if axis == "y" else win_w
    max_offset = max(0, span)

    duration = num_frames / max(fps, 1)

    # The camera DRIFTS; it does not traverse. Measured against the reference channel's
    # own edit (per-shot phase correlation, 2026-08-26): it never moves more than 0.25
    # frame-heights within a shot — 0% of its shots exceed that, median 0.093, p90
    # 0.201 — and half its shots are effectively static, the motion being zoom. Our
    # previous rule panned whenever the panel was taller than 16:9, which is nearly
    # always: 93% of shots panned, 47% by more than 0.25 frame-heights (median 0.228),
    # and the video read as one long scroll. Travel is now capped at a fraction of the
    # WINDOW, so tall panels are covered by CUTTING to another window, never by sliding.
    max_pan_frac = float(get_nested(config, "video", "max_pan_frame_fraction", default=0.20))
    pan_min_seconds = float(get_nested(config, "video", "pan_min_seconds", default=1.8))
    travel_cap = int(min(max_px_per_sec * duration, max_pan_frac * win_len))
    if duration < pan_min_seconds:
        travel_cap = 0  # a short shot that also moves is the jarring combination

    # Anchor on the most salient window, then allow a small drift around it.
    legs: list[tuple[int, int]] = []  # (start_offset, end_offset)
    anchor = int(np.argmax(profile)) if len(profile) > 1 else 0
    anchor = _snap_offset(anchor, win_len, bubbles, axis, max_offset)
    if span <= max(8, int(0.08 * win_len)) or travel_cap <= 0:
        legs = [(anchor, anchor)]
    else:
        # Drift forward from the anchor (reading order), staying inside the panel.
        start = max(0, min(anchor, max_offset))
        end = _snap_offset(min(start + travel_cap, max_offset), win_len, bubbles, axis, max_offset)
        legs = [(start, max(start, end))]

    # Re-frame CUT for long dwells. With drift capped, this is now how a tall panel's
    # other content reaches the screen: jump to the best salient window at least one
    # window away from the anchor — a hard cut, the way the reference channel covers a
    # tall page. Only when no such window exists does the shot push in on itself.
    zoom_in_leg = False
    if duration > max_dwell and num_frames >= 2 * fps:
        start, end = legs[0]
        far = [
            off
            for off in range(0, max_offset + 1, max(1, win_len // 4))
            if abs(off - anchor) >= win_len * 0.75
        ]
        if far:
            second = max(far, key=lambda off: profile[min(off, len(profile) - 1)])
            second = _snap_offset(second, win_len, bubbles, axis, max_offset)
            drift = min(travel_cap, max_offset - second)
            legs = [(start, end), (second, second + max(0, drift))]
        else:
            legs = [(start, end), (end, end)]
            zoom_in_leg = True

    z0, z1 = ken_burns_params(seed or str(panel_path))
    # The zoom must not re-clip what `_snap_offset` just protected. Not applied to the
    # `closer` push-in below: that fires only when the alternative is a frozen hold over
    # `max_dwell` with nowhere left to cut to, where stillness is the worse defect.
    protect = _protected_boxes(bubbles, legs, axis, win_w, win_h, panel.width, panel.height)
    z_cap = _max_unclipped_zoom(protect, win_w, win_h, max(z0, z1))
    z0, z1 = min(z0, z_cap), min(z1, z_cap)
    frames: list[Image.Image] = []
    per_leg = [num_frames // len(legs)] * len(legs)
    per_leg[-1] += num_frames - sum(per_leg)
    for leg_idx, ((o0, o1), leg_frames) in enumerate(zip(legs, per_leg)):
        closer = zoom_in_leg and leg_idx == len(legs) - 1
        for i in range(leg_frames):
            t = i / max(leg_frames - 1, 1)
            offset = o0 + (o1 - o0) * cosine_ease(t)
            zoom = z0 + (z1 - z0) * t
            if closer:
                zoom = 1.30 + 0.05 * t  # push-in accent on the same window
            cw, ch = win_w / zoom, win_h / zoom
            if axis == "y":
                cx = panel.width / 2.0
                cy = offset + win_h / 2.0
            else:
                cx = offset + win_w / 2.0
                cy = panel.height / 2.0
            left = max(0.0, min(panel.width - cw, cx - cw / 2.0))
            top = max(0.0, min(panel.height - ch, cy - ch / 2.0))
            left, top = _contain(left, top, cw, ch, protect, panel.width, panel.height)
            # Sub-pixel. `left`/`top`/`cw`/`ch` move smoothly, so int()-ing them into a
            # crop box quantised the camera TWICE over: the origin snapped 100->100->101
            # instead of gliding, and the box WIDTH flipped between cw and cw+1 as the
            # fractional parts crossed, changing the scale factor from one frame to the
            # next. Together that is the jiggle visible on every zoom in every video.
            # resize(box=...) takes float coordinates and does crop+scale in one
            # resampling step, so neither quantisation happens.
            frames.append(
                panel.resize(
                    (width, height),
                    Image.Resampling.LANCZOS,
                    box=(left, top, left + cw, top + ch),
                )
            )
    return frames


def render_letterbox_frames(
    panel_path: Path,
    width: int,
    height: int,
    num_frames: int,
    config: dict[str, Any],
    *,
    seed: str = "",
) -> list[Image.Image]:
    """Show the panel WHOLE, centred, blurred copy filling the bars, gentle push-in.

    This is the reference channel's default look and it is measured, not assumed: its
    sharp centre band is 0.50 of frame width at the median and bars are present on 70%
    of its frames (p10 0.34, p90 0.90). Filling the frame on every shot — which this
    pipeline briefly did — sits at 0.84 median, further from the reference than the
    reference is from us.

    It also answers the scrolling complaint directly: a panel shown whole has nothing
    left to pan across. The push-in is deliberately tiny (4%) so "whole" stays true.
    """
    push = float(get_nested(config, "video", "letterbox_push_in", default=0.04))
    blur = int(get_nested(config, "video", "letterbox_blur_radius", default=20))
    panel = crop_to_content(Image.open(panel_path).convert("RGB"))

    # SUB-PIXEL, second pass 2026-08-30. The first jiggle fix (resize(box=...)) reached
    # the fill and scroll cameras but not this one, and this one is the DEFAULT for
    # tall panels — which is why the video was smooth early (the opening prefers the
    # fill camera) and jiggly later. The old loop resized the sharp panel to
    # int(round(w*scale)) per frame and centred it at (width-new_w)//2: the size
    # stepped a whole pixel every few frames and the centring hopped as the parity
    # flipped. A 4% push over 8s moves ~0.15 px/frame — every step visible.
    #
    # Instead: compose ONE supersampled canvas (blurred bars + sharp panel at its base
    # scale), then per frame sample a float window from it with resize(box=...). The
    # push-in becomes a sub-pixel zoom of a static composite; the bars zoom by <=4%
    # along with the panel, invisible on an amorphous blur.
    ss = 2
    cw, ch = width * ss, height * ss
    canvas = panel.resize((cw, ch), Image.Resampling.LANCZOS)
    canvas = canvas.filter(ImageFilter.GaussianBlur(radius=blur * ss))
    fit = min(cw / panel.width, ch / panel.height)
    sharp_w = max(1, int(round(panel.width * fit)))
    sharp_h = max(1, int(round(panel.height * fit)))
    sharp = panel.resize((sharp_w, sharp_h), Image.Resampling.LANCZOS)
    canvas.paste(sharp, ((cw - sharp_w) // 2, (ch - sharp_h) // 2))

    rng = random.Random(seed or str(panel_path))
    grow = rng.choice([True, False])

    frames: list[Image.Image] = []
    for i in range(num_frames):
        t = cosine_ease(i / max(num_frames - 1, 1))
        zoom = (1.0 + push * t) if grow else (1.0 + push * (1.0 - t))
        win_w, win_h = cw / zoom, ch / zoom
        left = (cw - win_w) / 2.0
        top = (ch - win_h) / 2.0
        frames.append(
            canvas.resize(
                (width, height),
                Image.Resampling.LANCZOS,
                box=(left, top, left + win_w, top + win_h),
            )
        )
    return frames


def render_panel_motion_frames(
    panel_path: Path,
    panel: Panel,
    width: int,
    height: int,
    num_frames: int,
    config: dict[str, Any],
    *,
    seed_salt: int | str | None = None,
    prefer_art: bool = False,
    style: str | None = None,
) -> list[Image.Image]:
    if panel.split_method == "strip":
        # A genuine continuous strip: the classic full-width crawl reads best.
        #
        # This used to route through choose_camera_mode(), which was inert: it returned
        # "scroll" whenever split_method was "strip", and the caller then AND-ed with
        # that same condition. Its aspect-ratio threshold and the Panel.camera_hint it
        # consulted could not change any routing decision — split.py only ever wrote
        # "scroll" or "auto", never the "ken_burns" the function could return.
        return render_vertical_scroll_frames(panel_path, width, height, num_frames, config)

    # `seed_salt` is the panel's position in the timeline, so a panel shown twice gets
    # two different camera moves instead of a byte-identical repeat the eye reads as a
    # glitch. Omitted (None) keeps the original panel-id-only seed, so existing
    # single-appearance renders are unchanged.
    seed = panel.id if seed_salt is None else f"{panel.id}:{seed_salt}"

    # Routing, measured against the reference channel rather than assumed. Its sharp
    # centre band is 0.50 of frame width at the median with bars on 70% of frames, so
    # SHOWING THE PANEL WHOLE IS THE DEFAULT — not a fallback. Filling the frame is
    # reserved for panels that already fit it, where the crop costs nothing.
    #
    # This is also the honest answer to "too much scrolling": a whole panel has nothing
    # left to pan across. Only panels too tall to read whole (a 16:9 fit would leave
    # them under `letterbox_min_width_fraction` of the frame) go to the fill-frame
    # camera, which covers them with capped drift and hard cuts.
    try:
        cropped = crop_to_content(Image.open(panel_path).convert("RGB"))
        pw, ph = cropped.size
    except OSError:
        pw, ph = max(panel.bbox.width, 1), max(panel.bbox.height, 1)

    frame_aspect = height / width
    aspect = ph / max(pw, 1)
    min_width_frac = float(
        get_nested(config, "video", "letterbox_min_width_fraction", default=0.32)
    )
    fits_frame = 0.85 * frame_aspect <= aspect <= 1.15 * frame_aspect
    letterbox_width_frac = frame_aspect / aspect if aspect > 0 else 1.0

    # `style` overrides the routing for LONG-HOLD segments (render.py cuts a hold
    # that outlives the shot cap into alternating close/wide treatments of the same
    # panel). "fill" is always honourable; "letterbox" falls back to fill when the
    # panel is too tall for a readable whole-panel fit — the same guard the router
    # applies to its own choice.
    if style == "fill":
        return render_fill_frame_frames(
            panel_path, width, height, num_frames, config, seed=seed, prefer_art=prefer_art
        )
    if style == "letterbox" and letterbox_width_frac >= min_width_frac:
        return render_letterbox_frames(
            panel_path, width, height, num_frames, config, seed=seed
        )
    if style == "letterbox":
        return render_fill_frame_frames(
            panel_path, width, height, num_frames, config, seed=seed, prefer_art=prefer_art
        )

    if not fits_frame and letterbox_width_frac >= min_width_frac:
        return render_letterbox_frames(
            panel_path, width, height, num_frames, config, seed=seed
        )

    return render_fill_frame_frames(
        panel_path, width, height, num_frames, config, seed=seed, prefer_art=prefer_art
    )
