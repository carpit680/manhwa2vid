"""Timeline-stage QA regression tests: blank entries, over-long dwells, orphaned beats."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest

from manhwa2vid.models import Panel, PanelBBox, ScriptBeat, project_paths
from manhwa2vid.qa import FAIL, PASS, WARN, QAGateFailure
from manhwa2vid.tts.engine import _enforce_timeline_qa
from manhwa2vid.video.timeline import _resolve_panels_for_beat, build_timeline


def _panel(pid: str, page: int, *, ink: float = 0.9, dark: float = 0.5) -> Panel:
    return Panel(
        id=pid,
        page_num=page,
        bbox=PanelBBox(x=0, y=0, width=100, height=100),
        image_path=f"panels/{pid}.png",
        ink_ratio=ink,
        dark_ratio=dark,
    )


def _wav(path: Path, seconds: float) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(struct.pack("<h", 0) * int(24000 * seconds))


def _config() -> dict:
    return {
        "video": {"min_panel_seconds": 2, "max_panel_seconds": 5, "fps": 30,
                  "dwell_warn_multiplier": 1.5},
        "panels": {"exclude_blank_panels": True, "blank_max_ink_ratio": 0.30,
                   "blank_max_dark_ratio": 0.10},
    }


def test_dwell_over_limit_warns(tmp_path: Path) -> None:
    """Regression: a 25-word single-panel beat dwelled 9.8s with no signal anywhere."""
    audio = tmp_path / "audio"
    audio.mkdir()
    _wav(audio / "beat_001.wav", 10.0)
    beats = [ScriptBeat(beat_id=1, panel_ids=["p0001_01"], narration=" ".join(["w"] * 25))]
    panels = [_panel("p0001_01", 1)]
    timeline = build_timeline(beats, panels, audio, _config())
    assert timeline.entries[0].duration == pytest.approx(10.0, rel=0.05)

    paths = project_paths(tmp_path)
    _enforce_timeline_qa(beats, panels, timeline, paths, _config())
    import json

    report = json.loads((tmp_path / "qa.timeline.json").read_text())
    gates = {g["name"]: g for g in report["gates"]}
    assert gates["dwell-over-limit"]["status"] == WARN
    assert "beat 1" in gates["dwell-over-limit"]["details"]
    assert gates["no-blank-panels"]["status"] == PASS


def test_no_blank_panels_gate_fails_on_blank_entry(tmp_path: Path) -> None:
    audio = tmp_path / "audio"
    audio.mkdir()
    _wav(audio / "beat_001.wav", 3.0)
    beats = [ScriptBeat(beat_id=1, panel_ids=["p0001_01"], narration="short line here")]
    blank = _panel("p0001_01", 1, ink=0.05, dark=0.01)
    timeline = build_timeline(beats, [blank], audio, _config())

    paths = project_paths(tmp_path)
    with pytest.raises(QAGateFailure):
        _enforce_timeline_qa(beats, [blank], timeline, paths, _config())
    import json

    report = json.loads((tmp_path / "qa.timeline.json").read_text())
    gates = {g["name"]: g for g in report["gates"]}
    assert gates["no-blank-panels"]["status"] == FAIL


def test_beat_with_all_panels_excluded_falls_back_to_nearest() -> None:
    """Regression: the old fallback showed the chapter's FIRST panel, visually wrong."""
    panel_map = {p.id: p for p in [_panel("p0002_01", 2), _panel("p0019_01", 19)]}
    all_ids = list(panel_map)
    beat = ScriptBeat(beat_id=5, panel_ids=["p0018_01"], narration="x")  # excluded blank
    resolved = _resolve_panels_for_beat(beat, panel_map, all_ids)
    assert resolved == ["p0019_01"]  # nearest by page, not the chapter opener


def test_orphaned_beat_reported_in_qa(tmp_path: Path) -> None:
    audio = tmp_path / "audio"
    audio.mkdir()
    _wav(audio / "beat_001.wav", 3.0)
    beats = [ScriptBeat(beat_id=1, panel_ids=["p0009_09"], narration="short line here")]
    panels = [_panel("p0002_01", 2)]
    timeline = build_timeline(beats, panels, audio, _config())
    paths = project_paths(tmp_path)
    _enforce_timeline_qa(beats, panels, timeline, paths, _config())
    import json

    report = json.loads((tmp_path / "qa.timeline.json").read_text())
    gates = {g["name"]: g for g in report["gates"]}
    assert gates["beat-panels-missing"]["status"] == WARN
