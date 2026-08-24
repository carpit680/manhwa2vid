"""Targeted few-shot rewrite passes: transitions (3-part move), exposition (told
through a person's reaction), and voice (flat delivery re-read with rhythm and a point
of view). Each is the fix for a defect that survived every prompt rule aimed at it —
see script/passes.py."""

from __future__ import annotations

from manhwa2vid.models import SceneCard, ScriptBeat, SeriesBible
from manhwa2vid.script.passes import (
    is_dialogue_heavy_exposition,
    rewrite_exposition,
    rewrite_transition,
    rewrite_voice,
    transition_needs_rework,
    voice_is_flat,
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


def test_voice_is_flat_needs_all_three_signals_absent():
    """Whole-script scorecard bands say the SCRIPT is flat but not which beats to fix.
    This is the per-beat version: uniform sentence lengths AND no evaluative read AND no
    casual epithet. Any one of the three present means the beat already carries voice and
    must be left alone, or the pass churns the good beats along with the bad."""
    flat = ScriptBeat(
        beat_id=1, panel_ids=["p"],
        narration=(
            "Jun-Ho lies broken on the cold ground, gasping for breath as blood pools around him. "
            "He clutches his bleeding hand, reminding himself that he is an E-rank hunter."
        ),
    )
    assert voice_is_flat(flat)

    # A short punch line is rhythm — leave it.
    assert not voice_is_flat(ScriptBeat(
        beat_id=1, panel_ids=["p"],
        narration="Jun-Ho lies broken on the cold ground as blood pools around him. Rank one.",
    ))
    # An evaluative read is a point of view — leave it.
    assert not voice_is_flat(ScriptBeat(
        beat_id=1, panel_ids=["p"],
        narration=(
            "Jun-Ho lies broken on the ground while the thing that put him there has barely "
            "moved. He tells himself he is only an E-rank hunter and keeps bleeding anyway."
        ),
    ))
    # A casual epithet is the register — leave it.
    assert not voice_is_flat(ScriptBeat(
        beat_id=1, panel_ids=["p"],
        narration=(
            "Bro is face down in his own blood on the cold stone floor of the dungeon. "
            "He reminds himself that he is only an E-rank hunter with nothing left to give."
        ),
    ))
    # A one-sentence beat has nothing to vary; the other passes own those.
    assert not voice_is_flat(ScriptBeat(beat_id=1, panel_ids=["p"], narration="He walks on."))


def test_rewrite_voice_keeps_the_facts_and_calls_the_model():
    beat = ScriptBeat(
        beat_id=3, panel_ids=["p"],
        narration="Jun-Ho lies broken on the ground, gasping. He reminds himself he is an E-rank hunter.",
    )
    llm = _EchoLLM("Jun-Ho is face down in his own blood. Rank one. Bro cannot catch a break.")
    out = rewrite_voice(beat, _bible(), [], {}, scene_cards=[], llm=llm)
    assert llm.calls
    assert "Original narration:" in llm.calls[0][1]
    assert "Rank one." in out


def test_rewrite_voice_falls_back_to_the_original_on_empty_reply():
    beat = ScriptBeat(beat_id=1, panel_ids=["p"], narration="Original text here, unchanged.")
    out = rewrite_voice(beat, _bible(), [], {}, scene_cards=[], llm=_EchoLLM(""))
    assert out.strip() == "Original text here, unchanged."
