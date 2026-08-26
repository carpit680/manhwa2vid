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
