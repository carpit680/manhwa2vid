"""The series brief-read pass: read chapters once, cache forever, feed the writer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from manhwa2vid.models import ProjectMeta, SourceType


@pytest.fixture()
def series_source(tmp_path, monkeypatch):
    """A fake source folder with chapters 0-5 plus a gap (7), and a repo root."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    src = tmp_path / "source"
    for n in [0, 1, 2, 3, 4, 5, 7]:
        d = src / f"Chapter_{n}"
        d.mkdir(parents=True)
        for i in range(3):
            Image.new("RGB", (200, 600), "white").save(d / f"{i:03d}.jpg")
    (tmp_path / "config.yaml").write_text("providers: {}\n")
    monkeypatch.setattr("manhwa2vid.story.brief.find_repo_root", lambda: tmp_path)
    meta = ProjectMeta(
        slug="t-ch1-2", title="T", chapters="1-2", source_lang="en",
        series_slug="t", source_type=SourceType.IMAGES, source_path=str(src),
    )
    return tmp_path, meta


def test_story_pass_reads_targets_and_caches(series_source, monkeypatch):
    from manhwa2vid.story import brief

    tmp_path, meta = series_source
    config = {"story": {"dense_chapters": 3, "rolling_ahead": 2, "pages_per_chapter": 2}}

    calls = {"n": 0}
    real = brief.get_stage_llm

    class CountingMock:
        def __init__(self, inner):
            self.inner = inner
        def describe_panels(self, paths, prompt):
            calls["n"] += 1
            return self.inner.describe_panels(paths, prompt)

    monkeypatch.setattr(brief, "get_stage_llm", lambda stage, cfg: CountingMock(real(stage, cfg)))
    monkeypatch.setattr(brief, "apply_stage_model", lambda llm, stage, cfg: llm)

    story_map = brief.run_story_pass(meta, {}, config)
    # dense 0-3, own range 1-2, ahead 3-4 -> targets 0,1,2,3,4 intersect disk {0..5,7} = 0..4
    assert sorted(story_map["chapters"]) == ["0", "1", "2", "3", "4"]
    assert calls["n"] == 5
    assert story_map["chapters"]["1"]["summary"]
    assert story_map["chapters"]["1"]["hook_moments"]

    # cached: a second run reads nothing new
    brief.run_story_pass(meta, {}, config)
    assert calls["n"] == 5

    # the map is on disk at series level
    from manhwa2vid.models import series_paths
    saved = json.loads(series_paths(tmp_path, "t")["story_map"].read_text())
    assert sorted(saved["chapters"]) == ["0", "1", "2", "3", "4"]


def test_story_pass_handles_gaps(series_source, monkeypatch):
    """Chapter 6 is missing on disk; 7 exists. The pass reads what is there."""
    from manhwa2vid.story import brief

    tmp_path, meta = series_source
    monkeypatch.setattr(brief, "apply_stage_model", lambda llm, stage, cfg: llm)
    config = {"story": {"dense_chapters": 9, "rolling_ahead": 9, "pages_per_chapter": 2}}
    story_map = brief.run_story_pass(meta, {}, config)
    assert "7" in story_map["chapters"]
    assert "6" not in story_map["chapters"]


def test_story_ahead_never_includes_current_or_past(series_source, monkeypatch):
    from manhwa2vid.story import brief

    tmp_path, meta = series_source
    monkeypatch.setattr(brief, "apply_stage_model", lambda llm, stage, cfg: llm)
    config = {"story": {"dense_chapters": 4, "rolling_ahead": 2, "pages_per_chapter": 2}}
    story_map = brief.run_story_pass(meta, {}, config)

    ahead = brief.story_ahead_from_map(story_map, meta)
    assert "Ch 3" in ahead and "Ch 4" in ahead
    assert "Ch 1:" not in ahead and "Ch 2:" not in ahead

    so_far = brief.story_so_far_from_map(story_map, meta)
    assert set(so_far) == {"0"}
