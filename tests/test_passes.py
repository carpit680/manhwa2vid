"""Targeted few-shot rewrite passes: transitions (3-part move) and exposition (told
through a person's reaction). Both are the fix for a defect present in EVERY sampled
candidate, not a selection problem — see script/passes.py."""

from __future__ import annotations

from manhwa2vid.models import SceneCard, ScriptBeat, SeriesBible
from manhwa2vid.script.passes import (
    is_dialogue_heavy_exposition,
    rewrite_exposition,
    rewrite_transition,
    transition_needs_rework,
)


def _bible() -> SeriesBible:
    return SeriesBible(series_slug="s", title="S")


class _EchoLLM:
    """Returns a fixed string, recording that it was called."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        self.calls.append((system, user))
        return self.reply


def test_transition_needs_rework_flags_a_single_sentence_beat():
    """A beat that only marks the jump has no room left for a stake sentence."""
    beat = ScriptBeat(
        beat_id=1, panel_ids=["p1"],
        narration="Twenty-five years ago, a towering ice pillar stands in the blizzard.",
    )
    assert transition_needs_rework(beat)


def test_transition_needs_rework_passes_a_cue_plus_stake_beat():
    beat = ScriptBeat(
        beat_id=1, panel_ids=["p1"],
        narration=(
            "That's the last thing he sees for twenty-five years. Now, five heroes stand "
            "before the same dungeon, and only one of them can go up those stairs."
        ),
    )
    assert not transition_needs_rework(beat)


def test_rewrite_transition_carries_the_previous_beats_last_sentence():
    prev = ScriptBeat(beat_id=1, panel_ids=["p1"], narration="He waves goodbye to his friends.")
    beat = ScriptBeat(
        beat_id=2, panel_ids=["p2"],
        narration="Twenty-five years ago, a towering ice pillar stands in the blizzard.",
    )
    llm = _EchoLLM("He waves back one final time. Now, twenty-five years later, the city looks nothing like it once did.")
    out = rewrite_transition(beat, prev, _bible(), [], {}, scene_cards=[], llm=llm)
    assert llm.calls, "the model must be called"
    assert "He waves goodbye to his friends." in llm.calls[0][1]
    assert "twenty-five years later" in out.lower()


def test_rewrite_transition_handles_no_previous_beat():
    beat = ScriptBeat(beat_id=1, panel_ids=["p1"], narration="Twenty-five years ago, an ice pillar stands.")
    llm = _EchoLLM("Twenty-five years ago, an ice pillar stands amid the fight.")
    out = rewrite_transition(beat, None, _bible(), [], {}, scene_cards=[], llm=llm)
    assert "opening beat" in llm.calls[0][1]
    assert out


def test_is_dialogue_heavy_exposition_true_for_talk_heavy_panels():
    cards = [
        SceneCard(
            panel_ids=["p1"],
            action="",
            source_text="Shim: In twenty five years humanity has cleared only one floor.",
        ),
    ]
    beat = ScriptBeat(beat_id=1, panel_ids=["p1"], narration="x")
    assert is_dialogue_heavy_exposition(beat, cards)


def test_is_dialogue_heavy_exposition_false_for_action_heavy_panels():
    cards = [
        SceneCard(panel_ids=["p1"], action="he lunges forward and strikes the beast", source_text=""),
    ]
    beat = ScriptBeat(beat_id=1, panel_ids=["p1"], narration="x")
    assert not is_dialogue_heavy_exposition(beat, cards)


def test_rewrite_exposition_calls_the_model_with_evidence():
    cards = [
        SceneCard(
            panel_ids=["p1"],
            action="",
            source_text="Shim: In twenty five years humanity has cleared only one floor.",
        ),
    ]
    beat = ScriptBeat(
        beat_id=1, panel_ids=["p1"],
        narration="In the twenty-five years since, humanity has cleared one additional floor.",
    )
    llm = _EchoLLM("Shim can barely say it. In twenty-five years, humanity cleared one more floor.")
    out = rewrite_exposition(beat, _bible(), [], {}, scene_cards=cards, llm=llm)
    assert llm.calls
    assert "Shim can barely say it" in out


def test_rewrite_transition_falls_back_to_original_on_empty_reply():
    beat = ScriptBeat(beat_id=1, panel_ids=["p1"], narration="Original text.")
    out = rewrite_transition(beat, None, _bible(), [], {}, scene_cards=[], llm=_EchoLLM(""))
    assert out.strip() == "Original text."
