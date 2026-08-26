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
