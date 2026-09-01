"""Narration-driven replay: a recall sentence may put its earlier shot back on screen.

Panel reuse used to be forbidden outright, because accidental reuse looked exactly like
a bug — Solo Leveling showed a hunter's leg at 605.2s and again at 627.3s, the second
time being the line that actually earned it. This feature NARROWS that rule rather than
loosening it, and these tests exist to prove the narrowing: a callback needs a recall
frame AND a resolved origin AND distance, so nothing accidental can produce a repeat.
"""

from __future__ import annotations

from manhwa2vid.script.callbacks import (
    callback_panels,
    is_recall,
    resolve_callbacks,
)


def _rows(*specs):
    """(number, text, panels) -> shotlist sentence rows."""
    return [
        {"number": n, "beat_id": 1, "block": 0, "text": t, "panels": list(p)}
        for n, t, p in specs
    ]


# --- the detector ---------------------------------------------------------------------

def test_recall_frames_are_recognised():
    for line in ("Remember the guy from the food truck?",
                 "If you remember, the system said the same thing two floors ago.",
                 "This is the same vendor who ran out of coffee.",
                 "Back when the party first stepped through the gate, nobody worried."):
        assert is_recall(line), line


def test_the_story_remembering_is_not_the_narrator_recalling():
    """"He remembers his mother" is a character's interiority — replaying an old shot
    over it would be a non-sequitur. The frame must open a clause, not sit mid-sentence."""
    for line in ("He remembers his mother and keeps walking.",
                 "She thinks back to the day she quit.",
                 "The memory of the gate still bothers him."):
        assert not is_recall(line), line


# --- resolution -----------------------------------------------------------------------

def test_a_recall_takes_the_panel_of_the_scene_it_names():
    rows = _rows(
        (1, "The vendor at the food truck apologises for running out of coffee.", ["p0010_01"]),
        *[(n, f"Filler sentence number {n} about the raid.", ["p%04d_01" % n]) for n in range(2, 16)],
        (16, "This is the same vendor from the food truck, still out of coffee.", []),
    )
    made = resolve_callbacks(rows)
    assert len(made) == 1
    assert rows[-1]["panels"] == ["p0010_01"]
    assert rows[-1]["callback"] is True and rows[-1]["callback_of"] == 1


def test_a_recall_with_no_matching_origin_stays_verbal():
    """The correct failure direction: no picture beats the wrong picture."""
    rows = _rows(
        (1, "The party steps through the shimmering gate into the cavern.", ["p0010_01"]),
        *[(n, f"Filler sentence number {n}.", ["p%04d_01" % n]) for n in range(2, 16)],
        (16, "Remember the thing nobody in this chapter ever mentioned.", []),
    )
    assert resolve_callbacks(rows) == []
    assert rows[-1]["panels"] == []


def test_a_sentence_that_already_has_its_own_panel_is_left_alone():
    """A bound sentence is describing what is on the page in front of it; trading that
    for a clever replay would swap a correct picture for a cute one."""
    rows = _rows(
        (1, "The vendor at the food truck runs out of coffee.", ["p0010_01"]),
        *[(n, f"Filler sentence number {n}.", ["p%04d_01" % n]) for n in range(2, 16)],
        (16, "This is the same food truck vendor.", ["p0099_01"]),
    )
    assert resolve_callbacks(rows) == []
    assert rows[-1]["panels"] == ["p0099_01"] and not rows[-1].get("callback")


def test_a_callback_must_reach_far_enough_back_to_read_as_deliberate():
    """A replay three sentences later is a stutter, not a return."""
    rows = _rows(
        (1, "The vendor at the food truck runs out of coffee.", ["p0010_01"]),
        (2, "He shrugs it off.", ["p0011_01"]),
        (3, "This is the same food truck vendor from before.", []),
    )
    assert resolve_callbacks(rows) == []


def test_a_callback_never_crosses_a_time_block():
    """Replaying art from the other side of a printed time skip shows the wrong era —
    the same reason every substitution in the planner is block-bounded."""
    rows = _rows(
        (1, "The vendor at the food truck runs out of coffee.", ["p0010_01"]),
        *[(n, f"Filler sentence number {n}.", ["p%04d_01" % n]) for n in range(2, 16)],
        (16, "This is the same food truck vendor, years later.", []),
    )
    rows[-1]["block"] = 1
    assert resolve_callbacks(rows) == []


# --- what the gates are allowed to permit ---------------------------------------------

def test_only_callback_panels_are_exempt_from_the_repeat_rule():
    shotlist = {"sentences": [
        {"number": 1, "panels": ["p0010_01"]},
        {"number": 9, "panels": ["p0010_01"], "callback": True},
        {"number": 5, "panels": ["p0044_01"]},
    ]}
    assert callback_panels(shotlist) == {"p0010_01"}
    assert "p0044_01" not in callback_panels(shotlist)


def test_a_shotlist_with_no_callbacks_exempts_nothing():
    """The default path must be exactly as strict as before this feature existed."""
    assert callback_panels({"sentences": [{"number": 1, "panels": ["p0001_01"]}]}) == set()
    assert callback_panels({}) == set()
