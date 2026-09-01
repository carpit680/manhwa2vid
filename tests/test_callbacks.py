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


def test_a_character_remembering_never_triggers_a_replay():
    """"Remembering the weeks spent in a hospital bed makes him shiver" is the STORY
    remembering. The first regex matched it because the verb had no closing word
    boundary — found by running the detector over a real generated script."""
    assert not is_recall("Remembering the weeks spent in a hospital bed makes him shiver.")
    assert not is_recall("He remembers his mother and keeps walking.")


def test_a_scene_transition_is_not_a_callback():
    """"Back in the hospital room" is one of the commonest openers in a recap and means
    "we have moved", not "you have seen this before"."""
    assert not is_recall("Back in his hospital room, Jun-Ho sits on his bed.")
    assert not is_recall("Back in the blood-stained temple, the situation deteriorates.")
    assert is_recall("Back when the party first stepped through the gate, nobody worried.")


# --- the closing coda -----------------------------------------------------------------

class TestClosingCoda:
    """The outro must not freeze the story's last panel.

    Measured on both titles that exceeded the hold limit: the >18s holds were the FINAL
    run on the FINAL panel, because the closing sentences inherit whatever the story
    ended on and the planner cannot help — `_gap_spare` looks forward into an empty
    range and backward only within SCENE_RADIUS, all of it already shown. Frozen Player
    ch3-4 held one image for 19.1 seconds this way.
    """

    def _rows(self, n_story=5, n_outro=2):
        rows = [{"number": i, "beat_id": 1, "block": 0, "text": f"Story {i}.",
                 "panels": [f"p{i:02d}"]} for i in range(1, n_story + 1)]
        rows += [{"number": n_story + j, "beat_id": 2, "block": 0,
                  "text": "Subscribe for more.", "panels": [], "outro": True}
                 for j in range(1, n_outro + 1)]
        return rows

    def test_the_outro_takes_an_unused_panel_rather_than_the_last_story_shot(self):
        from manhwa2vid.script.callbacks import resolve_closing_coda

        rows = self._rows()
        rows[2]["panels"] = []            # p03 never claimed — real unused art
        order = [f"p{i:02d}" for i in range(1, 6)]
        coda = resolve_closing_coda(rows, order)
        assert coda is not None
        assert coda["panels"] == ["p03"], "new art beats a repeat"
        assert coda["coda"] and coda["callback"]

    def test_it_replays_only_when_there_is_nothing_unused(self):
        """A repeat is the fallback, not the first choice — and it must be marked so
        the no-repeated-panels gate permits it deliberately."""
        from manhwa2vid.script.callbacks import callback_panels, resolve_closing_coda

        rows = self._rows()
        order = [f"p{i:02d}" for i in range(1, 6)]
        coda = resolve_closing_coda(rows, order)
        assert coda["panels"] == ["p01"], "falls back to the opening shot"
        assert coda["panels"][0] in callback_panels({"sentences": rows})

    def test_a_short_closing_run_is_left_as_a_normal_held_beat(self):
        """One trailing sentence on the last panel is ordinary editing, not a freeze."""
        from manhwa2vid.script.callbacks import resolve_closing_coda

        rows = self._rows(n_outro=1)
        assert resolve_closing_coda(rows, [f"p{i:02d}" for i in range(1, 6)]) is None

    def test_a_closing_run_that_already_has_art_is_untouched(self):
        from manhwa2vid.script.callbacks import resolve_closing_coda

        rows = self._rows()
        rows[-1]["panels"] = ["p05"]
        assert resolve_closing_coda(rows, [f"p{i:02d}" for i in range(1, 6)]) is None

    def test_nothing_happens_without_a_shot_list_to_close_on(self):
        from manhwa2vid.script.callbacks import resolve_closing_coda

        rows = [{"number": 1, "beat_id": 1, "block": 0, "text": "x", "panels": [],
                 "outro": True},
                {"number": 2, "beat_id": 1, "block": 0, "text": "y", "panels": [],
                 "outro": True}]
        assert resolve_closing_coda(rows, ["p01"]) is None
