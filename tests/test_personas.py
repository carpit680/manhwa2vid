"""Selectable narrator voices, and the invariants that must hold across all of them.

The voice block used to be hard-coded in `freeform._SYSTEM`, which made trying a
different narrator a global, unversioned, unmeasurable edit. It is now selected by
`script.persona`. These tests pin the two things that matter: the default path is
unchanged, and no persona may quietly drop a rule that is craft rather than voice.
"""

from __future__ import annotations

import re

from manhwa2vid.script.freeform import _system_for
from manhwa2vid.script.personas import CURRENT, DEFAULT_PERSONA, PERSONAS, voice_block


def test_the_default_persona_is_the_voice_that_shipped():
    """An unconfigured run must be byte-identical to the pre-persona pipeline."""
    assert DEFAULT_PERSONA == "current"
    assert voice_block(None) == CURRENT
    assert CURRENT in _system_for(None)


def test_an_unknown_persona_falls_back_instead_of_raising():
    """A typo in config.yaml should not destroy a run that has already paid for its
    read pass and its writer windows."""
    assert voice_block("writer_bolde") == CURRENT


def test_every_persona_keeps_the_craft_rules():
    """Preamble and SHAPE are shared, not per-persona: a narrator may change how it
    sounds, never whether it honours a printed time jump or ends on the forward edge."""
    for name in PERSONAS:
        system = _system_for(name)
        assert "Read the WHOLE thing first as a story" in system, name
        assert "Honour every explicit time jump" in system, name
        assert "forward edge" in system, name
        assert "Only the words the voice actor reads aloud." in system, name


def test_every_persona_still_bans_narrating_the_frame():
    """Talking ABOUT the work is now allowed; narrating the picture as a picture is
    not, and that distinction is the whole point of the rewrite."""
    for name in PERSONAS:
        lowered = _system_for(name).lower()
        assert "we see" in lowered, name          # ...as something it names and forbids
        assert "never invent a name" in lowered, name


def test_the_writer_personas_lift_the_first_person_ban_deliberately():
    """The ban came from measuring a DIFFERENT channel at 0.24 first-person per 1k.
    The writer-narrator spends the pronoun on purpose, so the ban must be gone from
    those arms — and still present in the control."""
    assert 'Zero first person: never "I" or "we"' in voice_block("current")
    for name in ("writer_light", "writer_medium", "writer_bold"):
        block = voice_block(name)
        assert "Zero first person" not in block, name
        assert 'You may say "I"' in block, name
        assert "never in the opening hook" in block, name


def test_the_writer_personas_carry_all_six_human_moves():
    """The user named these explicitly; a persona missing one is not the persona."""
    for name in ("writer_light", "writer_medium", "writer_bold"):
        block = voice_block(name)
        for move in ("EXPLAIN WHAT THE CHAPTER ASSUMES", "COMPARE IT TO SOMETHING REAL",
                     "REMEMBER THINGS FOR THE VIEWER", "NOTE THE SOURCE",
                     "SAY WHEN THE WORK STUMBLES", "TALK ABOUT THE ART"):
            assert move in block, f"{name} is missing {move}"


def test_each_writer_arm_states_a_budget():
    """"Without overdoing it" is a rate, so every arm has to state one — otherwise the
    three arms are the same prompt and the bake-off measures nothing."""
    budgets = [voice_block(n) for n in ("writer_light", "writer_medium", "writer_bold")]
    for block in budgets:
        assert "BUDGET" in block
    assert len({b for b in budgets}) == 3, "the arms are not actually different"


def test_no_persona_names_a_development_series():
    """tests/test_series_agnostic.py scans module-level strings for dev-series names;
    this asserts the same thing at the composed-prompt level, where a persona built by
    concatenation would otherwise slip past a constant-only scan."""
    banned = ("jin-woo", "jinwoo", "joo-hee", "sangshik", "chi-yul", "solo leveling",
              "frozen player", "deok-gu", "jun-ho")
    for name in PERSONAS:
        lowered = _system_for(name).lower()
        for token in banned:
            assert token not in lowered, f"{name} names {token}"


def test_quotable_lines_block_offers_real_printed_lines(tmp_path):
    """The writer works from images and re-reading lettering is the hardest thing we
    ask of it, so the exact strings are handed over as data. Truncated bubbles are
    excluded — "THE JOB WHERE YOUR LIFE'S ON THE" is a real scene-card line, and
    offering it invites quoting half a sentence."""
    import json

    from manhwa2vid.script.freeform import _quotable_block

    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "0001.png").write_bytes(b"")
    cards = [
        {"panel_ids": ["p0001_01"],
         "source_text": 'char_a: "MY NAME IS SUNG JIN-WOO." / char_a: "Haah"'},
        {"panel_ids": ["p0001_02"],
         "source_text": 'char_b: "THE JOB WHERE YOUR LIFE\'S ON THE"'},
    ]
    (tmp_path / "scene_cards.json").write_text(json.dumps(cards))
    block = _quotable_block({"scene_json": tmp_path / "scene_cards.json"}, [pages / "0001.png"])
    assert "MY NAME IS SUNG JIN-WOO." in block
    assert "LIFE'S ON THE" not in block, "a truncated bubble was offered for quoting"


def test_quotable_block_is_silent_without_scene_cards(tmp_path):
    """Older projects have no cards; the block is a bonus and must never be an error."""
    from manhwa2vid.script.freeform import _quotable_block

    assert _quotable_block({}, []) == ""
    assert _quotable_block({"scene_json": tmp_path / "missing.json"}, []) == ""
