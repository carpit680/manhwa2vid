"""The draft-viewer-judge loop: the listener's seat nothing else in the pipeline occupies.

Every other gate checks the script against SOURCE material. These check it against the
only question the product is judged on — can a listener follow it, and is it any fun.
"""

from __future__ import annotations

from manhwa2vid.models import ScriptBeat
from manhwa2vid.script.judge import pick_best_script
from manhwa2vid.script.viewer import (
    ViewerComplaint,
    ViewerReport,
    as_listener_hears,
    beats_for_complaint,
    issues_by_beat,
    review_script,
)

BLIND = [
    ScriptBeat(beat_id=1, panel_ids=["p"],
               narration="Rell falls in the dark chamber as the sentinel raises its spear."),
    # No time marker, no name: exactly the shape the reviewer kept catching.
    ScriptBeat(beat_id=2, panel_ids=["p"],
               narration="A crowd gathers at the museum. He shatters the ice and steps out."),
]
MARKED = [
    ScriptBeat(beat_id=1, panel_ids=["p"],
               narration="Rell falls in the dark chamber as the sentinel raises its spear."),
    ScriptBeat(beat_id=2, panel_ids=["p"],
               narration="Twenty-five years later, a crowd gathers at the museum. "
                         "The ice around Rell shatters and he steps out."),
]


def test_listener_sees_only_what_a_listener_gets():
    """No beat ids, no panel ids, no evidence — if a character cannot be identified from
    the words alone, the viewer cannot identify them either. That is the whole point."""
    heard = as_listener_hears(BLIND, hook="A hero wakes up in the wrong century.")
    assert "p" not in heard.split()
    assert "beat" not in heard.lower()
    assert heard.startswith("A hero wakes up")
    assert "shatters the ice" in heard


def test_viewer_complains_about_an_unmarked_jump(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    blind = review_script(BLIND, "", {})
    marked = review_script(MARKED, "", {})
    assert blind is not None and marked is not None
    assert blind.lost and not marked.lost
    assert blind.score < marked.score


def test_per_criterion_scores_differentiate_where_a_scalar_could_not():
    """The bug this fix targets: a single 1-10 ask scored three visibly different
    candidates 6/10 each. Four independent 1-5 axes must be able to disagree with each
    other and still sum to a legible total."""
    strong = ViewerReport(followable=5, told_not_listed=5, payoffs_landed=4, rhythm=4)
    weak = ViewerReport(followable=2, told_not_listed=2, payoffs_landed=3, rhythm=2)
    assert strong.score == 9.0
    assert weak.score == 4.5
    assert strong.score > weak.score
    # A candidate can be followable but flat, or lively but confusing — the axes must be
    # free to disagree, which a single scalar cannot represent at all.
    followable_but_flat = ViewerReport(followable=5, told_not_listed=1, payoffs_landed=3, rhythm=3)
    lively_but_lost = ViewerReport(followable=1, told_not_listed=5, payoffs_landed=3, rhythm=3)
    assert followable_but_flat.score == lively_but_lost.score  # same total, different shape
    assert followable_but_flat.followable != lively_but_lost.followable


def test_complaints_route_to_the_beat_they_came_from():
    """A complaint that cannot be located does nothing, so quotes map back by exact match
    first and stemmed overlap after — models paraphrase their own quotes constantly."""
    exact = ViewerReport(lost=[ViewerComplaint(quote="He shatters the ice and steps out.",
                                               why="who is he")])
    assert beats_for_complaint("He shatters the ice and steps out.", BLIND) == [2]
    # Paraphrased quote still lands on the right beat.
    assert beats_for_complaint("he shatters ice and then steps out", BLIND) == [2]
    # Unrelated text lands nowhere rather than on beat 1 by accident.
    assert beats_for_complaint("a completely different sentence about soup", BLIND) == []

    issues = issues_by_beat(exact, BLIND)
    assert list(issues) == [2]
    assert "viewer" in issues[2][0] and "who is he" in issues[2][0]


def test_blind_candidate_loses_the_tournament(monkeypatch):
    """The seeded-defect test this whole loop exists for: a candidate that narrates a time
    jump blind must lose to one that marks it."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    blind_text = as_listener_hears(BLIND)
    marked_text = as_listener_hears(MARKED)

    win, _ = pick_best_script([blind_text, marked_text], {}, tiebreak=[4.0, 9.0])
    assert win == 1
    # And the result does not depend on which one was handed over first.
    win2, _ = pick_best_script([marked_text, blind_text], {}, tiebreak=[9.0, 4.0])
    assert win2 == 0


def test_single_candidate_degrades_without_calling_a_judge():
    win, why = pick_best_script(["only one"], {})
    assert win == 0 and "single" in why


def test_selection_prefers_the_livelier_candidate_when_the_viewer_cannot_separate_them():
    """The viewer scored three visibly different candidates 6/10 each and the judge split
    both comparisons, so selection fell through to index order and picked a flat draft.
    A model's 1-10 score has no resolution here; the reference-derived voice measures do."""
    import sys
    sys.path.insert(0, "src")
    from manhwa2vid.script.scorecard import _EVAL_RE, _short_sentence_fraction

    flat = [ScriptBeat(beat_id=i, panel_ids=["p"], narration=(
        "The group proceeds toward the location and the leader explains the situation "
        "to the assembled members of the expedition.")) for i in range(1, 4)]
    lively = [ScriptBeat(beat_id=1, panel_ids=["p"], narration=(
        "Rell hits the floor hard. He barely gets up. The riders are in no hurry at all.")),
        ScriptBeat(beat_id=2, panel_ids=["p"], narration=(
            "Nobody moves. Vesh almost says something, then doesn't.")),
        ScriptBeat(beat_id=3, panel_ids=["p"], narration="Twenty years. Just like that.")]

    assert _short_sentence_fraction(lively) > _short_sentence_fraction(flat)
    lively_text = " ".join(b.narration for b in lively)
    flat_text = " ".join(b.narration for b in flat)
    assert len(_EVAL_RE.findall(lively_text)) > len(_EVAL_RE.findall(flat_text))
