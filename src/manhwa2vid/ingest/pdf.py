"""PDF ingest stage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import fitz
from rich.console import Console
from rich.progress import Progress

from manhwa2vid.config import get_nested
from manhwa2vid.models import PageInfo, ProjectMeta, save_json

console = Console()


def ingest_pdf(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> list[PageInfo]:
    pages_dir = paths["pages"]
    manifest_path = pages_dir / "manifest.json"

    if manifest_path.exists() and not force:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        console.print(f"[dim]Using cached pages ({len(data)} pages)[/]")
        return [PageInfo.model_validate(p) for p in data]

    pages_dir.mkdir(parents=True, exist_ok=True)
    target_width = int(get_nested(config, "ingest", "page_width", default=1080))
    dpi_scale = float(get_nested(config, "ingest", "dpi_scale", default=2.0))

    doc = fitz.open(meta.source_path or meta.pdf_path)
    page_infos: list[PageInfo] = []

    with Progress() as progress:
        task = progress.add_task("Extracting pages", total=len(doc))
        for i, page in enumerate(doc):
            page_num = i + 1
            rect = page.rect
            scale = (target_width / rect.width) * dpi_scale
            matrix = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            filename = f"{page_num:03d}.png"
            out_path = pages_dir / filename
            pix.save(str(out_path))
            page_infos.append(
                PageInfo(
                    page_num=page_num,
                    filename=filename,
                    width=pix.width,
                    height=pix.height,
                )
            )
            progress.advance(task)

    doc.close()
    manifest_path.write_text(
        json.dumps([p.model_dump() for p in page_infos], indent=2),
        encoding="utf-8",
    )
    console.print(f"[green]Extracted {len(page_infos)} pages[/] → {pages_dir}")
    return page_infos
