"""Find the content regions inside one page image — the 2D answer to gutter splitting.

`_find_gutter_rows` cuts a page on HORIZONTAL bands: it can only separate panels that
are stacked, full width, with a uniform row between them. Modern webtoon pages are not
built that way. They are collages — inset panels of different widths floating on a flat
background at staggered offsets, with speech bubbles bridging the space between them.

Measured case that motivated this (Solo Leveling page 2, the video's opening shot):
a 720x1633 "panel" that is really three story panels — a hand on stone at x=308, a blade
at x=30 six hundred rows lower, and three bubbles. No full-width row separates any of
them, so gutter detection found exactly one cut in the whole page and shipped the
collage as a single 2.3:1 strip. The renderer then crawled down it, clipping every
inset at the frame edge; nothing was ever fully on screen.

The background is whatever colour the page border is — white paper on most titles,
black on dark chapters — so nothing here assumes white, the same lesson
`_find_gutter_rows` already learned once.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

Box = tuple[int, int, int, int]  # x, y, w, h


def background_level(gray: np.ndarray) -> int:
    """Modal brightness of the page border: the paper, whatever colour it is."""
    edge = max(1, min(4, min(gray.shape) // 4))
    border = np.concatenate(
        [
            gray[:edge].ravel(),
            gray[-edge:].ravel(),
            gray[:, :edge].ravel(),
            gray[:, -edge:].ravel(),
        ]
    )
    return int(np.bincount(border.astype(np.uint8), minlength=256).argmax())


def content_bbox(gray: np.ndarray, tol: int = 18) -> Box | None:
    """Bounding box of everything that is not page background."""
    mask = np.abs(gray.astype(np.int16) - background_level(gray)) > tol
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    if not len(rows) or not len(cols):
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1)


def _overlap_frac(a: list[int], b: list[int]) -> float:
    """Intersection area as a fraction of the SMALLER box."""
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    smaller = min(a[2] * a[3], b[2] * b[3])
    return (ix * iy) / smaller if smaller else 0.0


def _merge_nested(boxes: list[list[int]], min_overlap: float) -> list[list[int]]:
    """Union boxes only when one substantially sits INSIDE the other.

    Proximity merging is the wrong rule here and was tried first: inset panels in a
    collage are staggered diagonally, so two components that never touch can still have
    overlapping bounding boxes. Merging on that bridged the Solo Leveling hand-inset and
    blade-inset — which sit 500 rows apart — back into one blob. Connected components
    already express physical connection; this pass only cleans up a detection nested
    inside another (a bubble tail inside its panel), and small strays are folded in by
    `merge_small_regions` on the caller's own budget.
    """
    changed = True
    while changed and boxes:
        changed = False
        out: list[list[int]] = []
        for box in boxes:
            for other in out:
                if _overlap_frac(box, other) >= min_overlap:
                    x0 = min(box[0], other[0])
                    y0 = min(box[1], other[1])
                    x1 = max(box[0] + box[2], other[0] + other[2])
                    y1 = max(box[1] + box[3], other[1] + other[3])
                    other[0], other[1], other[2], other[3] = x0, y0, x1 - x0, y1 - y0
                    changed = True
                    break
            else:
                out.append(list(box))
        boxes = out
    return boxes


def detect_content_regions(
    img: np.ndarray,
    *,
    tol: int = 18,
    close_px: int = 5,
    min_area_frac: float = 0.004,
    min_overlap: float = 0.6,
) -> list[Box]:
    """Content islands on the page background, in reading order (top to bottom).

    Returns the single full-content box when the page is one continuous illustration —
    a caller can tell "collage" from "full-bleed art" by the length of this list.
    """
    if img.ndim == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    height, width = gray.shape[:2]

    mask = (np.abs(gray.astype(np.int16) - background_level(gray)) > tol).astype(np.uint8)
    if close_px > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (close_px, close_px))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    min_area = min_area_frac * height * width
    boxes = [
        [int(stats[i, 0]), int(stats[i, 1]), int(stats[i, 2]), int(stats[i, 3])]
        for i in range(1, count)
        if stats[i, 4] >= min_area
    ]
    if not boxes:
        box = content_bbox(gray, tol)
        return [box] if box else []

    boxes = _merge_nested(boxes, min_overlap)
    boxes.sort(key=lambda b: (b[1] + b[3] / 2, b[0]))
    return [(b[0], b[1], b[2], b[3]) for b in boxes]


def bubble_fraction(crop: np.ndarray) -> float:
    """Fraction of a region that is solid near-white blob — speech bubble / caption ink.

    Same detector the 2026-08-26 audit used to count bubble-dominant frames (>232
    brightness). A region that is MOSTLY this is a bare bubble, not art."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    return float((gray > 232).mean())


def is_text_only_panel(img: np.ndarray) -> bool:
    """A panel with (almost) no art: bare bubbles, SFX strokes on white, blank slivers.

    Signature measured across FP's 289 panels (2026-08-26): meaningful bright area but
    under 15% mid-tone pixels — art always carries mid-tones, text/SFX panels don't.
    Validated by eye on the 63 panels the rule selects: bubbles-on-black, sound-effect
    calligraphy, near-blank transitions; zero real art panels among them. Used to keep
    bounded fill from volunteering them (a matcher CLAIM still shows one — quoting its
    line is legitimate)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    bright = float((gray > 232).mean())
    mid = float(((gray > 40) & (gray <= 232)).mean())
    return bright > 0.2 and mid < 0.15



# --- lettering ------------------------------------------------------------------------
#
# `is_text_only_panel` above answers a TONAL question and is used on split BANDS, where
# it works. On whole panels it cannot work at all, and this was measured rather than
# assumed (2026-08-27): across FP's shown panels it flags 0 of 100, because it requires a
# large BRIGHT region and half the offending frames are white type on a black field. Nor
# can any tonal rule be made to work — after cropping to content, verified text panels
# measure mid-tone 0.013-0.051 and verified art panels 0.037-0.052, fully overlapping.
# Line art on flat fill IS tonally identical to text on flat fill.
#
# So `text_content_ratio` asks a geometric question instead: find LETTERING by its shape
# (glyph-sized ink in rows of one height and one stroke width), grow it to whatever
# bubble or caption box holds it, and report that as a fraction of the panel's
# NON-BACKGROUND pixels. A panel whose only content is text scores ~1.0 whichever way
# round the ink runs; a face with a bubble scores low, because the face is content the
# text mask does not cover.
#
# Validated on all 607 panels of both titles with every flagged panel opened by eye:
# at 0.82 it flags 10 (FP 8, SL 2), all genuine lettering, ZERO false positives. The
# labelled extremes are pinned in tests/test_regions.py — lowest true text 0.853
# ("NEVER." on black), highest true art 0.778 — so the threshold cannot be nudged into
# either class without a test going red.
#
# What it deliberately does NOT catch: title cards, credit pages and publisher logos
# (0.67-0.80). Those are the title/credit-page filter's job, and they are already
# excluded upstream. A system-message panel the narration QUOTES also stays legitimate:
# the planner uses this to stop fill VOLUNTEERING a text panel, not to forbid a matcher
# claim.

TEXT_DOMINANT = 0.82
_TEXT_NORM_W = 800  # source art is 720-800px wide; the glyph sizes below are in these units
_GLYPH_MIN_H = 7
_GLYPH_MAX_H = 70

def _text_norm(gray: np.ndarray) -> np.ndarray:
    if gray.shape[1] == _TEXT_NORM_W:
        return gray
    s = _TEXT_NORM_W / gray.shape[1]
    return cv2.resize(gray, (_TEXT_NORM_W, max(1, int(round(gray.shape[0] * s)))),
                      interpolation=cv2.INTER_AREA)


def _glyph_boxes(gray: np.ndarray):
    """Glyph-sized ink blobs with their stroke width, both polarities.

    Returns (x, y, w, h, stroke). Stroke width comes from a distance transform, which is
    what lets a row of letters be told apart from a patch of cross-hatching: lettering in
    one line is drawn with one pen.
    """
    out = []
    for polarity in (0, 1):
        img = gray if polarity == 0 else (255 - gray)
        # ADAPTIVE, not global Otsu. A white caption inside a small black box on a white
        # panel is invisible to a global threshold: Otsu splits the page into white and
        # black, so the whole caption box comes back as ONE component and its letters
        # are never isolated. Locally, the same letters are ordinary ink.
        binimg = cv2.adaptiveThreshold(
            img, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 12
        )
        dist = cv2.distanceTransform(binimg, cv2.DIST_L2, 3)
        n, lbl, stats, _c = cv2.connectedComponentsWithStats(binimg.astype(np.uint8), 8)
        for i in range(1, n):
            x, y, w, h, area = (int(v) for v in stats[i])
            if not (_GLYPH_MIN_H <= h <= _GLYPH_MAX_H and 2 <= w <= 90):
                continue
            if not (0.12 <= w / h <= 4.0):
                continue
            if not (0.10 <= area / max(w * h, 1) <= 0.95):
                continue
            sub = dist[y:y + h, x:x + w][lbl[y:y + h, x:x + w] == i]
            if not sub.size:
                continue
            out.append((x, y, w, h, float(2.0 * sub.max())))
    return out


def _text_lines(boxes, shape):
    """Group glyph boxes into rows, keeping only rows that behave like LETTERING.

    Adjacency alone is not enough once glyph finding is adaptive: artwork detail forms
    plenty of accidental rows. Real lettering in one line shares a height and a stroke
    width, so both are required to be consistent, and the row must be wider than it is
    tall.
    """
    lines = []
    boxes = sorted(boxes, key=lambda b: (b[1] + b[3] / 2, b[0]))
    used = [False] * len(boxes)
    for i, b in enumerate(boxes):
        if used[i]:
            continue
        cy, h = b[1] + b[3] / 2, b[3]
        row = [i]
        for j in range(i + 1, len(boxes)):
            c = boxes[j]
            # Boxes are sorted by vertical centre and a row admits at most
            # 0.45 * max(h) of drift, so once we are past that bound no LATER box can
            # join either. Without the break this is O(n^2), and a 22000px-tall strip
            # carries tens of thousands of glyph-sized components: the camera tests on
            # extreme strips went from 0.4s to 30s each. The bound uses the largest
            # glyph the finder accepts, so the grouping is byte-identical.
            if (c[1] + c[3] / 2) - cy > 0.45 * _GLYPH_MAX_H:
                break
            if used[j]:
                continue
            if abs((c[1] + c[3] / 2) - cy) > 0.45 * max(h, c[3]):
                continue
            if abs(c[3] - h) > 0.75 * max(h, c[3]):
                continue
            row.append(j)
        if len(row) < 3:
            continue
        xs = sorted((boxes[k] for k in row), key=lambda b: b[0])
        keep = [xs[0]]
        for prev, cur in zip(xs, xs[1:]):
            if cur[0] - (prev[0] + prev[2]) <= 2.5 * max(prev[3], cur[3]):
                keep.append(cur)
        if len(keep) < 3:
            continue
        hs = np.array([k[3] for k in keep], float)
        sw = np.array([k[4] for k in keep], float)
        if hs.mean() <= 0 or hs.std() / hs.mean() > 0.30:
            continue  # one line of type is set in one size
        if sw.mean() <= 0 or sw.std() / sw.mean() > 0.45:
            continue  # ...and drawn with one pen
        x0 = min(k[0] for k in keep); y0 = min(k[1] for k in keep)
        x1 = max(k[0] + k[2] for k in keep); y1 = max(k[1] + k[3] for k in keep)
        if (x1 - x0) < 1.2 * (y1 - y0):
            continue  # a line of text is wider than it is tall
        lines.append((x0, y0, x1 - x0, y1 - y0))
        for k in row:
            used[k] = True
    return lines


def _text_and_content_masks(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(lettering-with-its-container, everything-that-is-not-page-ground), same shape.

    Split out of `text_content_ratio` so the CAMERA can use the same regions the panel
    test uses. `effects` needs the boxes, not the fraction: a window chosen inside a tall
    panel can be entirely bubble even when the panel as a whole is mostly art.
    """
    bg = background_level(gray)
    content = np.abs(gray.astype(np.int16) - bg) > 18
    empty = np.zeros(gray.shape, bool)
    if int(content.sum()) < 200:
        return empty, content

    glyphs = _glyph_boxes(gray)
    lines = _text_lines(glyphs, gray.shape)
    if not lines:
        return empty, content

    # Every glyph, not just the ones that grouped into a line. Flatness of a container is
    # measured with ALL lettering removed: a caption box holds more type than one grouped
    # row, and the leftover letters read as texture and fail the flatness test.
    ink = np.zeros(gray.shape, bool)
    for (gx, gy, gw, gh, _sw) in glyphs:
        ink[max(0, gy - 2):gy + gh + 2, max(0, gx - 2):gx + gw + 2] = True

    text = np.zeros_like(content)
    # The container search below depends only on the sampled TONE, and a panel's lines
    # nearly all sit on the same white. Recomputing connected components per LINE made
    # the camera tests on tall strips take 30s each; caching by tone is a pure
    # optimisation with no effect on the result.
    comps: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    # a bubble/caption is a connected region of near-uniform tone that HOLDS a text line
    flat = cv2.morphologyEx(
        ((np.abs(gray.astype(np.int16) - bg) > 18).astype(np.uint8)), cv2.MORPH_CLOSE,
        np.ones((3, 3), np.uint8))
    for (x, y, w, h) in lines:
        pad = max(2, int(0.35 * h))
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(gray.shape[1], x + w + pad), min(gray.shape[0], y + h + pad)
        text[y0:y1, x0:x1] = True
        # Grow to the enclosing bubble/caption box. Seed from the RING around the text
        # line, never its centre: the centre of "WHAT?!" lands inside a letter, and the
        # enclosed white counter of a glyph is a 114px blob, not the bubble.
        ring = np.ones(gray.shape, bool)
        ring[y0:y1, x0:x1] = False
        band = np.zeros(gray.shape, bool)
        # A THIN ring just outside the padded text box: sample the bubble's own
        # interior, not the world around it. Too wide and the ring on a small caption
        # box is mostly the dark panel ground, the container grows to the whole panel,
        # and a hooded figure gets reported as text. The band must be strictly larger
        # than the hole `text[y0:y1, x0:x1]` punches, or the ring comes out EMPTY and
        # no container is ever found.
        rp = max(4, int(1.1 * h))
        band[max(0, y - rp):min(gray.shape[0], y + h + rp),
             max(0, x - rp):min(gray.shape[1], x + w + rp)] = True
        ring &= band
        px = gray[ring]
        if px.size < 50:
            continue
        # Modal tone of the ring EXCLUDING the page ground. A caption box only slightly
        # bigger than its lettering leaves a ring that is mostly the page, so the plain
        # mode returns the ground and the box is never found ("THAT I KNEW VERY WELL.",
        # white type in a small black box on a white panel).
        px = px[np.abs(px.astype(np.int16) - bg) > 18]
        if px.size < 50:
            continue  # the text sits directly on the page ground: no container to grow
        tone = int(np.bincount(px.astype(np.uint8), minlength=256).argmax())
        if tone not in comps:
            same = (np.abs(gray.astype(np.int16) - tone) < 30).astype(np.uint8)
            _n, _lbl, _stats, _c = cv2.connectedComponentsWithStats(same, 8)
            comps[tone] = (_lbl, _stats)
        lbl, stats = comps[tone]
        seeds = lbl[ring & (np.abs(gray.astype(np.int16) - tone) < 15)]
        seeds = seeds[seeds > 0]
        if not seeds.size:
            continue
        lab = int(np.bincount(seeds).argmax())
        # A bubble is a BOUNDED object. Without this the container can be the panel's
        # own ground, which swallows the art and reports every dark panel as text.
        if stats[lab][4] >= 0.45 * gray.size:
            continue
        bx, by, bw, bh, _a = (int(v) for v in stats[lab])
        if bw >= gray.shape[1] * 0.99 and bh >= gray.shape[0] * 0.99:
            continue
        # A container CONTAINS its text. Without this, any nearby flat region can be
        # adopted as the bubble for a line it does not actually hold.
        if not (bx - 2 <= x and by - 2 <= y and bx + bw + 2 >= x + w and by + bh + 2 >= y + h):
            continue
        # The container's interior must be FLAT. This is what separates a bubble from a
        # region of artwork that merely happens to have SFX lettering painted on it —
        # the failure that made a woman's face, a bottle and two insets score 0.98+.
        # Measured on FP: real bubble interiors std 0.4-5.0 (the jagged "WHAT?!"
        # starburst is the worst at 5.0), art-grown containers 6.6-17.3.
        # ERODE before measuring flatness. On a small container the anti-aliased rim
        # against the page is a fifth of its own area, and that gradient alone reads as
        # texture: the black caption box holding "THAT I KNEW VERY WELL." measured std
        # 8.6 from its edge pixels while its surface is perfectly flat.
        core = cv2.erode((lbl == lab).astype(np.uint8), np.ones((5, 5), np.uint8), 1)
        interior = core.astype(bool) & ~ink
        interior[y0:y1, x0:x1] = False
        if interior.sum() >= 100 and float(gray[interior].std()) >= 6.0:
            continue
        blob = (lbl == lab).astype(np.uint8)
        # CONVEX HULL, not the raw blob: a jagged "WHAT?!" starburst is one bubble whose
        # spikes radiate away from the core, and the raw blob leaves the gaps between
        # spikes counted as art. The hull of an ordinary oval bubble is the oval, so
        # this costs nothing on the common case.
        cnts, _hh = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if cnts:
            hull = cv2.convexHull(max(cnts, key=cv2.contourArea))
            hull_area = cv2.contourArea(hull)
            # The HULL needs its own bounds, not just the blob's. A thin dark shape
            # snaking across a panel has a small blob and an enormous hull, which is how
            # a caption over artwork swallowed whole Solo Leveling panels. A bubble is
            # BOUNDED and CONVEX; measured, real bubbles hull 6.9-32.1% of the panel at
            # solidity 0.49-0.91 (the jagged starburst is the extreme on both), while
            # art-grown containers ran 47.3-76.3% at solidity 0.08-0.36.
            if hull_area >= 0.40 * gray.size:
                continue
            if float(blob.sum()) / max(hull_area, 1.0) < 0.42:
                continue
            filled = np.zeros_like(blob)
            cv2.drawContours(filled, [hull], -1, 1, -1)
            # A bubble's HULL IS THE BUBBLE. What the hull adds beyond the blob must be
            # empty ground, not artwork: SFX lettering painted on a flat colour field
            # inside a panel makes that field look exactly like a bubble, and its hull
            # then swallows the drawing sitting on it (a boy's face scored 0.83 this
            # way). The starburst passes because the gaps between its spikes are the
            # black page, which is not content.
            gap = (filled.astype(bool) & ~blob.astype(bool) & ~ink).astype(np.uint8)
            # Erode: the anti-aliased rim between a white bubble and a black page is
            # non-background by definition, so an un-eroded rim reads as "art in the
            # hull" and rejects every genuine bubble. And the gap must be a real share
            # of the hull, not a hairline.
            gap = cv2.erode(gap, np.ones((5, 5), np.uint8), 1).astype(bool)
            if gap.sum() > 0.08 * hull_area and float(content[gap].mean()) > 0.15:
                continue
            text |= filled.astype(bool)

    return text, content


def text_content_ratio(img: np.ndarray) -> float:
    """Fraction of the panel's non-background content that is lettering or its container."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    text, content = _text_and_content_masks(_text_norm(gray))
    total = int(content.sum())
    if total < 200:
        return 1.0  # nothing here at all
    return float((text & content).sum() / total)


def text_regions(img: np.ndarray) -> list[Box]:
    """Boxes of the lettering (and the bubbles holding it), in the INPUT's coordinates.

    The camera's own bubble finder is the tonal one this module documents as unusable,
    and the cost was visible: a jagged "WHAT?!" starburst is not a solid bright blob, so
    it was never down-weighted, and its very high gradient energy actively ATTRACTED the
    window. Feeding these regions into salience instead points the camera at art.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    norm = _text_norm(gray)
    text, _content = _text_and_content_masks(norm)
    if not text.any():
        return []
    n, _lbl, stats, _c = cv2.connectedComponentsWithStats(text.astype(np.uint8), 8)
    sx = gray.shape[1] / norm.shape[1]
    sy = gray.shape[0] / norm.shape[0]
    out: list[Box] = []
    for i in range(1, n):
        x, y, w, h, _area = (int(v) for v in stats[i])
        out.append((int(x * sx), int(y * sy), max(1, int(w * sx)), max(1, int(h * sy))))
    return out



def is_text_dominant_panel(img: np.ndarray, threshold: float = TEXT_DOMINANT) -> bool:
    """Is everything a viewer can see in this panel just lettering?"""
    return text_content_ratio(img) >= threshold


def is_content_free(img: np.ndarray) -> bool:
    """A panel with nothing a viewer can read as story: not blank, not text — just void.

    The classes this catches, all four found by the user in a finished render:
      * a dark field with two or three thin slivers of a blade (coverage 0.08)
      * a single blown-up sound-effect glyph (coverage 0.14, orientation entropy 0.70)
      * speed lines / motion streaks (entropy 0.28 — every edge points the same way)
      * flat colour bands left over from a split

    Two measured signals separate them from real art with no overlap, checked across
    every story panel in both projects (FP 24/210, SL 18/350 flagged, and reading all
    of them found zero real art):
      * CONTENT COVERAGE — art panels measured 0.32-0.85, these 0.06-0.19
      * EDGE-ORIENTATION ENTROPY — art panels 0.865-0.985 because drawings point every
        way; speed lines and single glyphs are orientation-poor.

    Deliberately NOT a beauty test. It answers "is there anything here at all", which is
    why the thresholds sit far below the weakest real art rather than near it.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    if gray.size == 0:
        return True
    coverage = float((np.abs(gray.astype(np.int16) - background_level(gray)) > 18).mean())
    if coverage < 0.15:
        return True

    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.hypot(gx, gy)
    strong = magnitude > np.percentile(magnitude, 90)
    if strong.sum() <= 50:
        return True
    angles = (np.arctan2(gy, gx) % np.pi)[strong]
    hist, _edges = np.histogram(angles, bins=12, range=(0.0, np.pi))
    probs = hist / hist.sum()
    probs = probs[probs > 0]
    entropy = float(-(probs * np.log2(probs)).sum()) / np.log2(12)
    return entropy < 0.72


def is_content_free_file(path: Path) -> bool:
    img = cv2.imread(str(path))
    return False if img is None else is_content_free(img)


def absorb_bubble_regions(
    img: np.ndarray, regions: list[Box], *, bright_frac: float = 0.45
) -> list[Box]:
    """Union bare-bubble regions into their nearest art region.

    A speech bubble floating on the page background comes out of connected components
    as its own region; shown alone it is the audit's worst defect class (SL's opening:
    19 seconds of bubbles on black). Folding it into the nearest art region keeps the
    dialogue attached to the moment it belongs to. If EVERY region is a bubble the
    caller gets them back untouched — a text-only page is one panel, not zero.
    """
    art: list[list[int]] = []
    bubbles: list[list[int]] = []
    for x, y, w, h in regions:
        crop = img[y : y + h, x : x + w]
        (bubbles if bubble_fraction(crop) >= bright_frac else art).append([x, y, w, h])
    if not art or not bubbles:
        return regions
    for b in bubbles:
        bcx, bcy = b[0] + b[2] / 2, b[1] + b[3] / 2
        target = min(
            art, key=lambda a: (a[0] + a[2] / 2 - bcx) ** 2 + (a[1] + a[3] / 2 - bcy) ** 2
        )
        x0, y0 = min(b[0], target[0]), min(b[1], target[1])
        x1 = max(b[0] + b[2], target[0] + target[2])
        y1 = max(b[1] + b[3], target[1] + target[3])
        target[0], target[1], target[2], target[3] = x0, y0, x1 - x0, y1 - y0
    art = _merge_nested(art, 0.6)
    art.sort(key=lambda b: (b[1] + b[3] / 2, b[0]))
    return [(b[0], b[1], b[2], b[3]) for b in art]


def split_collage_regions(
    img: np.ndarray,
    *,
    tol: int = 18,
    close_px: int = 5,
    min_area_frac: float = 0.004,
    bubble_bright_frac: float = 0.45,
    max_regions: int = 6,
    min_height: int = 120,
    pad_frac: float = 0.03,
) -> list[Box] | None:
    """The split stage's question: is this crop a collage, and if so, what are its panels?

    Returns None when the crop is one continuous piece (or all bubbles) — the caller
    keeps it whole. Otherwise returns ≥2 padded boxes in reading order, bubbles absorbed
    into their art, small strays folded, count capped.
    """
    height, width = img.shape[:2]
    regions = detect_content_regions(
        img, tol=tol, close_px=close_px, min_area_frac=min_area_frac
    )
    if len(regions) < 2:
        return None
    if all(
        bubble_fraction(img[y : y + h, x : x + w]) >= bubble_bright_frac
        for x, y, w, h in regions
    ):
        return None  # a text-only band is one panel, not several bubbles
    regions = absorb_bubble_regions(img, regions, bright_frac=bubble_bright_frac)
    # Fold undersized strays — BOTH axes: a 58px-wide SFX scrap is no more a panel than
    # a 58px-tall one (observed on FP page 5, which emitted a 58x104 "panel" when only
    # height was checked). Then cap the count.
    while len(regions) > 1 and min(min(r[2], r[3]) for r in regions) < min_height:
        regions = merge_small_regions(regions, len(regions) - 1)
    regions = merge_small_regions(regions, max_regions)
    if len(regions) < 2:
        return None
    out: list[Box] = []
    for x, y, w, h in regions:
        pad_x, pad_y = int(w * pad_frac), int(h * pad_frac)
        x0, y0 = max(0, x - pad_x), max(0, y - pad_y)
        x1, y1 = min(width, x + w + pad_x), min(height, y + h + pad_y)
        out.append((x0, y0, x1 - x0, y1 - y0))
    return out


def merge_small_regions(regions: list[Box], keep: int) -> list[Box]:
    """Reduce to at most `keep` regions by folding the smallest into its nearest neighbour.

    This is what stops a bare speech bubble becoming its own shot: a bubble is a small
    region, so it is absorbed by the panel it belongs to rather than filling the screen
    on its own. Reading order is preserved because a union only ever spans neighbours.
    """
    boxes = [list(r) for r in regions]
    while len(boxes) > max(1, keep):
        smallest = min(range(len(boxes)), key=lambda i: boxes[i][2] * boxes[i][3])
        neighbours = [i for i in (smallest - 1, smallest + 1) if 0 <= i < len(boxes)]
        target = min(neighbours, key=lambda i: boxes[i][2] * boxes[i][3])
        a, b = boxes[smallest], boxes[target]
        x0, y0 = min(a[0], b[0]), min(a[1], b[1])
        x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
        boxes[target] = [x0, y0, x1 - x0, y1 - y0]
        boxes.pop(smallest)
    return [(b[0], b[1], b[2], b[3]) for b in boxes]
