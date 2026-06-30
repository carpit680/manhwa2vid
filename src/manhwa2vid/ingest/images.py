"""Image folder ingest — scanlation-style chapter directories."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from PIL import Image
from rich.console import Console
from rich.progress import Progress

from manhwa2vid.config import get_nested
from manhwa2vid.models import PageInfo, ProjectMeta, save_json

console = Console()

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def parse_chapter_range(chapters: str) -> tuple[int, int]:
    text = chapters.strip()
    if "-" in text:
        start_s, end_s = text.split("-", 1)
        return int(start_s.strip()), int(end_s.strip())
    value = int(text)
    return value, value


def extract_chapter_number(name: str) -> int | None:
    patterns = (
        r"c(\d+)\s*$",
        r"[_\s-]c(\d+)\s*$",
        r"(?:chapter|ch)[-_ ]?(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _natural_sort_key(path: Path) -> list[int | str]:
    parts = re.split(r"(\d+)", path.stem)
    key: list[int | str] = []
    for part in parts:
        key.append(int(part) if part.isdigit() else part.lower())
    return key


def iter_image_files(directory: Path) -> list[Path]:
    files = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
    return sorted(files, key=_natural_sort_key)


def discover_chapter_dirs(root: Path, chapters: str) -> list[tuple[int, Path]]:
    """Find chapter subdirectories within *root* for the requested range."""
    start, end = parse_chapter_range(chapters)
    subdirs = [p for p in root.iterdir() if p.is_dir()]

    if not subdirs:
        if iter_image_files(root):
            return [(start, root)]
        raise FileNotFoundError(f"No chapter folders or images found in {root}")

    matched: list[tuple[int, Path]] = []
    for subdir in subdirs:
        chapter_num = extract_chapter_number(subdir.name)
        if chapter_num is None:
            continue
        if start <= chapter_num <= end:
            images = iter_image_files(subdir)
            if images:
                matched.append((chapter_num, subdir))

    matched.sort(key=lambda item: item[0])
    if not matched:
        raise FileNotFoundError(
            f"No chapter folders with images found for chapters {chapters} under {root}"
        )
    return matched


def collect_source_images(root: Path, chapters: str) -> list[tuple[int, int, Path]]:
    """Return ordered (chapter_num, index_in_chapter, source_path) tuples."""
    collected: list[tuple[int, int, Path]] = []
    for chapter_num, chapter_dir in discover_chapter_dirs(root, chapters):
        for index, image_path in enumerate(iter_image_files(chapter_dir), start=1):
            collected.append((chapter_num, index, image_path))
    return collected


def normalize_image(src: Path, dest: Path, target_width: int) -> tuple[int, int]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        rgb = img.convert("RGB")
        if rgb.width != target_width:
            scale = target_width / rgb.width
            new_height = max(1, int(rgb.height * scale))
            rgb = rgb.resize((target_width, new_height), Image.Resampling.LANCZOS)
        rgb.save(dest, "PNG")
        return rgb.width, rgb.height


def ingest_images(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> list[PageInfo]:
    pages_dir = paths["pages"]
    manifest_path = pages_dir / "manifest.json"
    sources_path = pages_dir / "sources.json"

    if manifest_path.exists() and not force:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        console.print(f"[dim]Using cached pages ({len(data)} images)[/]")
        return [PageInfo.model_validate(p) for p in data]

    root = Path(meta.source_path)
    if not root.is_dir():
        raise FileNotFoundError(f"Image source directory not found: {root}")

    pages_dir.mkdir(parents=True, exist_ok=True)
    target_width = int(get_nested(config, "ingest", "page_width", default=1080))
    sources = collect_source_images(root, meta.chapters)
    page_infos: list[PageInfo] = []
    source_records: list[dict[str, Any]] = []

    with Progress() as progress:
        task = progress.add_task("Importing images", total=len(sources))
        for page_num, (chapter_num, index_in_chapter, src_path) in enumerate(sources, start=1):
            filename = f"{page_num:04d}.png"
            out_path = pages_dir / filename
            width, height = normalize_image(src_path, out_path, target_width)
            page_infos.append(
                PageInfo(
                    page_num=page_num,
                    filename=filename,
                    width=width,
                    height=height,
                )
            )
            source_records.append(
                {
                    "page_num": page_num,
                    "chapter_num": chapter_num,
                    "index_in_chapter": index_in_chapter,
                    "source_path": str(src_path.resolve()),
                }
            )
            progress.advance(task)

    manifest_path.write_text(
        json.dumps([p.model_dump() for p in page_infos], indent=2),
        encoding="utf-8",
    )
    sources_path.write_text(json.dumps(source_records, indent=2), encoding="utf-8")
    console.print(
        f"[green]Imported {len(page_infos)} images[/] from {root} "
        f"(chapters {meta.chapters}) → {pages_dir}"
    )
    return page_infos
