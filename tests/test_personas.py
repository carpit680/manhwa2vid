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
    budgets = [voice_block(n, 2750) for n in ("writer_light", "writer_medium", "writer_bold")]
    for block in budgets:
        assert "BUDGET" in block
    assert len({b for b in budgets}) == 3, "the arms are not actually different"


def test_the_aside_rate_thins_as_the_script_grows():
    """The approved 6-minute render ran 2.42 asides per 1000 words and was called good;
    the ask was for roughly half OVER LONG VIDEOS. A flat halving would have thinned the
    short video too, so the rate tapers: a 20-chapter script gets about half the density
    of a 2-chapter one, and the short one is left as approved."""
    from manhwa2vid.script.personas import aside_rate_per_1k

    short, long = aside_rate_per_1k(1100), aside_rate_per_1k(11000)
    assert short > long, "the rate must thin with length"
    assert 2.2 <= short <= 2.6, "the approved short-form density must survive"
    assert long <= short / 1.9, "long form must land near half"
    # Monotone, so no length is accidentally denser than a shorter one.
    rates = [aside_rate_per_1k(w) for w in (500, 1100, 2750, 5500, 11000, 22000)]
    assert rates == sorted(rates, reverse=True)


def test_an_unknown_length_errs_toward_more_voice():
    """A persona that fails to appear is invisible to everything except the
    persona-voice floor; one that appears too often is obvious on first listen. When
    the length is unknown, err toward the side that gets noticed."""
    from manhwa2vid.script.personas import aside_rate_per_1k

    assert aside_rate_per_1k(None) >= aside_rate_per_1k(11000)
    assert aside_rate_per_1k(0) == aside_rate_per_1k(None)


def test_the_budget_scales_with_the_script_it_is_written_for():
    """The first budgets said "about three or four times across the whole script" — a
    fixed total, which means a dense 6-minute recap and an almost silent 52-minute one
    from the same words. Whatever the phrasing, the instruction must DIFFER by length;
    that is the property, not any particular sentence."""
    short = voice_block("writer_light", 1100)
    long = voice_block("writer_light", 11000)
    assert short != long, "the same instruction was given for both lengths"
    assert "every" in short and "every" in long, "the rate is what scales"


def test_the_control_arm_gets_no_aside_budget():
    """`current` has no asides to budget, and appending one would quietly change the
    control arm of the bake-off."""
    assert "BUDGET" not in voice_block("current", 2750)
    assert voice_block("current", 2750) == voice_block("current", None) == CURRENT


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


def test_the_budget_states_a_count_as_well_as_a_rate():
    """Measured on the first 20-chapter run: a budget stated only as an interval
    ("about once every 830 words") produced ZERO asides in 13,637 words, while the
    earlier absolute phrasing produced 3 on a 1,100-word script and 9 on a 2,700-word
    one. A large interval reads as permission to skip; a total reads as a target."""
    for words, expected in ((1265, "3 times"), (12649, "15 times")):
        block = voice_block("writer_light", words)
        assert expected in block, words
        assert "every" in block, "the rate must survive too — it is what scales"


def test_the_count_scales_with_length_and_intensity():
    from manhwa2vid.script.personas import voice_block as vb

    def total(arm, words):
        line = [l for l in vb(arm, words).splitlines() if "BUDGET" in l][0]
        return int(line.split("about ")[1].split(" times")[0])

    assert total("writer_light", 1265) < total("writer_light", 12649)
    assert total("writer_light", 3162) < total("writer_bold", 3162)
    assert total("writer_light", 500) >= 2, "a short script still gets a voice"
