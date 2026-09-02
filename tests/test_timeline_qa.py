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


def _pace_gate(tmp_path: Path, *, words: int, seconds: float, target_wpm: float) -> dict:
    """Run the timeline QA and return the narration-pace gate."""
    import json

    audio = tmp_path / "audio"
    audio.mkdir(exist_ok=True)
    _wav(audio / "beat_001.wav", seconds)
    beats = [ScriptBeat(beat_id=1, panel_ids=["p0001_01"], narration=" ".join(["w"] * words))]
    panels = [_panel("p0001_01", 1)]
    config = {**_config(), "script": {"target_wpm": target_wpm}}
    timeline = build_timeline(beats, panels, audio, config)
    paths = project_paths(tmp_path)
    _enforce_timeline_qa(beats, panels, timeline, paths, config)
    report = json.loads((tmp_path / "qa.timeline.json").read_text())
    return {g["name"]: g for g in report["gates"]}["narration-pace"]


def test_narration_pace_warns_when_the_voice_misses_its_budget(tmp_path: Path) -> None:
    """The defect this exists for: Kokoro delivered ~171 WPM while the script was
    budgeted at 235, so every panel dwelled a third too long and the video ran 55%
    longer than the reference. `tts.kokoro_speed` and `script.target_wpm` live in
    disjoint code paths and nothing compared them, so a 30% miss shipped unnoticed."""
    # 100 words over 35s = 171 WPM against a 235 budget — the shipped FP numbers.
    gate = _pace_gate(tmp_path, words=100, seconds=35.0, target_wpm=235)
    assert gate["status"] == WARN
    assert gate["data"]["actual_wpm"] == pytest.approx(171, abs=3)
    assert "235" in gate["details"]


def test_narration_pace_passes_when_delivered_rate_matches(tmp_path: Path) -> None:
    # 100 words over 25.5s = 235 WPM — what kokoro_speed 1.35 is meant to produce.
    gate = _pace_gate(tmp_path, words=100, seconds=25.5, target_wpm=235)
    assert gate["status"] == PASS
    assert gate["details"] == ""


# --- binding, holds and timing (qa-hardening-brief Phase 3) ----------------------------

def _gates(tmp_path: Path, beats, panels, timeline, config=None):
    import json

    from manhwa2vid.qa import QAGateFailure

    paths = project_paths(tmp_path)
    try:
        _enforce_timeline_qa(beats, panels, timeline, paths, config or _config())
    except QAGateFailure:
        pass  # some fixtures deliberately fail a gate; we want the report either way
    report = json.loads((tmp_path / "qa.timeline.json").read_text())
    return {g["name"]: g for g in report["gates"]}


def test_dwell_gate_reads_merged_runs_not_planned_entries(tmp_path: Path) -> None:
    """Frozen Player's 18.6s hold was TWO entries of 7.4s and 11.2s on one panel, and
    neither tripped a 12s limit. Consecutive entries on one panel are one shot to the
    viewer, so the gate must measure the run."""
    from manhwa2vid.models import Timeline, TimelineEntry

    def entry(pid, start, dur, beat):
        return TimelineEntry(panel_id=pid, panel_path=f"panels/{pid}.png", start=start,
                             end=start + dur, duration=dur, beat_id=beat,
                             subtitle_text="x")

    timeline = Timeline(
        entries=[entry("p0001_01", 0.0, 7.4, 1), entry("p0001_01", 7.4, 11.2, 2)],
        total_duration=18.6,
    )
    beats = [ScriptBeat(beat_id=1, panel_ids=["p0001_01"], narration="a b c"),
             ScriptBeat(beat_id=2, panel_ids=["p0001_01"], narration="d e f")]
    gates = _gates(tmp_path, beats, [_panel("p0001_01", 1)], timeline)
    assert gates["dwell-over-limit"]["status"] == WARN
    assert "18.6s" in gates["dwell-over-limit"]["details"]
    assert gates["no-invisible-cuts"]["status"] == WARN


def test_panel_utilisation_warns_when_most_art_never_airs(tmp_path: Path) -> None:
    from manhwa2vid.models import Timeline, TimelineEntry

    timeline = Timeline(
        entries=[TimelineEntry(panel_id="p0001_01", panel_path="panels/p0001_01.png",
                               start=0.0, end=3.0, duration=3.0, beat_id=1,
                               subtitle_text="x")],
        total_duration=3.0,
    )
    beats = [ScriptBeat(beat_id=1, panel_ids=["p0001_01"], narration="a b c")]
    panels = [_panel(f"p0001_{i:02d}", 1) for i in range(1, 6)]   # 1 of 5 shown = 20%
    gates = _gates(tmp_path, beats, panels, timeline)
    assert gates["panel-utilisation"]["status"] == WARN
    assert gates["panel-utilisation"]["data"]["utilisation_pct"] == 20.0


def test_hold_run_warns_only_when_sentence_numbers_exist(tmp_path: Path) -> None:
    """Without TimelineEntry.sentence_numbers the honest answer is entries-per-run, which
    UNDERSTATES the hold — so the gate reports 'not measured' instead of a false pass."""
    from manhwa2vid.models import Timeline, TimelineEntry

    def entry(nums):
        return TimelineEntry(panel_id="p0001_01", panel_path="panels/p0001_01.png",
                             start=0.0, end=9.0, duration=9.0, beat_id=1,
                             subtitle_text="x", sentence_numbers=nums)

    beats = [ScriptBeat(beat_id=1, panel_ids=["p0001_01"], narration="a b c")]
    panels = [_panel("p0001_01", 1)]

    blind = Timeline(entries=[entry([])], total_duration=9.0)
    gates = _gates(tmp_path, beats, panels, blind)
    assert gates["hold-run"]["status"] == PASS
    assert "not measured" in gates["hold-run"]["details"]

    seeing = Timeline(entries=[entry([1, 2, 3, 4, 5])], total_duration=9.0)
    gates = _gates(tmp_path, beats, panels, seeing)
    assert gates["hold-run"]["status"] == WARN
    assert gates["hold-run"]["data"]["longest_hold_sentences"] == 5


def test_timing_measured_fails_on_a_regression_to_word_proration(tmp_path: Path) -> None:
    """Kokoro synthesizes per sentence, so its sidecars are measured. Another provider
    returns one clip per beat and timeline._subdivide_segments word-prorates it — a
    plausible estimate that silently decouples every cut from the speech."""
    import json

    from manhwa2vid.models import Timeline, TimelineEntry

    audio = tmp_path / "audio"
    audio.mkdir()
    (tmp_path / "script.shotlist.json").write_text(json.dumps(
        {"sentences": [{"number": 1, "beat_id": 1, "text": "one", "panels": ["p0001_01"]},
                       {"number": 2, "beat_id": 1, "text": "two", "panels": []}]}
    ))
    timeline = Timeline(
        entries=[TimelineEntry(panel_id="p0001_01", panel_path="panels/p0001_01.png",
                               start=0.0, end=4.0, duration=4.0, beat_id=1,
                               subtitle_text="x")],
        total_duration=4.0,
    )
    beats = [ScriptBeat(beat_id=1, panel_ids=["p0001_01"], narration="one. two.")]
    panels = [_panel("p0001_01", 1)]

    # one sidecar entry for a two-sentence beat: the proration path
    (audio / "beat_001.segments.json").write_text(json.dumps([{"text": "one two", "seconds": 4.0}]))
    gates = _gates(tmp_path, beats, panels, timeline)
    assert gates["timing-measured"]["status"] == FAIL
    assert gates["timing-measured"]["data"]["mismatched_beats"] == [1]

    # one per sentence: measured
    (audio / "beat_001.segments.json").write_text(json.dumps(
        [{"text": "one", "seconds": 2.0}, {"text": "two", "seconds": 2.0}]
    ))
    gates = _gates(tmp_path, beats, panels, timeline)
    assert gates["timing-measured"]["status"] == PASS
    assert gates["match-rate"]["status"] == WARN   # 50% bound, floor is 70%


def test_match_rate_floor_is_reachable_given_the_matchers_own_instructions():
    """The floor must sit under what a correct matcher achieves. The matcher is told to
    claim nothing for narrator commentary, so the ceiling is the share of sentences the
    model will claim at all. Re-pinned 2026-08-31 after adjacent co-claims and the
    short-gap second pass removed the dominant filter loss (neighbour contention):
    measured SL 77%, FP ch1-2 87%, ch3-4 89%. The floor sits below the worst title
    with margin, and high enough to catch a collapsed matcher."""
    from manhwa2vid.tts.engine import _MATCH_MIN_PCT

    assert _MATCH_MIN_PCT <= 77.0, "floor exceeds the worst measured title"
    assert _MATCH_MIN_PCT >= 60.0, "floor so low it would not catch a collapsed matcher"


def test_a_panel_returning_later_is_caught(tmp_path: Path) -> None:
    """Solo Leveling showed a hunter's leg at 605.2s and again at 627.3s, the second
    time being the line that describes it. `no-invisible-cuts` cannot see this: it fuses
    ADJACENT entries, and a non-adjacent repeat has another panel in between."""
    from manhwa2vid.models import Timeline, TimelineEntry

    def entry(pid, start, dur, beat):
        return TimelineEntry(panel_id=pid, panel_path=f"panels/{pid}.png", start=start,
                             end=start + dur, duration=dur, beat_id=beat,
                             subtitle_text="x")

    timeline = Timeline(
        entries=[entry("p0001_01", 0.0, 3.0, 1),
                 entry("p0001_02", 3.0, 3.0, 1),
                 entry("p0001_01", 6.0, 3.0, 2)],       # the same picture, 6s later
        total_duration=9.0,
    )
    beats = [ScriptBeat(beat_id=1, panel_ids=["p0001_01", "p0001_02"], narration="a b"),
             ScriptBeat(beat_id=2, panel_ids=["p0001_01"], narration="c d")]
    panels = [_panel("p0001_01", 1), _panel("p0001_02", 1)]
    gates = _gates(tmp_path, beats, panels, timeline)

    # FAIL since 2026-08-30 (user decision): the planner's gap rule makes repeats
    # exactly 0 on real artifacts, so nonzero is a regression, and this class shipped
    # twice while warns scrolled past.
    assert gates["no-repeated-panels"]["status"] == FAIL
    assert "p0001_01" in gates["no-repeated-panels"]["details"]
    assert "0.0s, 6.0s" in gates["no-repeated-panels"]["details"]
    # The one-panel rewind is inside SCENE_RADIUS, so reading-order alone tolerates it
    # (same-scene editing, user decision later the same day) — the REPEAT is what
    # fails this fixture. Cross-scene rewinds are pinned separately below.
    assert gates["reading-order"]["status"] == PASS
    # The gate that already existed is blind to it — which is why this one exists.
    assert gates["no-invisible-cuts"]["status"] == PASS


def test_a_hold_across_a_beat_boundary_is_not_a_repeat(tmp_path: Path) -> None:
    """One shot split over two entries is a HOLD, already reported by
    `no-invisible-cuts`. Counting it twice here would fire on every render."""
    from manhwa2vid.models import Timeline, TimelineEntry

    def entry(pid, start, dur, beat):
        return TimelineEntry(panel_id=pid, panel_path=f"panels/{pid}.png", start=start,
                             end=start + dur, duration=dur, beat_id=beat,
                             subtitle_text="x")

    timeline = Timeline(
        entries=[entry("p0001_01", 0.0, 3.0, 1), entry("p0001_01", 3.0, 3.0, 2)],
        total_duration=6.0,
    )
    beats = [ScriptBeat(beat_id=1, panel_ids=["p0001_01"], narration="a b"),
             ScriptBeat(beat_id=2, panel_ids=["p0001_01"], narration="c d")]
    gates = _gates(tmp_path, beats, [_panel("p0001_01", 1)], timeline)
    assert gates["no-repeated-panels"]["status"] == PASS
    assert gates["no-invisible-cuts"]["status"] == WARN


def test_an_in_order_timeline_passes_the_reading_order_gate(tmp_path: Path) -> None:
    from manhwa2vid.models import Timeline, TimelineEntry

    def entry(pid, start, dur, beat):
        return TimelineEntry(panel_id=pid, panel_path=f"panels/{pid}.png", start=start,
                             end=start + dur, duration=dur, beat_id=beat,
                             subtitle_text="x")

    timeline = Timeline(
        entries=[entry("p0001_01", 0.0, 3.0, 1), entry("p0001_02", 3.0, 3.0, 1),
                 entry("p0002_01", 6.0, 3.0, 2)],
        total_duration=9.0,
    )
    beats = [ScriptBeat(beat_id=1, panel_ids=["p0001_01", "p0001_02"], narration="a b"),
             ScriptBeat(beat_id=2, panel_ids=["p0002_01"], narration="c d")]
    panels = [_panel("p0001_01", 1), _panel("p0001_02", 1), _panel("p0002_01", 2)]
    gates = _gates(tmp_path, beats, panels, timeline)
    assert gates["reading-order"]["status"] == PASS
    assert gates["no-repeated-panels"]["status"] == PASS


def test_a_cross_scene_rewind_still_fails_reading_order(tmp_path: Path) -> None:
    """SCENE_RADIUS tolerates the close-up -> establishing-shot cut; the 26-71 panel
    jumps the user originally reported are another scene entirely and stay FAIL."""
    from manhwa2vid.models import Timeline, TimelineEntry

    def entry(pid, start, dur, beat):
        return TimelineEntry(panel_id=pid, panel_path=f"panels/{pid}.png", start=start,
                             end=start + dur, duration=dur, beat_id=beat,
                             subtitle_text="x")

    panels = [_panel(f"p{i:04d}_01", 1) for i in range(1, 21)]
    timeline = Timeline(
        entries=[entry("p0018_01", 0.0, 3.0, 1),
                 entry("p0002_01", 3.0, 3.0, 2)],     # 16 panels back: another scene
        total_duration=6.0,
    )
    beats = [ScriptBeat(beat_id=1, panel_ids=["p0018_01"], narration="a b"),
             ScriptBeat(beat_id=2, panel_ids=["p0002_01"], narration="c d")]
    gates = _gates(tmp_path, beats, panels, timeline)
    assert gates["reading-order"]["status"] == FAIL
    assert "p0002_01" in gates["reading-order"]["details"]


def _block_meta(tmp_path: Path, boundaries: list[str], visits: list[int]) -> None:
    """Write the shotlist metadata the reading-order gate reads."""
    import json as _json

    p = project_paths(tmp_path)["script_shotlist_json"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps({
        "sentences": [],
        "time_blocks": {"boundaries": boundaries, "visits": visits, "returns": []},
    }), encoding="utf-8")


def _entry(pid, start, dur, beat):
    from manhwa2vid.models import TimelineEntry

    return TimelineEntry(panel_id=pid, panel_path=f"panels/{pid}.png", start=start,
                         end=start + dur, duration=dur, beat_id=beat, subtitle_text="x")


class TestReadingOrderAcrossTimeBlocks:
    """A chapter told out of page order — cold open, flashback, RETURN — makes the
    return a legitimate large backward jump. Frozen Player's is 46 panels. Judged
    globally it fails a correct artifact; judged only globally, 11 sentences of fight
    narration played over sky. Order is checked WITHIN a visit; the visit SEQUENCE is
    checked structurally against what the aligner planned."""

    def _panels(self, n=20):
        return [_panel(f"p{i:04d}_01", 1) for i in range(1, n + 1)]

    def _beats(self, ids):
        return [ScriptBeat(beat_id=i + 1, panel_ids=[pid], narration="a b")
                for i, pid in enumerate(ids)]

    def test_a_planned_return_is_legal(self, tmp_path: Path) -> None:
        from manhwa2vid.models import Timeline

        _block_meta(tmp_path, ["p0006_01", "p0012_01"], [0, 1, 0, 2])
        ids = ["p0002_01", "p0008_01", "p0003_01", "p0015_01"]
        timeline = Timeline(
            entries=[_entry(pid, i * 3.0, 3.0, i + 1) for i, pid in enumerate(ids)],
            total_duration=12.0,
        )
        gates = _gates(tmp_path, self._beats(ids), self._panels(), timeline)
        assert gates["reading-order"]["status"] == PASS
        assert gates["reading-order"]["data"]["observed_visits"] == [0, 1, 0, 2]

    def test_an_unplanned_extra_visit_fails(self, tmp_path: Path) -> None:
        """A rogue borrow into an earlier block adds a visit nobody planned."""
        from manhwa2vid.models import Timeline

        _block_meta(tmp_path, ["p0006_01", "p0012_01"], [0, 1, 2])
        ids = ["p0002_01", "p0008_01", "p0003_01", "p0015_01"]
        timeline = Timeline(
            entries=[_entry(pid, i * 3.0, 3.0, i + 1) for i, pid in enumerate(ids)],
            total_duration=12.0,
        )
        gates = _gates(tmp_path, self._beats(ids), self._panels(), timeline)
        assert gates["reading-order"]["status"] == FAIL
        assert "not a subsequence" in gates["reading-order"]["details"]

    def test_a_vanished_visit_is_allowed(self, tmp_path: Path) -> None:
        """A visit whose sentences all became holds legitimately never reaches the
        screen — subsequence, not equality."""
        from manhwa2vid.models import Timeline

        _block_meta(tmp_path, ["p0006_01", "p0012_01"], [0, 1, 0, 2])
        ids = ["p0002_01", "p0015_01"]
        timeline = Timeline(
            entries=[_entry(pid, i * 3.0, 3.0, i + 1) for i, pid in enumerate(ids)],
            total_duration=6.0,
        )
        gates = _gates(tmp_path, self._beats(ids), self._panels(), timeline)
        assert gates["reading-order"]["status"] == PASS

    def test_a_rewind_inside_one_visit_still_fails(self, tmp_path: Path) -> None:
        """The original watched defect was a 26-71 panel jump WITHIN a block."""
        from manhwa2vid.models import Timeline

        _block_meta(tmp_path, ["p0006_01"], [0, 1])
        ids = ["p0008_01", "p0020_01", "p0009_01"]     # 11 back inside block 1
        timeline = Timeline(
            entries=[_entry(pid, i * 3.0, 3.0, i + 1) for i, pid in enumerate(ids)],
            total_duration=9.0,
        )
        gates = _gates(tmp_path, self._beats(ids), self._panels(), timeline)
        assert gates["reading-order"]["status"] == FAIL
        assert "p0009_01" in gates["reading-order"]["details"]

    def test_no_metadata_keeps_the_old_global_rule(self, tmp_path: Path) -> None:
        """Old artifacts and projects with no printed jumps must be unaffected."""
        from manhwa2vid.models import Timeline

        ids = ["p0018_01", "p0002_01"]
        timeline = Timeline(
            entries=[_entry(pid, i * 3.0, 3.0, i + 1) for i, pid in enumerate(ids)],
            total_duration=6.0,
        )
        gates = _gates(tmp_path, self._beats(ids), self._panels(), timeline)
        assert gates["reading-order"]["status"] == FAIL


def test_a_marked_callback_may_replay_its_shot(tmp_path: Path) -> None:
    """The narration asked for this picture back ("this is the same guy from the food
    truck"), so showing it is the edit a human editor would make. Same timeline as
    test_a_panel_returning_later_is_caught, with a shot list that marks the second
    appearance a callback — that one difference must flip the gate."""
    import json

    from manhwa2vid.models import Timeline, TimelineEntry, project_paths

    def entry(pid, start, dur, beat):
        return TimelineEntry(panel_id=pid, panel_path=f"panels/{pid}.png", start=start,
                             end=start + dur, duration=dur, beat_id=beat,
                             subtitle_text="x")

    timeline = Timeline(
        entries=[entry("p0001_01", 0.0, 3.0, 1),
                 entry("p0001_02", 3.0, 3.0, 1),
                 entry("p0001_01", 6.0, 3.0, 2)],
        total_duration=9.0,
    )
    beats = [ScriptBeat(beat_id=1, panel_ids=["p0001_01", "p0001_02"], narration="a b"),
             ScriptBeat(beat_id=2, panel_ids=["p0001_01"], narration="c d")]
    panels = [_panel("p0001_01", 1), _panel("p0001_02", 1)]

    paths = project_paths(tmp_path)
    paths["script_shotlist_json"].write_text(json.dumps({"sentences": [
        {"number": 1, "beat_id": 1, "panels": ["p0001_01"]},
        {"number": 2, "beat_id": 1, "panels": ["p0001_02"]},
        {"number": 3, "beat_id": 2, "panels": ["p0001_01"], "callback": True},
    ]}))
    gates = _gates(tmp_path, beats, panels, timeline)
    assert gates["no-repeated-panels"]["status"] == PASS
    assert gates["no-repeated-panels"]["data"]["callback_replays"] == ["p0001_01"]


def test_an_unmarked_repeat_still_fails_beside_a_marked_one(tmp_path: Path) -> None:
    """The narrowing must not become a loosening: a shot list containing ONE callback
    does not license every other repeat in the video."""
    import json

    from manhwa2vid.models import Timeline, TimelineEntry, project_paths

    def entry(pid, start, dur, beat):
        return TimelineEntry(panel_id=pid, panel_path=f"panels/{pid}.png", start=start,
                             end=start + dur, duration=dur, beat_id=beat,
                             subtitle_text="x")

    timeline = Timeline(
        entries=[entry("p0001_01", 0.0, 3.0, 1), entry("p0001_02", 3.0, 3.0, 1),
                 entry("p0001_01", 6.0, 3.0, 2),      # the marked callback
                 entry("p0001_03", 9.0, 3.0, 2),
                 entry("p0001_02", 12.0, 3.0, 3)],    # nobody asked for this one
        total_duration=15.0,
    )
    beats = [ScriptBeat(beat_id=1, panel_ids=["p0001_01", "p0001_02"], narration="a b"),
             ScriptBeat(beat_id=2, panel_ids=["p0001_01", "p0001_03"], narration="c d"),
             ScriptBeat(beat_id=3, panel_ids=["p0001_02"], narration="e f")]
    panels = [_panel(f"p0001_0{i}", 1) for i in (1, 2, 3)]

    paths = project_paths(tmp_path)
    paths["script_shotlist_json"].write_text(json.dumps({"sentences": [
        {"number": 3, "beat_id": 2, "panels": ["p0001_01"], "callback": True},
    ]}))
    gates = _gates(tmp_path, beats, panels, timeline)
    assert gates["no-repeated-panels"]["status"] == FAIL
    assert "p0001_02" in gates["no-repeated-panels"]["details"]
    assert "p0001_01" not in gates["no-repeated-panels"]["details"]


def test_a_third_appearance_is_never_legal(tmp_path: Path) -> None:
    """A callback licenses ONE return, not a motif."""
    import json

    from manhwa2vid.models import Timeline, TimelineEntry, project_paths

    def entry(pid, start, dur, beat):
        return TimelineEntry(panel_id=pid, panel_path=f"panels/{pid}.png", start=start,
                             end=start + dur, duration=dur, beat_id=beat,
                             subtitle_text="x")

    timeline = Timeline(
        entries=[entry("p0001_01", 0.0, 3.0, 1), entry("p0001_02", 3.0, 3.0, 1),
                 entry("p0001_01", 6.0, 3.0, 2), entry("p0001_02", 9.0, 3.0, 2),
                 entry("p0001_01", 12.0, 3.0, 3)],
        total_duration=15.0,
    )
    beats = [ScriptBeat(beat_id=b, panel_ids=["p0001_01"], narration="a b")
             for b in (1, 2, 3)]
    panels = [_panel("p0001_01", 1), _panel("p0001_02", 1)]

    paths = project_paths(tmp_path)
    paths["script_shotlist_json"].write_text(json.dumps({"sentences": [
        {"number": 3, "beat_id": 2, "panels": ["p0001_01"], "callback": True},
    ]}))
    gates = _gates(tmp_path, beats, panels, timeline)
    assert gates["no-repeated-panels"]["status"] == FAIL
    assert "p0001_01 shown 3x" in gates["no-repeated-panels"]["details"]


def test_coverage_gaps_separate_sampling_from_a_skipped_sequence():
    """"Fewer panels are fine as long as the story is conveyed without disconnect."
    Utilisation cannot tell those apart: an evenly-sampled long recap and one that
    jumps 27 pages can show the same SHARE of panels. The distribution is the signal —
    the 20-chapter probe had a median gap of 2 and one run of 165."""
    from manhwa2vid.measure.binding import coverage_gaps

    order = [f"p{i:04d}" for i in range(100)]
    sampled = [{"panel_id": p} for p in order[::3]]          # every third panel
    holed = [{"panel_id": p} for p in order[:20] + order[80:]]  # 60-panel hole

    a, b = coverage_gaps(order, sampled), coverage_gaps(order, holed)
    assert a["longest_gap"] <= 3, a
    assert b["longest_gap"] == 60, b
    # Both show a similar share; only the gap measure separates them.
    assert b["worst"][0]["from"] == "p0020" and b["worst"][0]["to"] == "p0079"


def test_a_fully_shown_range_has_no_gaps():
    from manhwa2vid.measure.binding import coverage_gaps

    order = [f"p{i:04d}" for i in range(10)]
    g = coverage_gaps(order, [{"panel_id": p} for p in order])
    assert g["gaps"] == 0 and g["longest_gap"] == 0
