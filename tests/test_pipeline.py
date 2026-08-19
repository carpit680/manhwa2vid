"""End-to-end pipeline tests (mock LLM/TTS, no API keys required)."""

from __future__ import annotations

import json
import os
import struct
import wave
from pathlib import Path

import fitz
import pytest

from manhwa2vid.models import ProjectMeta, SourceLanguage, project_paths, save_json
from manhwa2vid.pipeline import init_glossary, load_project, run_all_until_review, run_stage
from manhwa2vid.models import PipelineStage
from manhwa2vid.review.checkpoints import approve_script


def _make_sample_pdf(path: Path) -> None:
    doc = fitz.open()
    for page_idx in range(2):
        page = doc.new_page(width=400, height=1200)
        y = 50
        for panel in range(3):
            rect = fitz.Rect(20, y, 380, y + 350)
            page.draw_rect(rect, color=(0.2, 0.2, 0.2), fill=(0.9, 0.85, 0.8))
            page.insert_text((40, y + 40), f"Page {page_idx + 1} Panel {panel + 1}", fontsize=14)
            page.insert_text((40, y + 80), "Hero: We must keep moving!", fontsize=11)
            y += 380
    doc.save(str(path))
    doc.close()


@pytest.fixture
def sample_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("TTS_PROVIDER", "mock")
    monkeypatch.setenv("MANHWA2VID_OCR", "0")  # no Paddle model downloads in tests

    pdf = tmp_path / "sample.pdf"
    _make_sample_pdf(pdf)

    project_dir = tmp_path / "test-recap-ch1-2"
    paths = project_paths(project_dir)
    for key in ("pages", "panels", "audio", "output", "debug"):
        paths[key].mkdir(parents=True)

    meta = ProjectMeta(
        slug="test-recap-ch1-2",
        title="Test Recap",
        chapters="1-2",
        source_lang=SourceLanguage.EN,
        pdf_path=str(pdf),
    )
    save_json(paths["meta"], meta)
    init_glossary(paths)
    return project_dir


def test_ingest_and_panels(sample_project: Path) -> None:
    run_stage(sample_project, PipelineStage.INGEST)
    run_stage(sample_project, PipelineStage.PANELS)

    paths = project_paths(sample_project)
    assert (paths["pages"] / "manifest.json").exists()
    assert paths["panels_json"].exists()
    panels = json.loads(paths["panels_json"].read_text())
    assert len(panels) >= 2


def test_full_pipeline_mock(sample_project: Path) -> None:
    run_all_until_review(sample_project)

    paths = project_paths(sample_project)
    assert paths["script_draft"].exists()
    assert paths["scene_json"].exists()
    assert paths["cast_attribution_json"].exists()
    assert paths["scene_enriched_json"].exists()

    _, paths, _, checkpoint = load_project(sample_project)
    approve_script(paths, checkpoint)

    run_stage(sample_project, PipelineStage.TTS)
    assert paths["timeline_json"].exists()

    run_stage(sample_project, PipelineStage.RENDER, preview=True)
    preview = paths["output"] / "preview.mp4"
    assert preview.exists()
    assert preview.stat().st_size > 1000

    run_stage(sample_project, PipelineStage.EXPORT)
    assert (paths["output"] / "metadata.yaml").exists()
    assert (paths["output"] / "thumbnail.png").exists()


def test_timeline_alignment(sample_project: Path) -> None:
    from manhwa2vid.models import Panel, ScriptBeat
    from manhwa2vid.video.timeline import build_timeline, audio_duration

    audio_dir = sample_project / "audio"
    audio_dir.mkdir(exist_ok=True)
    wav = audio_dir / "beat_001.wav"
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(struct.pack("<h", 0) * 48000)

    beats = [ScriptBeat(beat_id=1, panel_ids=["p001_01", "p001_02"], narration="Hello world test")]
    panels = [
        Panel(id="p001_01", page_num=1, bbox={"x": 0, "y": 0, "width": 100, "height": 100}, image_path="panels/p001_01.png"),
        Panel(id="p001_02", page_num=1, bbox={"x": 0, "y": 100, "width": 100, "height": 100}, image_path="panels/p001_02.png"),
    ]
    timeline = build_timeline(beats, panels, audio_dir, {"video": {"min_panel_seconds": 2, "max_panel_seconds": 8, "fps": 30}})
    assert len(timeline.entries) == 2
    # Visual duration must lock to audio — no min-clamp stretch past the WAV
    assert timeline.total_duration == pytest.approx(audio_duration(wav), abs=0.05)
    assert audio_duration(wav) == pytest.approx(2.0, rel=0.1)
    assert abs(sum(e.duration for e in timeline.entries) - timeline.total_duration) < 1e-6


def test_normalize_image_never_upscales(tmp_path):
    """page_width is a ceiling. An 800px-wide source must pass through at native size —
    upscaling invents no detail and blurs exactly the text the vision pass needs."""
    from PIL import Image

    from manhwa2vid.ingest.images import normalize_image

    src = tmp_path / "src.jpg"
    Image.new("RGB", (800, 4000), "white").save(src)
    w, h = normalize_image(src, tmp_path / "out.png", target_width=1080)
    assert (w, h) == (800, 4000)

    wide = tmp_path / "wide.jpg"
    Image.new("RGB", (1600, 4000), "white").save(wide)
    w, h = normalize_image(wide, tmp_path / "out2.png", target_width=1080)
    assert w == 1080 and h == 2700


def test_split_thresholds_scale_with_page_width():
    """min_panel_height etc. are calibrated at the config ceiling; on a narrower native
    page the same GEOMETRY must apply, not the same pixel count."""
    from manhwa2vid.panels.split import _px

    config = {"ingest": {"page_width": 1080}, "panels": {"min_panel_height": 120}}
    assert _px(config, 1080, "panels", "min_panel_height", default=120) == 120
    assert _px(config, 800, "panels", "min_panel_height", default=120) == 89
    assert _px(config, 2160, "panels", "min_panel_height", default=120) == 240
