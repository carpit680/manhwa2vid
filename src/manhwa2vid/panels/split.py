"""Vertical panel splitting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw
from rich.console import Console
from rich.progress import Progress

from manhwa2vid.config import get_nested
from manhwa2vid.models import (
    PageInfo,
    Panel,
    PanelBBox,
    PageSplitResult,
    ProjectMeta,
    SourceType,
    save_json,
)

console = Console()


def _load_manifest(pages_dir: Path) -> list[PageInfo]:
    manifest = pages_dir / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return [PageInfo.model_validate(p) for p in data]


def _find_gutter_rows(gray: np.ndarray, threshold_ratio: float, min_gap: int) -> list[int]:
    """Return y-coordinates of horizontal gutters.

    A gutter is a UNIFORM band between panels — not necessarily a white one. The first
    version defined gutters as low-ink (near-white) rows, which worked until a title
    drew its pages on black: panels separated by black gutters scored as maximum ink,
    no gutter was ever found, and a 10,800px page shipped as a single scroll strip.

    A row is a gutter candidate when it is uniform two ways:
      - internally: low variance across the row (one flat color, any color), and
      - vertically: its mean barely differs from its neighbor row's.
    The ink-based test is kept as the light-page fast path; the variance test extends
    the same idea to dark and colored gutters without any per-title configuration.
    """
    row_density = 1.0 - (gray.mean(axis=1) / 255.0)
    threshold = row_density.max() * (1.0 - threshold_ratio)
    low = row_density < max(threshold, 0.02)

    # Uniformity path: flat rows (std within the row ~0) whose brightness also barely
    # changes row-to-row. Art regions — even dark ones — have texture and edges; a
    # printed gutter has neither.
    row_std = gray.std(axis=1)
    row_mean = gray.mean(axis=1)
    step = np.abs(np.diff(row_mean, prepend=row_mean[:1]))
    uniform = (row_std < 6.0) & (step < 2.0)
    low = low | uniform

    gutters: list[int] = []
    in_gap = False
    gap_start = 0
    for y, is_low in enumerate(low):
        if is_low and not in_gap:
            in_gap = True
            gap_start = y
        elif not is_low and in_gap:
            gap_len = y - gap_start
            if gap_len >= min_gap:
                gutters.append(gap_start + gap_len // 2)
            in_gap = False
    return gutters


def panel_ink_stats(img: np.ndarray) -> tuple[float, float]:
    """(ink_ratio, dark_ratio) for a BGR or grayscale image array.

    ink = fraction of pixels below near-white (gray < 245); dark = fraction below mid
    (gray < 128). Blank page-transition slivers score low on both; every legitimate story
    panel measured so far clears ink 0.32 / dark 0.24 comfortably.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return float((gray < 245).mean()), float((gray < 128).mean())


def panel_ink_stats_from_file(path: Path) -> tuple[float, float] | None:
    """Lazy backfill for panels persisted before ink stats existed."""
    img = cv2.imread(str(path))
    if img is None:
        return None
    return panel_ink_stats(img)


def white_margin_bbox(img: np.ndarray, thresh: int = 240) -> tuple[int, int, int, int] | None:
    """Tight (x, y, w, h) around non-WHITE content, or None for a blank image.

    Deliberately white-only, and named so it cannot be mistaken for
    `panels.regions.content_bbox`, which is background-aware. Two functions called
    `content_bbox` with different semantics is how a dark page ends up measured against
    a white-paper assumption. This one is correct where it is used: `is_visually_empty`
    only reaches it once a panel is already >70% near-white, and the backfill in
    panels/filter.py records a white-margin box.

    The spatial complement of `panel_ink_stats`: those are global scalars, so a panel
    that is one small drawing in a sea of white margin looks "inky enough" while the
    letterboxed frame is mostly nothing. Measured across both real projects, the median
    shown panel's content fills ~87-92% of its area — but ~48 shown panels sat under
    60%, and the whole PNG including margin was what got fit to screen.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    mask = gray < thresh
    if not mask.any():
        return None
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    y0, y1 = int(rows[0]), int(rows[-1]) + 1
    x0, x1 = int(cols[0]), int(cols[-1]) + 1
    return (x0, y0, x1 - x0, y1 - y0)


def is_visually_empty(img: np.ndarray) -> bool:
    """A panel not worth screen time: mostly white, and what remains is margin or specks.

    The global blank gate (`is_blank_panel`, ink<=0.30) cannot catch these — a small
    dense blob of text in a white field clears a global ink threshold while the frame is
    visually nothing. Calibrated against 34 measured panels the old rule shipped
    (2.5s each of near-blank screen): white>70% AND (content box under half the area OR
    the box itself under half ink) drops all 34 — including a two-finger transition
    sliver — and keeps every measured piece of real art, down to a 63%-white sparse
    action panel. Applied at ALIGN time, not split time: these panels stay in the
    inventory (they are part of the page), they just don't get shown.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    if float((gray >= 240).mean()) <= 0.70:
        return False
    box = white_margin_bbox(gray)
    if box is None:
        return True
    x, y, w, h = box
    total_h, total_w = gray.shape[:2]
    if (w * h) / (total_w * total_h) < 0.5:
        return True
    crop = gray[y : y + h, x : x + w]
    return float((crop < 240).mean()) < 0.5


def is_visually_empty_file(path: Path) -> bool:
    img = cv2.imread(str(path))
    return False if img is None else is_visually_empty(img)


def panel_visual_stats_file(path: Path) -> tuple[bool, float]:
    """(visually_empty, content_score) in one image read.

    content_score = fraction of the whole image that is content pixels inside the
    content box — i.e. how much of the frame is actually art. Used to rank key panels
    now that the story-first path has no scene-card salience: a positional spread was
    the placeholder, and it happily crowned a margin-heavy panel.
    """
    img = cv2.imread(str(path))
    if img is None:
        return False, 0.0
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    box = white_margin_bbox(gray)
    if box is None:
        return True, 0.0
    x, y, w, h = box
    total_h, total_w = gray.shape[:2]
    crop = gray[y : y + h, x : x + w]
    density = float((crop < 240).mean())
    score = (w * h) / (total_w * total_h) * density
    return is_visually_empty(gray), score


def content_bbox_from_file(
    path: Path, thresh: int = 240
) -> tuple[tuple[int, int, int, int] | None, tuple[int, int]] | None:
    """(content box or None, (image_w, image_h)) — box and size from the SAME pixels.

    The ratio consumers compute must divide by the image's own dimensions, not by
    `Panel.bbox` (page coordinates): the two can disagree after ingest rescaling, and a
    ratio mixing the coordinate spaces is silently wrong.
    """
    img = cv2.imread(str(path))
    if img is None:
        return None
    h, w = img.shape[:2]
    return white_margin_bbox(img, thresh), (w, h)


def _panel_metadata(width: int, height: int, config: dict[str, Any], *, split_method: str) -> dict[str, Any]:
    """Panel shape. `camera_hint` used to be computed here and was never consulted:
    the camera routes on `split_method == "strip"` alone."""
    return {"aspect_ratio": round(height / max(width, 1), 3)}


def _make_panel(
    img: np.ndarray,
    page_num: int,
    idx: int,
    y0: int,
    ph: int,
    panels_dir: Path,
    project_root: Path,
    config: dict[str, Any],
    *,
    confidence: float,
    split_method: str,
    x0: int = 0,
    pw: int | None = None,
) -> Panel:
    h, w = img.shape[:2]
    if pw is None:
        pw = w
    crop = img[y0 : y0 + ph, x0 : x0 + pw]
    panel_id = f"p{page_num:04d}_{idx + 1:02d}"
    panel_path = panels_dir / f"{panel_id}.png"
    panel_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(panel_path), crop)
    meta = _panel_metadata(pw, ph, config, split_method=split_method)
    ink, dark = panel_ink_stats(crop)
    return Panel(
        id=panel_id,
        page_num=page_num,
        bbox=PanelBBox(x=x0, y=y0, width=pw, height=ph),
        image_path=str(panel_path.relative_to(project_root)),
        confidence=confidence,
        split_method=split_method,
        aspect_ratio=meta["aspect_ratio"],
        ink_ratio=ink,
        dark_ratio=dark,
    )


def _merge_text_only_bands(
    img: np.ndarray, bboxes: list[tuple[int, int]], config: dict[str, Any]
) -> list[tuple[int, int]]:
    """Fold a band that is ONLY a speech bubble into the neighbouring art band.

    Gutter splitting happily emits a full-width band containing nothing but a bubble on
    the page background. Shown alone that is a wall of text on black — the user's
    report was a 4-second one in Frozen Player, and it is the same defect class as the
    collage bubbles `absorb_bubble_regions` already handles, just one level up. Merging
    it into its neighbour puts the line back on the art it belongs to; the region pass
    then re-absorbs it properly.

    The band is merged into whichever neighbour has more ink, so a bubble between two
    panels joins the busier one rather than always the one above.

    Extreme WIDE SLIVERS are folded the same way. A band under `sliver_max_aspect`
    (height/width) is either a split fragment — a 800x108 crop showing the bottom arc of
    a speech bubble, measured, and held on screen for six seconds — or a system-message
    banner. Neither wants to be its own shot: the fragment is noise, and the banner
    reads far better sitting with the art it interrupts, which is how the reference
    channel presents them. `min_panel_height` cannot catch these because it is an
    absolute pixel floor (89px on an 800-wide page) and a 108px sliver clears it; the
    signal is the SHAPE.
    """
    if not bool(get_nested(config, "panels", "regions", "enabled", default=True)):
        return bboxes
    from manhwa2vid.panels.regions import is_text_only_panel

    h, w = img.shape[:2]
    sliver_max_aspect = float(
        get_nested(config, "panels", "regions", "sliver_max_aspect", default=0.20)
    )
    bands = [list(b) for b in bboxes]
    changed = True
    while changed and len(bands) > 1:
        changed = False
        for i, (y0, ph) in enumerate(bands):
            crop = img[y0 : y0 + ph, 0:w]
            if crop.size == 0:
                continue
            is_sliver = (ph / max(w, 1)) < sliver_max_aspect
            if not is_sliver and not is_text_only_panel(crop):
                continue
            candidates = [j for j in (i - 1, i + 1) if 0 <= j < len(bands)]
            if not candidates:
                continue
            def ink(j: int) -> float:
                cy0, cph = bands[j]
                sub = img[cy0 : cy0 + cph, 0:w]
                return float(panel_ink_stats(sub)[0]) if sub.size else 0.0

            target = max(candidates, key=ink)
            ty0, tph = bands[target]
            ny0 = min(y0, ty0)
            ny1 = max(y0 + ph, ty0 + tph)
            bands[target] = [ny0, ny1 - ny0]
            bands.pop(i)
            changed = True
            break
    return [(b[0], b[1]) for b in bands]


def _expand_region_bboxes(
    img: np.ndarray,
    bboxes: list[tuple[int, int]],
    config: dict[str, Any],
) -> list[tuple[int, int, int, int, bool]]:
    """Second splitting dimension: break collage bands into their content regions.

    `_find_gutter_rows` can only separate panels stacked full-width with a uniform row
    between them. Modern webtoon pages are collages — insets of different widths
    staggered in x AND y on a flat background, bridged by speech bubbles — so a gutter
    band often contains several story panels that no horizontal cut can reach. Measured
    case: SL page 2's band 2 (720x1633) held three panels plus three bubbles and became
    the video's opening shot, a bubble on black crawled past for six seconds.

    Input is the gutter bands (y0, height); output is (x, y, w, h, from_collage) boxes —
    bands that are one continuous piece pass through at full width (False), collage
    bands are replaced by their regions (True; bubbles absorbed into their art, reading
    order preserved).
    """
    if not bool(get_nested(config, "panels", "regions", "enabled", default=True)):
        h, w = img.shape[:2]
        return [(0, y0, w, ph, False) for y0, ph in bboxes]

    from manhwa2vid.panels.regions import split_collage_regions

    h, w = img.shape[:2]
    min_height = _px(config, w, "panels", "min_panel_height", default=120)
    out: list[tuple[int, int, int, int, bool]] = []
    for y0, ph in bboxes:
        band = img[y0 : y0 + ph, 0:w]
        regions = split_collage_regions(
            band,
            tol=int(get_nested(config, "panels", "regions", "tol", default=18)),
            close_px=int(get_nested(config, "panels", "regions", "close_px", default=5)),
            min_area_frac=float(
                get_nested(config, "panels", "regions", "min_area_frac", default=0.004)
            ),
            bubble_bright_frac=float(
                get_nested(config, "panels", "regions", "bubble_bright_frac", default=0.45)
            ),
            max_regions=int(get_nested(config, "panels", "regions", "max_regions", default=6)),
            min_height=min_height,
            pad_frac=float(get_nested(config, "panels", "regions", "pad_frac", default=0.03)),
        )
        if not regions:
            out.append((0, y0, w, ph, False))
        else:
            out.extend((rx, y0 + ry, rw, rh, True) for rx, ry, rw, rh in regions)
    return out


def _bbox_has_content(img: np.ndarray, y0: int, height: int, min_ink_ratio: float = 0.06) -> bool:
    """Return False for whitespace gutters or nearly blank crops."""
    crop = img[y0 : y0 + height]
    if crop.size == 0:
        return False
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    ink_ratio = float((gray < 245).mean())
    return ink_ratio >= min_ink_ratio


def _px(config: dict[str, Any], page_width: int, *keys: str, default: int) -> int:
    """A pixel threshold from config, scaled to this page's actual width.

    Threshold values in config are calibrated at `ingest.page_width` (the ceiling every
    wider source is downscaled to). Sources narrower than the ceiling now pass through at
    native resolution, so a fixed 120px minimum that meant 11% of a 1080-wide page would
    silently mean 15% of an 800-wide one — same config, different split behavior per
    title. Scaling by actual/nominal keeps the GEOMETRY of the rule constant across
    resolutions. Nothing here is per-series: the nominal width is the config ceiling.
    """
    nominal = max(1, int(get_nested(config, "ingest", "page_width", default=1080)))
    value = int(get_nested(config, *keys, default=default))
    return max(1, round(value * page_width / nominal))


def _gutter_bboxes(img: np.ndarray, config: dict[str, Any]) -> list[tuple[int, int]]:
    h, _w = img.shape[:2]
    min_height = _px(config, _w, "panels", "min_panel_height", default=120)
    threshold = float(get_nested(config, "panels", "whitespace_threshold", default=0.92))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gutters = _find_gutter_rows(gray, threshold, min_gap=8)
    split_points = sorted(set([0] + gutters + [h]))
    bboxes: list[tuple[int, int]] = []
    for i in range(len(split_points) - 1):
        y0, y1 = split_points[i], split_points[i + 1]
        height = y1 - y0
        if height >= min_height and _bbox_has_content(img, y0, height):
            bboxes.append((y0, height))
    return bboxes


def _split_page_image(
    image_path: Path,
    page_num: int,
    panels_dir: Path,
    project_root: Path,
    config: dict[str, Any],
) -> PageSplitResult:
    img = cv2.imread(str(image_path))
    if img is None:
        raise RuntimeError(f"Failed to read page image: {image_path}")

    h, w = img.shape[:2]
    min_height = _px(config, w, "panels", "min_panel_height", default=120)
    chunk_h = _px(config, w, "panels", "fallback_chunk_height", default=800)
    overlap = _px(config, w, "panels", "fallback_overlap", default=80)
    bboxes = _gutter_bboxes(img, config)
    method = "gutter"
    confidence = 0.85 if len(bboxes) >= 2 else 0.5

    if len(bboxes) <= 1:
        method = "chunk"
        confidence = 0.4
        bboxes = []
        y = 0
        while y < h:
            height = min(chunk_h, h - y)
            if height >= min_height:
                bboxes.append((y, height))
            y += chunk_h - overlap
            if y >= h:
                break

    if not bboxes:
        bboxes = [(0, h)]
        method = "full_page"
        confidence = 0.3

    if method == "gutter":
        bboxes = _merge_text_only_bands(img, bboxes, config)
        boxes = _expand_region_bboxes(img, bboxes, config)
    else:
        boxes = [(0, y0, w, ph, False) for y0, ph in bboxes]

    panels = [
        _make_panel(
            img,
            page_num,
            idx,
            y0,
            ph,
            panels_dir,
            project_root,
            config,
            confidence=confidence,
            split_method="region" if from_collage else method,
            x0=x0,
            pw=pw,
        )
        for idx, (x0, y0, pw, ph, from_collage) in enumerate(boxes)
    ]

    return PageSplitResult(
        page_num=page_num,
        panels=panels,
        confidence=confidence,
        split_method=method,
        low_confidence=confidence < 0.5,
    )


def _split_image_hybrid(
    image_path: Path,
    page_num: int,
    panels_dir: Path,
    project_root: Path,
    config: dict[str, Any],
) -> PageSplitResult:
    img = cv2.imread(str(image_path))
    if img is None:
        raise RuntimeError(f"Failed to read page image: {image_path}")

    h, w = img.shape[:2]
    bboxes = _gutter_bboxes(img, config)

    if len(bboxes) >= 2:
        bboxes = _merge_text_only_bands(img, bboxes, config)
        boxes = _expand_region_bboxes(img, bboxes, config)
        panels = [
            _make_panel(
                img,
                page_num,
                idx,
                y0,
                ph,
                panels_dir,
                project_root,
                config,
                confidence=0.85,
                split_method="region" if from_collage else "gutter",
                x0=x0,
                pw=pw,
            )
            for idx, (x0, y0, pw, ph, from_collage) in enumerate(boxes)
        ]
        return PageSplitResult(
            page_num=page_num,
            panels=panels,
            confidence=0.85,
            split_method="gutter",
            low_confidence=False,
        )

    # No gutters found — but a gutterless page is not necessarily one continuous strip.
    # The measured worst case (FP p0004_03, 800x5682) was two scenes joined diagonally:
    # no full-width uniform row anywhere, yet plainly two pieces of content.
    boxes = _expand_region_bboxes(img, [(0, h)], config)
    if len(boxes) >= 2:
        panels = [
            _make_panel(
                img,
                page_num,
                idx,
                y0,
                ph,
                panels_dir,
                project_root,
                config,
                confidence=0.85,
                split_method="region",
                x0=x0,
                pw=pw,
            )
            for idx, (x0, y0, pw, ph, _from_collage) in enumerate(boxes)
        ]
        return PageSplitResult(
            page_num=page_num,
            panels=panels,
            confidence=0.85,
            split_method="region",
            low_confidence=False,
        )

    panel = _make_panel(
        img,
        page_num,
        0,
        0,
        h,
        panels_dir,
        project_root,
        config,
        confidence=1.0,
        split_method="strip",
    )
    return PageSplitResult(
        page_num=page_num,
        panels=[panel],
        confidence=1.0,
        split_method="strip",
        low_confidence=False,
    )


def _write_debug_overlay(page_path: Path, result: PageSplitResult, debug_dir: Path) -> None:
    debug_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(page_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    for panel in result.panels:
        b = panel.bbox
        color = (255, 80, 80) if result.low_confidence else (80, 255, 120)
        draw.rectangle([b.x, b.y, b.x + b.width, b.y + b.height], outline=color, width=4)
        draw.text((b.x + 8, b.y + 8), panel.id, fill=color)
    out = debug_dir / f"page_{result.page_num:04d}_split.png"
    img.save(out)


def _panels_one_to_one(
    page_infos: list[PageInfo],
    paths: dict[str, Path],
    config: dict[str, Any],
) -> list[Panel]:
    """Each imported image is already a panel (scanlation folder layout)."""
    panels: list[Panel] = []
    for info in page_infos:
        page_path = paths["pages"] / info.filename
        img = cv2.imread(str(page_path))
        if img is None:
            raise RuntimeError(f"Failed to read page image: {page_path}")
        h, w = img.shape[:2]
        panel_id = f"p{info.page_num:04d}_01"
        panel_path = paths["panels"] / f"{panel_id}.png"
        panel_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(panel_path), img)
        meta = _panel_metadata(w, h, config, split_method="image_file")
        ink, dark = panel_ink_stats(img)
        panels.append(
            Panel(
                id=panel_id,
                page_num=info.page_num,
                bbox=PanelBBox(x=0, y=0, width=w, height=h),
                image_path=str(panel_path.relative_to(paths["root"])),
                confidence=1.0,
                split_method="image_file",
                aspect_ratio=meta["aspect_ratio"],
                        ink_ratio=ink,
                dark_ratio=dark,
            )
        )
    return panels


def split_panels(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> list[Panel]:
    if paths["panels_json"].exists() and not force:
        data = json.loads(paths["panels_json"].read_text(encoding="utf-8"))
        console.print(f"[dim]Using cached panels ({len(data)} panels)[/]")
        return [Panel.model_validate(p) for p in data]

    for stale in ("panels_story_json", "excluded_panels_json", "scene_partial_json"):
        paths[stale].unlink(missing_ok=True)

    page_infos = _load_manifest(paths["pages"])
    split_mode = get_nested(config, "panels", "split_image_files", default="one_to_one")

    if meta.source_type == SourceType.IMAGES and meta.images_are_panels:
        all_panels: list[Panel] = []
        page_results: list[PageSplitResult] = []

        if split_mode == "one_to_one":
            all_panels = _panels_one_to_one(page_infos, paths, config)
            save_json(paths["panels_json"], all_panels)
            console.print(
                f"[green]Mapped {len(all_panels)} image files to panels[/] "
                "(scanlation layout — no splitting)"
            )
            return all_panels

        with Progress() as progress:
            task = progress.add_task("Splitting image panels", total=len(page_infos))
            for info in page_infos:
                page_path = paths["pages"] / info.filename
                if split_mode == "hybrid":
                    result = _split_image_hybrid(
                        page_path, info.page_num, paths["panels"], paths["root"], config
                    )
                else:
                    result = _split_page_image(
                        page_path, info.page_num, paths["panels"], paths["root"], config
                    )
                page_results.append(result)
                all_panels.extend(result.panels)
                _write_debug_overlay(page_path, result, paths["debug"])
                progress.advance(task)

        save_json(paths["panels_json"], all_panels)
        split_count = sum(1 for r in page_results if r.split_method == "gutter")
        strip_count = sum(1 for r in page_results if r.split_method == "strip")
        console.print(
            f"[green]Processed {len(page_infos)} images → {len(all_panels)} panels[/] "
            f"({split_count} gutter-split, {strip_count} scroll strips — see debug/)"
        )
        return all_panels

    all_panels: list[Panel] = []
    page_results: list[PageSplitResult] = []

    with Progress() as progress:
        task = progress.add_task("Splitting panels", total=len(page_infos))
        for info in page_infos:
            page_path = paths["pages"] / info.filename
            result = _split_page_image(
                page_path, info.page_num, paths["panels"], paths["root"], config
            )
            page_results.append(result)
            all_panels.extend(result.panels)
            _write_debug_overlay(page_path, result, paths["debug"])
            progress.advance(task)

    save_json(paths["panels_json"], all_panels)
    low_count = sum(1 for r in page_results if r.low_confidence)
    console.print(
        f"[green]Split {len(all_panels)} panels[/] from {len(page_infos)} pages "
        f"({low_count} low-confidence pages — see debug/)"
    )
    return all_panels
