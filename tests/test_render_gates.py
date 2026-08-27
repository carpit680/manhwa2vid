"""Gate assembly on the final surface, and the precondition that stops a bad render.

The detectors in `qa_visual` are tested elsewhere; what is pinned here is the layer that
turns measurements into PASS/WARN/FAIL, and `pipeline.run_stage(RENDER)` refusing to run
over a red upstream gate. Both audited videos shipped while script gates were FAILING —
nothing connected a failed gate to the render that published it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manhwa2vid.models import PipelineStage
from manhwa2vid.qa import QAGateFailure
from manhwa2vid.video.qa_visual import enforce_render_qa


def _metrics(**over):
    """A clean measurement set; tests override one field at a time."""
    base = {
        "frames": 100,
        "opening_luma_mean": 110.0,
        "opening_bubble_frac_max": 0.10,
        "bubble_over_20pct_frames_pct": 15.0,
        "clipped_text_frames_pct": 40.0,
        "dead_width_mean": 0.55,
        "dead_over_50pct_frames_pct": 50.0,
        "true_peak_dbtp": -1.4,
        "loudness_lufs": -15.0,
        "shots": 100,
        "cuts_per_min": 16.0,
        "shot_median_s": 2.5,
        "shot_under_1_5s_pct": 22.0,
        "shot_longest_s": 9.0,
    }
    base.update(over)
    return base


def _run(monkeypatch, tmp_path, **over):
    import manhwa2vid.video.qa_visual as qa

    monkeypatch.setattr(qa, "measure_video", lambda _v: _metrics(**over))
    paths = {"root": tmp_path}
    enforce_render_qa(Path("dummy.mp4"), paths, {"_qa_force": True})
    report = json.loads((tmp_path / "qa.render.json").read_text())
    return {g["name"]: g["status"] for g in report["gates"]}


def test_a_clean_render_passes_every_gate(monkeypatch, tmp_path):
    assert set(_run(monkeypatch, tmp_path).values()) == {"pass"}


def test_opening_on_a_black_screen_fails(monkeypatch, tmp_path):
    """Solo Leveling opened on 19 seconds of speech bubbles on black — a viewer decides
    in ten."""
    assert _run(monkeypatch, tmp_path, opening_luma_mean=8.0)["opening-shot"] == "fail"


def test_opening_on_a_giant_bubble_fails(monkeypatch, tmp_path):
    assert _run(monkeypatch, tmp_path, opening_bubble_frac_max=0.55)["opening-shot"] == "fail"


def test_true_peak_above_the_ceiling_fails(monkeypatch, tmp_path):
    """+0.30 dBTP shipped on every render for weeks and clips on transcode."""
    assert _run(monkeypatch, tmp_path, true_peak_dbtp=0.30)["true-peak"] == "fail"
    assert _run(monkeypatch, tmp_path, true_peak_dbtp=-1.5)["true-peak"] == "pass"


def test_bubble_dominance_is_report_only(monkeypatch, tmp_path):
    """The detector finds "large pale region", not "bubble".

    Audited on the FP render (2026-08-27): of 223 flagged frames, 64% carried a "bubble"
    over 40% of the frame — hospital bedding and white walls — while a frame holding a
    real "??" bubble scored 0.00. Gating on it would tune the camera away from pale
    artwork, so the number is kept as data. Pinned here so that a future band cannot be
    reintroduced without also rebuilding the detector.
    """
    for pct in (27.0, 33.0, 60.0, 100.0):
        assert _run(monkeypatch, tmp_path, bubble_over_20pct_frames_pct=pct)["bubble-dominance"] == "pass"


def test_clipped_text_tolerates_the_reference_rate(monkeypatch, tmp_path):
    """The reference measures 43.9% — a panning camera clips text as a matter of course,
    so the band must not punish the source material."""
    assert _run(monkeypatch, tmp_path, clipped_text_frames_pct=43.9)["clipped-text"] == "pass"
    assert _run(monkeypatch, tmp_path, clipped_text_frames_pct=80.0)["clipped-text"] == "fail"


def test_dead_space_is_report_only(monkeypatch, tmp_path):
    """The detector reads low-detail columns, and manhwa art is flat by style: the
    reference video scores 0.742, worse than anything we ship. Data, not a gate."""
    assert _run(monkeypatch, tmp_path, dead_width_mean=0.95)["dead-space"] == "pass"


def test_shot_rhythm_warns_when_the_edit_drifts(monkeypatch, tmp_path):
    assert _run(monkeypatch, tmp_path, shot_median_s=6.0, shot_under_1_5s_pct=0.0)["shot-rhythm"] == "warn"


# --- the render precondition ---------------------------------------------------------

def _project(tmp_path: Path) -> Path:
    """Minimal project: a timeline exists, and one upstream gate has FAILED."""
    from manhwa2vid.models import ProjectMeta, SourceLanguage, SourceType, project_paths, save_json

    paths = project_paths(tmp_path)
    for key in ("pages", "panels", "audio", "output", "debug"):
        paths[key].mkdir(parents=True, exist_ok=True)
    save_json(paths["meta"], ProjectMeta(
        slug="t", title="T", chapters="1", source_lang=SourceLanguage.EN,
        source_type=SourceType.IMAGES, source_path=str(tmp_path), pdf_path=str(tmp_path),
    ))
    paths["timeline_json"].write_text(json.dumps({"entries": [], "total_duration": 0}))
    (tmp_path / "qa.script-story-first.json").write_text(json.dumps({
        "stage": "script-story-first",
        "gates": [{"name": "dialogue-delivery", "status": "fail", "details": "", "data": {}}],
    }))
    return tmp_path


def test_render_refuses_over_a_failed_upstream_gate(tmp_path):
    from manhwa2vid.pipeline import run_stage

    with pytest.raises(QAGateFailure) as exc:
        run_stage(_project(tmp_path), PipelineStage.RENDER, preview=True)
    assert "dialogue-delivery" in str(exc.value)


def test_force_past_qa_overrides_the_refusal(tmp_path, monkeypatch):
    """The override must still reach the renderer — a gate that cannot be bypassed
    becomes a gate people delete."""
    import manhwa2vid.pipeline as pipeline_mod

    called = {}
    monkeypatch.setattr(
        pipeline_mod, "render_video",
        lambda *a, **k: called.setdefault("ran", True) or Path("out.mp4"),
    )
    run = pipeline_mod.run_stage
    run(_project(tmp_path), PipelineStage.RENDER, preview=True, force_past_qa=True)
    assert called.get("ran") is True


def test_render_without_a_timeline_is_refused(tmp_path):
    from manhwa2vid.pipeline import run_stage

    project = _project(tmp_path)
    (project / "timeline.json").unlink()
    with pytest.raises(RuntimeError, match="Timeline missing"):
        run_stage(project, PipelineStage.RENDER, preview=True)
