"""Shot-list construction: the deterministic half of sentence→panel matching.

The vision call decides WHICH panels depict a sentence; everything tested here decides
what that becomes on screen. Measured motivation: with panels apportioned by airtime
alone, 86% (Frozen Player) and 93% (Solo Leveling) of matchable sentences were showing a
panel that does not depict them.
"""

from __future__ import annotations

from manhwa2vid.script.match import filter_monotonic, plan_shots


# --- the monotonic filter -----------------------------------------------------------

def test_monotonic_filter_drops_backward_claims():
    """A model claim that runs against the story's forward motion is dropped, not
    negotiated with: sentences advance, so the panels they claim must advance too."""
    order = ["p1", "p2", "p3", "p4", "p5"]
    claims = [
        (1, "p1"),
        (2, "p2"),
        (3, "p1"),   # sentence 3 reaching BACK to panel 1 — contradiction
        (4, "p4"),
        (5, "p5"),
    ]
    kept = filter_monotonic(claims, order)
    assert (3, "p1") not in kept
    assert [c for c in kept] == [(1, "p1"), (2, "p2"), (4, "p4"), (5, "p5")]


def test_monotonic_filter_keeps_the_largest_consistent_set():
    """When claims conflict, keep the most that CAN be true together — a single early
    outlier must not cost us the whole chain behind it."""
    order = [f"p{i}" for i in range(1, 8)]
    claims = [(1, "p7"), (2, "p2"), (3, "p3"), (4, "p4"), (5, "p5")]
    kept = filter_monotonic(claims, order)
    assert len(kept) == 4 and (1, "p7") not in kept


def test_monotonic_filter_ignores_unknown_panels():
    assert filter_monotonic([(1, "ghost")], ["p1"]) == []
    assert filter_monotonic([], ["p1"]) == []


# --- planning: claims + measured seconds -> shots ------------------------------------

def _sl(*specs):
    return {"sentences": [
        {"number": i + 1, "beat_id": 1, "text": f"s{i+1}", "panels": list(p)}
        for i, p in enumerate(specs)
    ]}


def test_commentary_holds_the_previous_shot():
    """A sentence that depicts nothing extends the shot it is commenting on — the user's
    choice, and what Mamoru does (17% of his shots run over 6 seconds)."""
    plan = plan_shots(_sl(["p1"], [], ["p2"]),
                      {1: [{"seconds": 3.0}, {"seconds": 2.0}, {"seconds": 3.0}]}, floor=1.0)
    assert plan[1] == [("p1", 5.0), ("p2", 3.0)]


def test_leading_commentary_attaches_to_the_first_real_shot():
    """Nothing has been shown yet, so a leading aside cannot hold anything — its seconds
    ride the first panel that IS claimed rather than vanishing."""
    plan = plan_shots(_sl([], ["p9"]), {1: [{"seconds": 2.0}, {"seconds": 3.0}]}, floor=1.0)
    assert plan[1] == [("p9", 5.0)]


def test_multi_panel_sentence_splits_its_seconds():
    plan = plan_shots(_sl(["p1", "p2"]), {1: [{"seconds": 6.0}]}, floor=1.0)
    assert plan[1] == [("p1", 3.0), ("p2", 3.0)]


def test_repeated_panel_folds_instead_of_cutting_to_itself():
    plan = plan_shots(_sl(["p1"], ["p1"]), {1: [{"seconds": 2.0}, {"seconds": 2.0}]}, floor=1.0)
    assert plan[1] == [("p1", 4.0)]


def test_short_shot_merges_and_total_seconds_survive():
    """Under-floor shots merge rather than strobing, and the beat's audio length is
    preserved exactly — A/V lock is downstream of this."""
    plan = plan_shots(_sl(["p1"], ["p2"]), {1: [{"seconds": 3.0}, {"seconds": 0.4}]}, floor=1.0)
    assert plan[1] == [("p1", 3.4)]

    plan = plan_shots(_sl(["p1"], ["p2"]), {1: [{"seconds": 0.4}, {"seconds": 3.0}]}, floor=1.0)
    assert plan[1] == [("p2", 3.4)], "a short FIRST shot has no previous to merge into"


def test_mismatched_sidecar_refuses_to_guess():
    """Sentence identity is the contract. If the sidecar and the shot list disagree the
    planner returns None so the caller falls back, rather than pairing the wrong seconds
    with the wrong panel and silently desynchronising picture from sound."""
    assert plan_shots(_sl(["p1"], ["p2"]), {1: [{"seconds": 3.0}]}, floor=1.0) is None
    assert plan_shots(_sl(["p1"]), {}, floor=1.0) is None


def test_hold_carries_across_a_beat_boundary():
    """A beat opening on commentary holds what the previous beat left on screen."""
    shotlist = {"sentences": [
        {"number": 1, "beat_id": 1, "text": "a", "panels": ["p1"]},
        {"number": 2, "beat_id": 2, "text": "b", "panels": []},
        {"number": 3, "beat_id": 2, "text": "c", "panels": ["p2"]},
    ]}
    segs = {1: [{"seconds": 3.0}], 2: [{"seconds": 2.0}, {"seconds": 3.0}]}
    plan = plan_shots(shotlist, segs, floor=1.0)
    assert plan[1] == [("p1", 3.0)]
    assert plan[2] == [("p1", 2.0), ("p2", 3.0)], "beat 2 opens on the held panel"


def test_shot_plan_entries_carry_their_audio_file(tmp_path):
    """A shot-plan render came out completely SILENT and nothing failed.

    _mix_audio collects narration by reading `audio_file` off the timeline entries; the
    shot-plan branch built entries without it, so the list came back empty and _mix_audio
    treated that as "no narration" and copied the video straight through. Silence is the
    one defect that no gate looks for, so it is pinned here.
    """
    import wave

    from manhwa2vid.models import Panel, PanelBBox, ScriptBeat
    from manhwa2vid.video.timeline import build_timeline

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    wav = audio_dir / "beat_001.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 24000 * 4)   # 4 seconds

    panels = [
        Panel(id=f"p0001_{i:02d}", page_num=1,
              bbox=PanelBBox(x=0, y=0, width=10, height=10),
              image_path=f"panels/p0001_{i:02d}.png")
        for i in (1, 2)
    ]
    beats = [ScriptBeat(beat_id=1, panel_ids=[p.id for p in panels], narration="One. Two.")]
    timeline = build_timeline(
        beats, panels, audio_dir, {},
        shot_plan={1: [("p0001_01", 2.0), ("p0001_02", 2.0)]},
    )
    assert timeline.entries, "the shot plan must produce entries"
    assert all(e.audio_file for e in timeline.entries), "every entry needs its audio file"
    assert {e.audio_file for e in timeline.entries} == {"audio/beat_001.wav"}


# --- bounded fill + accent cuts (2026-08-26 revision) --------------------------------

def test_unmatched_run_walks_the_panels_between_anchors():
    """SL matched only 49% of sentences; holding made half the picture stand still.
    An unmatched run now walks the unclaimed panels BETWEEN its anchors, in reading
    order — bounded, so it can never jump to an unrelated image."""
    order = ["p1", "p2", "p3", "p4", "p5"]
    plan = plan_shots(
        _sl(["p1"], [], [], ["p5"]),
        {1: [{"seconds": 3.0}, {"seconds": 2.0}, {"seconds": 2.0}, {"seconds": 3.0}]},
        floor=1.0,
        panel_order=order,
    )
    shown = [pid for pid, _ in plan[1]]
    assert shown == ["p1", "p2", "p3", "p4", "p5"], shown
    assert abs(sum(sec for _, sec in plan[1]) - 10.0) < 1e-6, "A/V total preserved"


def test_fill_without_gap_panels_still_holds():
    """No panels between the anchors -> the old hold behaviour stands."""
    plan = plan_shots(
        _sl(["p1"], [], ["p2"]),
        {1: [{"seconds": 3.0}, {"seconds": 2.0}, {"seconds": 3.0}]},
        floor=1.0,
        panel_order=["p1", "p2"],
    )
    assert plan[1] == [("p1", 5.0), ("p2", 3.0)]


def test_fill_needs_both_anchors():
    """A trailing unmatched run has no right bound — it holds rather than wandering
    into panels the narration may never reach."""
    plan = plan_shots(
        _sl(["p1"], [], []),
        {1: [{"seconds": 3.0}, {"seconds": 2.0}, {"seconds": 2.0}]},
        floor=1.0,
        panel_order=["p1", "p2", "p3"],
    )
    assert plan[1] == [("p1", 7.0)]


def test_fill_subsamples_a_wide_gap_in_order():
    """More gap panels than the run's airtime can carry at the floor: subsample evenly,
    order preserved, each shot at least the floor."""
    order = [f"p{i}" for i in range(1, 13)]
    plan = plan_shots(
        _sl(["p1"], [], ["p12"]),
        {1: [{"seconds": 2.0}, {"seconds": 3.0}, {"seconds": 2.0}]},
        floor=1.0,
        panel_order=order,
    )
    shown = [pid for pid, _ in plan[1]]
    assert shown[0] == "p1" and shown[-1] == "p12"
    middle = shown[1:-1]
    assert 1 <= len(middle) <= 3, f"airtime caps the fill: {middle}"
    positions = [order.index(p) for p in shown]
    assert positions == sorted(positions), "reading order preserved"


def test_fill_skips_panels_claimed_elsewhere():
    """A panel matched to a LATER sentence is not stolen by the fill."""
    order = ["p1", "p2", "p3", "p4"]
    plan = plan_shots(
        _sl(["p1"], [], ["p3"], ["p4"]),
        {1: [{"seconds": 2.0}, {"seconds": 2.0}, {"seconds": 2.0}, {"seconds": 2.0}]},
        floor=1.0,
        panel_order=order,
    )
    shown = [pid for pid, _ in plan[1]]
    assert shown == ["p1", "p2", "p3", "p4"]


def test_accent_cut_survives_below_the_floor():
    """A multi-panel action sentence keeps its intra-sentence cuts below the 1.0s
    floor — deleting them is why the videos had ZERO shots under 1.5s against the
    reference's 22%."""
    plan = plan_shots(
        _sl(["p1", "p2", "p3"]),
        {1: [{"seconds": 2.4}]},
        floor=1.0,
        accent_floor=0.4,
    )
    assert [pid for pid, _ in plan[1]] == ["p1", "p2", "p3"]
    assert all(abs(sec - 0.8) < 1e-6 for _, sec in plan[1])


def test_accent_below_accent_floor_still_merges():
    plan = plan_shots(
        _sl(["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"]),
        {1: [{"seconds": 2.4}]},
        floor=1.0,
        accent_floor=0.4,
    )
    assert all(sec >= 0.4 for _, sec in plan[1]), plan[1]
    assert abs(sum(sec for _, sec in plan[1]) - 2.4) < 1e-6


def test_fill_crosses_beat_boundaries():
    """Anchors in DIFFERENT beats still bound a fill run."""
    shotlist = {"sentences": [
        {"number": 1, "beat_id": 1, "text": "a", "panels": ["p1"]},
        {"number": 2, "beat_id": 1, "text": "b", "panels": []},
        {"number": 3, "beat_id": 2, "text": "c", "panels": []},
        {"number": 4, "beat_id": 2, "text": "d", "panels": ["p4"]},
    ]}
    segs = {1: [{"seconds": 2.0}, {"seconds": 2.0}], 2: [{"seconds": 2.0}, {"seconds": 2.0}]}
    plan = plan_shots(shotlist, segs, floor=1.0, panel_order=["p1", "p2", "p3", "p4"])
    shown = [pid for beat in (1, 2) for pid, _ in plan[beat]]
    assert shown == ["p1", "p2", "p3", "p4"], shown
