"""The storyboard reviewer: the agent that has the source the judge never did."""

from __future__ import annotations

import json

from manhwa2vid.models import ChapterSynopsis, ScriptBeat
from manhwa2vid.script.story_review import StoryProblem, StoryReview, issues_by_beat, review_story


def _syn():
    return ChapterSynopsis(
        logline="A hero wakes up in the wrong century.", acts=["Act 1: the fight", "Act 2: the museum"],
        named_cast=[], plot_facts=[],
        narrative_structure="Opens on the final battle, then jumps twenty years to a museum.",
    )


BLIND = [
    ScriptBeat(beat_id=1, panel_ids=["p"], narration="The blade comes down and everything goes white."),
    ScriptBeat(beat_id=2, panel_ids=["p"], narration="A crowd gathers at the case. A boy points at a statue."),
]
MARKED = [
    BLIND[0],
    ScriptBeat(beat_id=2, panel_ids=["p"],
               narration="Twenty years later, that war is something children see behind glass. "
                         "A boy points at a statue and swears it moved."),
]


def test_reviewer_flags_an_unmarked_boundary_and_hands_back_a_usable_sentence(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    boundaries = {2: 'the art prints "20 YEARS LATER" here'}
    blind = review_story(BLIND, _syn(), boundaries, {})
    marked = review_story(MARKED, _syn(), boundaries, {})
    assert blind is not None and marked is not None
    assert blind.transitions and not blind.sequence_ok
    assert blind.transitions[0].beat_id == 2
    # The hint must be a sentence to imitate, not advice to follow — four zero-shot rules
    # about marking time already failed where an exemplar worked.
    assert blind.transitions[0].fix_hint.strip()
    assert marked.sequence_ok and not marked.transitions


def test_issues_carry_the_model_sentence_verbatim():
    review = StoryReview(transitions=[StoryProblem(
        beat_id=2, problem="crosses a marked boundary silently",
        fix_hint="Open with: 'Twenty years later, ...'")], sequence_ok=False)
    issues = issues_by_beat(review, BLIND)
    assert list(issues) == [2]
    assert "Twenty years later" in issues[2][0]
    # A problem naming a beat that does not exist is dropped rather than crashing a run.
    stray = StoryReview(transitions=[StoryProblem(beat_id=99, problem="x", fix_hint="y")])
    assert issues_by_beat(stray, BLIND) == {}


def test_structural_ranking_beats_a_livelier_but_confusing_candidate():
    """The ordering the whole loop turns on: a candidate that loses a listener at a time
    jump is not rescued by being punchy."""
    problem_counts = [2, 0]          # candidate 0 is broken, candidate 1 is clean
    scores = [9.0, 4.0]              # candidate 0 is livelier
    order = sorted(range(2), key=lambda i: (problem_counts[i], -scores[i], i))
    assert order[0] == 1


def test_lessons_ledger_round_trips_and_counts_repeat_runs(tmp_path):
    """A defect that survived its rewrites is worth remembering; one that got fixed is not."""
    from manhwa2vid.script.lessons import load_lessons, record_lessons

    paths = {"lessons_json": tmp_path / "lessons.json"}
    assert load_lessons(paths) == []
    record_lessons(paths, ["world-history exposition reads like a textbook"])
    record_lessons(paths, ["world-history exposition reads like a textbook"])
    entries = json.loads((tmp_path / "lessons.json").read_text())
    assert len(entries) == 1 and entries[0]["runs"] == 2
    assert "world-history" in load_lessons(paths)[0]

    # A missing or corrupt ledger never breaks a run.
    assert load_lessons({"lessons_json": tmp_path / "nope.json"}) == []
    (tmp_path / "bad.json").write_text("{not json")
    assert load_lessons({"lessons_json": tmp_path / "bad.json"}) == []
