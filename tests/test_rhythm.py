"""The opener-rhythm pass: function-words-only edits, measured openers, safe refusals.

Root cause it repairs (2026-08-31): the reference channel links consecutive actions
("Then" alone opens 7.5% of its sentences) while our scripts ran reported-speech
chains with no connective tissue — "he tells" x23 on Solo Leveling, back-to-back
openers at 3-6x the reference rate. Prompt-only fixes failed twice when measured, so
the pass is deterministic code and these tests pin its safety envelope.
"""

from __future__ import annotations

from manhwa2vid.script.rhythm import (
    _content_words,
    apply_rhythm_pass,
    opener_profile,
)


def test_same_subject_reporting_chain_merges_with_then():
    text = "He asks if the gate is stable. He tells the crew to fall back."
    out, rec = apply_rhythm_pass(text)
    assert out == "He asks if the gate is stable, then tells the crew to fall back."
    assert rec["merges"] == [(1, 2)]


def test_merge_preserves_the_content_word_multiset():
    """The meaning guard the density pass lacked: only function words may change."""
    text = "He asks if the gate is stable. He tells the crew to fall back."
    out, _ = apply_rhythm_pass(text)
    assert _content_words(out) == _content_words(text)


def test_name_subjects_never_merge():
    """Eliding a NAME drops a glossary-name occurrence — the count the audit
    acceptance and the lint both watch. Only pronoun subjects fold."""
    text = "Jun-Ho asks if the gate is stable. Jun-Ho tells the crew to fall back."
    out, rec = apply_rhythm_pass(text)
    assert rec["merges"] == []
    assert "Jun-Ho asks" in out and "Jun-Ho tells" in out


def test_quoted_dialogue_blocks_a_merge():
    text = 'He says "hold the line" to them. He tells the crew to fall back.'
    _, rec = apply_rhythm_pass(text)
    assert rec["merges"] == []


def test_non_reporting_verbs_do_not_merge():
    """Elision is only meaning-safe on the says-class frame."""
    text = "He runs to the gate without a word. He tells the crew to fall back."
    _, rec = apply_rhythm_pass(text)
    assert rec["merges"] == []


def test_back_to_back_opener_gets_then():
    text = "He grabs the sword from the altar. He swings it at the statue."
    out, rec = apply_rhythm_pass(text)
    assert "Then he swings it at the statue." in out
    assert rec["insertions"] == 1


def test_no_then_before_a_stative_verb():
    """"Then he is terrified" is not rhythm, it is a mistake."""
    text = "He stares at the beast on the throne. He is terrified of it."
    out, _ = apply_rhythm_pass(text)
    assert "Then he is" not in out


def test_no_then_on_the_naming_idiom():
    """"They call him the World's Weakest" states a standing fact; "Then" would
    misstate it as something that happens next. Caught reading the SL diff."""
    text = "They watch him limp into the dungeon. They call him the World's Weakest."
    out, _ = apply_rhythm_pass(text)
    assert "Then they call" not in out


def test_no_then_on_an_it_subject():
    """"Then it radiates a heavy pressure" turns scene description into a false
    event. Also caught reading the SL diff."""
    text = "It towers over the whole party. It radiates a heavy pressure."
    out, _ = apply_rhythm_pass(text)
    assert "Then it" not in out


def test_merged_sentence_never_also_gets_a_then_prefix():
    """Read aloud, "Then he tells X, then explains Y" stacks the word — the first
    dry run produced exactly that, twice on Solo Leveling."""
    text = (
        "He checks the seal on the floor. "
        "He tells the group to stay calm. He explains the exit is sealed."
    )
    out, _ = apply_rhythm_pass(text)
    assert "Then he tells the group to stay calm, then" not in out
    assert ", then explains the exit is sealed." in out


def test_never_twice_in_a_row():
    text = (
        "He grabs the rope from the wall. He climbs the ledge above the pit. "
        "He jumps the gap at the top."
    )
    out, _ = apply_rhythm_pass(text)
    assert out.count("Then ") <= 1


def test_outro_paragraph_ships_verbatim():
    outro = "He hopes you subscribe for part two. He means it this time."
    out, _ = apply_rhythm_pass("He fights the boss. He wins the fight.\n\n" + outro)
    assert outro in out


def test_idempotency_record_blocks_a_second_application(tmp_path):
    paths = {"debug": tmp_path}
    text = "He asks if the gate is stable. He tells the crew to fall back."
    out1, _ = apply_rhythm_pass(text, paths)
    out2, rec2 = apply_rhythm_pass(out1, paths)
    assert out2 == out1 and rec2.get("skipped")


def test_opener_profile_counts_what_the_gate_reads():
    text = "He runs at the gate. He jumps over it. Then he lands hard. But it holds."
    p = opener_profile(text)
    assert p["sentences"] == 4
    assert p["pronoun_open_pct"] == 50.0
    assert p["connector_pct"] == 50.0
    assert p["b2b_pct"] == 25.0
