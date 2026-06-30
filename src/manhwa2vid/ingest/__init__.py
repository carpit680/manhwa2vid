"""Ingest stage entry points."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from manhwa2vid.models import PageInfo, ProjectMeta, SourceType


def ingest_source(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> list[PageInfo]:
    if meta.source_type == SourceType.IMAGES:
        from manhwa2vid.ingest.images import ingest_images

        return ingest_images(meta, paths, config, force=force)

    from manhwa2vid.ingest.pdf import ingest_pdf

    return ingest_pdf(meta, paths, config, force=force)
