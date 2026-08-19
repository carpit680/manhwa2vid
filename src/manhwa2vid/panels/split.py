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
    """Return y-coordinates of horizontal gutters (low-ink rows)."""
    row_density = 1.0 - (gray.mean(axis=1) / 255.0)
    threshold = row_density.max() * (1.0 - threshold_ratio)
    low = row_density < max(threshold, 0.02)

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


def _panel_metadata(width: int, height: int, config: dict[str, Any], *, split_method: str) -> dict[str, Any]:
    aspect = height / max(width, 1)
    scroll_threshold = float(get_nested(config, "panels", "strip_scroll_aspect", default=2.0))
    video_threshold = float(get_nested(config, "video", "strip_scroll_aspect", default=scroll_threshold))
    threshold = max(scroll_threshold, video_threshold)
    camera_hint = "scroll" if split_method == "strip" or aspect >= threshold else "auto"
    return {"aspect_ratio": round(aspect, 3), "camera_hint": camera_hint}


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
) -> Panel:
    h, w = img.shape[:2]
    crop = img[y0 : y0 + ph, 0:w]
    panel_id = f"p{page_num:04d}_{idx + 1:02d}"
    panel_path = panels_dir / f"{panel_id}.png"
    panel_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(panel_path), crop)
    meta = _panel_metadata(w, ph, config, split_method=split_method)
    ink, dark = panel_ink_stats(crop)
    return Panel(
        id=panel_id,
        page_num=page_num,
        bbox=PanelBBox(x=0, y=y0, width=w, height=ph),
        image_path=str(panel_path.relative_to(project_root)),
        confidence=confidence,
        split_method=split_method,
        aspect_ratio=meta["aspect_ratio"],
        camera_hint=meta["camera_hint"],
        ink_ratio=ink,
        dark_ratio=dark,
    )


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
            split_method=method,
        )
        for idx, (y0, ph) in enumerate(bboxes)
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
                split_method="gutter",
            )
            for idx, (y0, ph) in enumerate(bboxes)
        ]
        return PageSplitResult(
            page_num=page_num,
            panels=panels,
            confidence=0.85,
            split_method="gutter",
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
                camera_hint=meta["camera_hint"],
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

    for stale in ("panels_story_json", "excluded_panels_json", "scene_normalized_json", "scene_partial_json"):
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
