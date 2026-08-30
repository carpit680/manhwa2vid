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
        "opening_lettering_max": 0.20,
        "opening_art_min_second": 0.45,
        "lettering_over_30pct_frames_pct": 12.0,
        "bare_bubble_frames_pct": 0.0,
        "bubble_over_20pct_frames_pct": 15.0,
        "clipped_text_frames_pct": 40.0,
        "dead_width_mean": 0.55,
        "dead_over_50pct_frames_pct": 50.0,
        "true_peak_dbtp": -1.4,
        "loudness_lufs": -14.5,
        "loudness_range_lu": 2.5,
        "quiet_floor_dbfs": -30.0,
        "tonality_ratio": 7.0,
        "duck_depth_db": 13.5,
        "duck_depth_estimate_db": 21.9,
        "shots": 100,
        "cuts_per_min": 16.0,
        "shot_median_s": 2.5,
        "shot_under_1_5s_pct": 22.0,
        "shot_longest_s": 9.0,
        "shot_over_8s_runtime_pct": 15.0,
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


def test_opening_is_not_failed_by_the_frame_lettering_detector(monkeypatch, tmp_path):
    """It read a blood-spattered stone wall in Solo Leveling's opening at 0.736 lettering
    — there is no text in that frame at all. Texture reads as glyph rows at frame scale
    (audit §7), which is why lettering-share and bare-bubble are report-only; gating on
    the same number here contradicted that."""
    r = _run(monkeypatch, tmp_path, opening_lettering_max=0.74, opening_art_min_second=0.26)
    assert r["opening-shot"] == "pass"


def test_opening_gate_ignores_the_bright_blob_measure(monkeypatch, tmp_path):
    """It read the Frost Queen's pale hair as a 34%-of-frame "bubble" and failed an
    opening whose lettering had in fact dropped from 48% to 30%. The blob number is
    still recorded; it no longer decides anything."""
    r = _run(monkeypatch, tmp_path, opening_bubble_frac_max=0.90, opening_lettering_max=0.28)
    assert r["opening-shot"] == "pass"


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


def test_clipped_text_is_report_only(monkeypatch, tmp_path):
    """Re-measured 2026-08-28 with the validated lettering detector: the REFERENCE slices
    lettering on 67.5-69.8% of its frames against our 45.3%/56.5%. It is worse at this
    than we are, and the brief's proposed 10% ceiling is unreachable for anyone — panning
    a 16:9 window over tall bubbled art clips lettering as a matter of course."""
    for pct in (43.9, 56.5, 80.0):
        assert _run(monkeypatch, tmp_path, clipped_text_frames_pct=pct)["clipped-text"] == "pass"


def test_composition_measures_are_reported_not_gated(monkeypatch, tmp_path):
    """The geometric detector is validated on PANELS at source resolution and that does
    not transfer to frames: a brick wall with no text measures 0.615 and a crowd on rock
    0.818, against 0.402 for a real bubble. Pinned so a future edit cannot quietly promote
    them without validating a frame-level detector first."""
    r = _run(monkeypatch, tmp_path, lettering_over_30pct_frames_pct=95.0,
             bare_bubble_frames_pct=50.0)
    assert r["lettering-share"] == "pass" and r["bare-bubble"] == "pass"


def test_opening_art_floor_separates_the_defect_from_dark_artwork(monkeypatch, tmp_path):
    """Both sides, measured on real frames.

    Defect: Solo Leveling opening on "E-RANK HUNTER." on black — 0.054 art.
    Not a defect: Frozen Player's Frost Queen crown against a dark ground — 0.13. That
    is a strong atmospheric shot, and a floor of 0.15 (the reference's window minimum,
    chosen with no negative example) failed it.
    """
    assert _run(monkeypatch, tmp_path, opening_art_min_second=0.054)["opening-shot"] == "fail"
    assert _run(monkeypatch, tmp_path, opening_art_min_second=0.13)["opening-shot"] == "pass"
    assert _run(monkeypatch, tmp_path, opening_art_min_second=0.283)["opening-shot"] == "pass"


def test_opening_art_floor_does_not_fail_the_reference(monkeypatch, tmp_path):
    """The brief proposed 50% detail-bearing area every second. The reference's own
    per-second minimum is 26.2%."""
    from manhwa2vid.video.qa_visual import _OPENING_ART_FAIL

    assert _OPENING_ART_FAIL < 0.262, "the floor must sit below the reference's own minimum"
    assert _run(monkeypatch, tmp_path, opening_art_min_second=0.262)["opening-shot"] == "pass"


def test_dead_space_is_report_only(monkeypatch, tmp_path):
    """The detector reads low-detail columns, and manhwa art is flat by style: the
    reference video scores 0.742, worse than anything we ship. Data, not a gate."""
    assert _run(monkeypatch, tmp_path, dead_width_mean=0.95)["dead-space"] == "pass"


def test_rhythm_gates_are_named_not_one_blob(monkeypatch, tmp_path):
    """`shot-rhythm` reported one verdict over three unrelated numbers, so a slow edit and
    a strobing one were indistinguishable in `status`. Split per the hardening brief."""
    r = _run(monkeypatch, tmp_path, shot_median_s=6.0, shot_under_1_5s_pct=0.0)
    assert r["shot-median"] == "warn" and r["shot-accent-share"] == "warn"
    assert "shot-rhythm" not in r


def test_shot_max_duration_band_does_not_fail_the_reference(monkeypatch, tmp_path):
    """The brief proposed failing over 12s. The reference channel's OWN longest shot is
    16.37s, so 12s would fail the video being imitated. Warn at 12, fail at 18."""
    assert _run(monkeypatch, tmp_path, shot_longest_s=16.37)["shot-max-duration"] == "warn"
    assert _run(monkeypatch, tmp_path, shot_longest_s=27.77)["shot-max-duration"] == "fail"
    assert _run(monkeypatch, tmp_path, shot_longest_s=9.0)["shot-max-duration"] == "pass"


def test_longtail_band_does_not_fail_the_reference(monkeypatch, tmp_path):
    """The brief proposed 15% of runtime in shots over 8s. The reference reaches 22.2%."""
    assert _run(monkeypatch, tmp_path, shot_over_8s_runtime_pct=22.2)["shot-longtail-share"] == "warn"
    assert _run(monkeypatch, tmp_path, shot_over_8s_runtime_pct=28.1)["shot-longtail-share"] == "fail"
    assert _run(monkeypatch, tmp_path, shot_over_8s_runtime_pct=14.0)["shot-longtail-share"] == "pass"


def test_cadence_band_admits_the_references_own_fastest_window(monkeypatch, tmp_path):
    """The brief said 12-20 cuts/min; the reference's W1 measures 20.08."""
    assert _run(monkeypatch, tmp_path, cuts_per_min=20.08)["shot-cadence"] == "pass"
    assert _run(monkeypatch, tmp_path, cuts_per_min=8.0)["shot-cadence"] == "warn"


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


# --- audio gates (docs/audio-quality-spec.md §6) ---------------------------------------

def test_true_peak_ceiling_is_the_tightened_one(monkeypatch, tmp_path):
    """The spec tightens -0.8 to -1.0. Measured -1.35/-1.32, so it costs nothing today
    and catches a regression."""
    assert _run(monkeypatch, tmp_path, true_peak_dbtp=-1.35)["true-peak"] == "pass"
    assert _run(monkeypatch, tmp_path, true_peak_dbtp=-0.9)["true-peak"] == "fail"


def test_loudness_is_judged_against_the_configured_target_not_a_constant(monkeypatch, tmp_path):
    """-16.4 LUFS is the pipeline's UNDERSHOOT, not its intent: loudnorm in linear mode
    will not apply gain that would breach TP -1.5. The spec proposed a -16 +/- 1 band,
    which would codify the bug and FAIL a future render that fixes it."""
    assert _run(monkeypatch, tmp_path, loudness_lufs=-14.0)["audio-loudness"] == "pass"
    assert _run(monkeypatch, tmp_path, loudness_lufs=-16.4)["audio-loudness"] == "warn"
    assert _run(monkeypatch, tmp_path, loudness_lufs=-20.0)["audio-loudness"] == "fail"
    assert _run(monkeypatch, tmp_path, loudness_lufs=-11.0)["audio-loudness"] == "fail"


def test_bed_separation_band_is_field_derived(monkeypatch, tmp_path):
    """Renamed from audio-duck-depth: sidechain ducking is off by default now, so
    "duck depth" no longer describes the chain — but voice-to-bed SEPARATION matters
    either way, and a constant bed has it too.

    Band is the corpus: 13.0-35.7 dB across twelve competitor videos, median 21.9.
    Judged on the estimate metric because competitors ship no narration stem, so it is
    the only value computable on both sides."""
    run = lambda **kw: _run(monkeypatch, tmp_path, **kw)["audio-bed-separation"]  # noqa: E731
    assert run(duck_depth_estimate_db=21.9) == "pass", "field median must pass"
    assert run(duck_depth_estimate_db=26.2) == "pass", "our own render must pass"
    assert run(duck_depth_estimate_db=13.0) == "pass", "field minimum must pass"
    assert run(duck_depth_estimate_db=35.7) == "pass", "field maximum must pass"
    assert run(duck_depth_estimate_db=6.0) == "warn", "bed competing with the voice"
    assert run(duck_depth_estimate_db=45.0) == "warn", "bed effectively absent"


def test_music_present_floor_accepts_the_field_and_still_catches_absence(monkeypatch, tmp_path):
    """The old -40 dBFS floor failed NINE of twelve field videos, Mamoru's 5.2M among
    them — it codified our own mix rather than the format. A bed-less render measures
    -64.7 and the quietest field video -57.4, so -60 is what honestly separates them.

    Tonality is reported but not gated: absence scores 2.87 against the quietest field
    video's 2.71, so it cannot tell silence from music."""
    run = lambda **kw: _run(monkeypatch, tmp_path, **kw)["audio-music-present"]  # noqa: E731
    assert run(quiet_floor_dbfs=-44.2) == "pass", "Mamoru's 5.2M video must not fail"
    assert run(quiet_floor_dbfs=-57.4) == "pass", "quietest real field video"
    assert run(quiet_floor_dbfs=-64.7) == "fail", "a genuinely bed-less render"
    # tonality no longer decides the verdict, either way
    assert run(quiet_floor_dbfs=-44.2, tonality_ratio=2.7) == "pass"


def test_loudness_range_band_is_reference_derived(monkeypatch, tmp_path):
    """The 5-9 LU band was an unsourced spec row no TTS chain could reach. The real
    channel's full 5h17m audio track measures 2.5 LU (loudnorm) / 2.6 (ebur128), so the
    band is now centred on reality: a flat delivery PASSES, and the gate fails on the
    defect it can actually catch — range crushed by a dynamic-loudnorm fallback — or on
    dynamics this format never legitimately produces."""
    assert _run(monkeypatch, tmp_path, loudness_range_lu=2.0)["audio-lra"] == "pass"
    assert _run(monkeypatch, tmp_path, loudness_range_lu=2.6)["audio-lra"] == "pass"
    assert _run(monkeypatch, tmp_path, loudness_range_lu=1.0)["audio-lra"] == "fail"
    assert _run(monkeypatch, tmp_path, loudness_range_lu=7.0)["audio-lra"] == "fail"


def test_loudnorm_fallback_is_visible_in_the_qa_record(monkeypatch, tmp_path):
    """The single-pass fallback runs loudnorm in DYNAMIC mode, which compresses range.
    It used to be one console line that scrolled away."""
    assert _run(monkeypatch, tmp_path, loudnorm_fallback=True)["audio-two-pass"] == "warn"
    assert "audio-two-pass" not in _run(monkeypatch, tmp_path)


def test_lra_provenance_reaches_the_gate_data(monkeypatch, tmp_path):
    """stem/premaster LRA say WHERE range was lost; they ride the audio-lra gate."""
    import json as _json

    import manhwa2vid.video.qa_visual as qa
    from manhwa2vid.video.qa_visual import enforce_render_qa
    from pathlib import Path

    monkeypatch.setattr(qa, "measure_video",
                        lambda _v: _metrics(stem_lra_lu=2.0, premaster_lra_lu=2.2))
    enforce_render_qa(Path("dummy.mp4"), {"root": tmp_path}, {"_qa_force": True})
    gates = {g["name"]: g for g in
             _json.loads((tmp_path / "qa.render.json").read_text())["gates"]}
    assert gates["audio-lra"]["data"]["stem_lra_lu"] == 2.0
    assert gates["audio-lra"]["data"]["premaster_lra_lu"] == 2.2


def test_audio_gates_are_absent_rather_than_passing_when_unmeasurable(monkeypatch, tmp_path):
    """A silent-video render has no audio metrics. A gate that cannot measure must not
    report a pass — absence is visible in `status`, a false green is not."""
    import manhwa2vid.video.qa_visual as qa

    metrics = {k: v for k, v in _metrics().items()
               if k not in {"true_peak_dbtp", "loudness_lufs", "loudness_range_lu",
                            "quiet_floor_dbfs", "tonality_ratio", "duck_depth_db",
                            "duck_depth_estimate_db"}}
    monkeypatch.setattr(qa, "measure_video", lambda _v: metrics)
    enforce_render_qa(Path("dummy.mp4"), {"root": tmp_path}, {"_qa_force": True})
    names = {g["name"] for g in json.loads((tmp_path / "qa.render.json").read_text())["gates"]}
    assert not (names & {"true-peak", "audio-loudness", "audio-music-present",
                         "audio-bed-separation", "audio-lra"})


# --- export gating (qa-hardening-brief Phase 4) ----------------------------------------

def _exportable(tmp_path: Path, *, render_gate: str = "pass", video_size: int = 1024):
    """A project ready to export, with a render report describing its preview."""
    from manhwa2vid.models import (
        ProjectMeta, SourceLanguage, SourceType, project_paths, save_json,
    )

    paths = project_paths(tmp_path)
    for key in ("pages", "panels", "audio", "output", "debug"):
        paths[key].mkdir(parents=True, exist_ok=True)
    save_json(paths["meta"], ProjectMeta(
        slug="t", title="T", chapters="1", source_lang=SourceLanguage.EN,
        source_type=SourceType.IMAGES, source_path=str(tmp_path), pdf_path=str(tmp_path),
    ))
    paths["timeline_json"].write_text(json.dumps({"entries": [], "total_duration": 0}))
    video = paths["output"] / "preview.mp4"
    video.write_bytes(b"x" * video_size)
    (tmp_path / "qa.render.json").write_text(json.dumps({
        "stage": "render",
        "subject": {"video": "preview.mp4", "size": 1024, "mtime": 1.0},
        "gates": [{"name": "audio-music-present", "status": render_gate,
                   "details": "no bed", "data": {}}],
    }))
    return tmp_path


def test_export_is_blocked_by_a_failed_render_gate(tmp_path):
    """The visual and audio gates can only be measured on the finished file, so they
    cannot gate the render that produces it — but they must gate the export that ships it."""
    from manhwa2vid.pipeline import run_stage

    with pytest.raises(QAGateFailure) as exc:
        run_stage(_exportable(tmp_path, render_gate="fail"), PipelineStage.EXPORT)
    assert "audio-music-present" in str(exc.value)


def test_forcing_export_needs_the_operator_to_say_it_out_loud(tmp_path):
    """--force-past-qa alone is not enough to PUBLISH over a named failure."""
    from manhwa2vid.pipeline import run_stage

    project = _exportable(tmp_path, render_gate="fail")
    with pytest.raises(QAGateFailure) as exc:
        run_stage(project, PipelineStage.EXPORT, force_past_qa=True)
    assert "--i-understand" in str(exc.value)


def test_a_forced_export_is_recorded_in_the_checkpoint_forever(tmp_path, monkeypatch):
    """The override used to be a console line that scrolled away. Both audited videos
    shipped over failing gates and nothing in the project said so afterwards."""
    import manhwa2vid.pipeline as pipeline_mod
    from manhwa2vid.models import CheckpointState

    monkeypatch.setattr(pipeline_mod, "export_youtube_pack", lambda *a, **k: None)
    project = _exportable(tmp_path, render_gate="fail")
    pipeline_mod.run_stage(project, PipelineStage.EXPORT,
                           force_past_qa=True, i_understand=True)

    saved = CheckpointState.model_validate(json.loads((project / "checkpoint.json").read_text()))
    assert len(saved.qa_overrides) == 1
    assert saved.qa_overrides[0].stage == "export"
    assert saved.qa_overrides[0].failed_gates == ["render:audio-music-present"]


def test_export_refuses_a_render_report_describing_a_different_file(tmp_path):
    """A project accumulates dozens of previews and qa.render.json describes exactly one.
    Without this, a clean report from an older render certifies a newer, unmeasured file."""
    from manhwa2vid.pipeline import run_stage

    project = _exportable(tmp_path, render_gate="pass", video_size=2048)  # report says 1024
    with pytest.raises(QAGateFailure) as exc:
        run_stage(project, PipelineStage.EXPORT)
    assert "not the preview.mp4 being exported" in str(exc.value)


def test_a_clean_project_exports(tmp_path, monkeypatch):
    import manhwa2vid.pipeline as pipeline_mod

    called = {}
    monkeypatch.setattr(pipeline_mod, "export_youtube_pack",
                        lambda *a, **k: called.setdefault("ran", True))
    pipeline_mod.run_stage(_exportable(tmp_path), PipelineStage.EXPORT)
    assert called.get("ran") is True
