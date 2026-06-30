"""Image folder ingest tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from manhwa2vid.ingest.images import (
    collect_source_images,
    discover_chapter_dirs,
    extract_chapter_number,
    ingest_images,
    parse_chapter_range,
)
from manhwa2vid.models import ProjectMeta, SourceLanguage, SourceType, project_paths, save_json
from manhwa2vid.pipeline import run_stage
from manhwa2vid.models import PipelineStage


def _write_png(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (600, 700), color).save(path)


@pytest.fixture
def scanlation_root(tmp_path: Path) -> Path:
    for chapter, color in ((1, (255, 0, 0)), (2, (0, 255, 0)), (3, (0, 0, 255))):
        chapter_dir = tmp_path / f"[Group]_Series_c{chapter:02d}"
        for index in range(1, 4):
            _write_png(chapter_dir / f"{index:03d}.png", color)
    return tmp_path


def test_parse_chapter_range() -> None:
    assert parse_chapter_range("1-10") == (1, 10)
    assert parse_chapter_range("5") == (5, 5)


def test_extract_chapter_number() -> None:
    assert extract_chapter_number("[Jaimini's_Box_]Solo_Leveling_c01") == 1
    assert extract_chapter_number("Solo_Leveling_c82") == 82


def test_discover_chapter_dirs(scanlation_root: Path) -> None:
    found = discover_chapter_dirs(scanlation_root, "1-2")
    assert [num for num, _ in found] == [1, 2]


def test_collect_source_images(scanlation_root: Path) -> None:
    images = collect_source_images(scanlation_root, "1-2")
    assert len(images) == 6
    assert images[0][0] == 1
    assert images[-1][0] == 2


def test_image_project_ingest_and_panels(scanlation_root: Path) -> None:
    project_dir = scanlation_root / "project"
    paths = project_paths(project_dir)
    for key in ("pages", "panels", "audio", "output", "debug"):
        paths[key].mkdir(parents=True)

    meta = ProjectMeta(
        slug="solo-leveling-ch1-2",
        title="Solo Leveling",
        chapters="1-2",
        source_lang=SourceLanguage.EN,
        source_type=SourceType.IMAGES,
        source_path=str(scanlation_root),
        images_are_panels=True,
    )
    save_json(paths["meta"], meta)

    run_stage(project_dir, PipelineStage.INGEST)
    run_stage(project_dir, PipelineStage.PANELS)

    pages = json.loads((paths["pages"] / "manifest.json").read_text())
    panels = json.loads(paths["panels_json"].read_text())
    assert len(pages) == 6
    assert len(panels) == 6
    assert panels[0]["split_method"] in ("strip", "gutter", "image_file")
    assert "aspect_ratio" in panels[0]
