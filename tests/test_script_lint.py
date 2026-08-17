"""Script lint tests."""

from __future__ import annotations

import pytest

from manhwa2vid.models import ScriptBeat
from manhwa2vid.script.lint import find_violations, lint_beats


def test_find_violations_flags_character() -> None:
    hits = find_violations("A character walks into the room.", ["character"])
    assert "character" in hits


def test_lint_beats_reports_offending_beats() -> None:
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p001"], narration="Clean narration."),
        ScriptBeat(beat_id=2, panel_ids=["p002"], narration="Two characters fight."),
    ]
    config = {"characters": {"ban_words": ["character", "two characters"]}}
    report = lint_beats(beats, config)
    assert 2 in report
    assert 1 not in report


def test_lint_mc_attribution_flags_off_screen_mc() -> None:
    from manhwa2vid.models import PanelCast, CharacterRef, ScriptBeat, SeriesBible, CharacterProfile, CharacterTier
    from manhwa2vid.script.lint import lint_mc_attribution

    bible = SeriesBible(
        series_slug="t",
        title="T",
        protagonist_id="char_mc",
        characters={"char_mc": CharacterProfile(id="char_mc", canonical_name="MC", tier=CharacterTier.MAIN)},
    )
    attribution = [
        PanelCast(panel_id="p002", people=[CharacterRef(ref="char_other", name_used="Other")]),
    ]
    beats = [ScriptBeat(beat_id=2, panel_ids=["p002"], narration="The MC watches from afar.")]
    report = lint_mc_attribution(beats, bible, attribution, {"characters": {"mc_labels": ["MC"]}})
    assert 2 in report


def test_name_budget_is_script_wide_not_per_beat() -> None:
    """Per-beat rotation cannot satisfy a script-wide rule.

    rotate_protagonist_name kept the first name use in EVERY beat, so 18 beats produced
    18 name uses against a budget of 2 — 11 of the 13 lint flags surviving on ch1.
    """
    from manhwa2vid.models import CharacterProfile, CharacterTier, ScriptBeat, SeriesBible
    from manhwa2vid.script.lint import enforce_mc_name_budget, lint_mc_name_spam

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="Sung Jin-Woo", tier=CharacterTier.MAIN, pronoun="he"
    )
    config = {"script": {"max_mc_full_name_after_hook": 2}}

    beats = [
        ScriptBeat(beat_id=i, panel_ids=[f"p{i:04d}_01"], narration="Sung Jin-Woo walks on.")
        for i in range(1, 11)
    ]

    assert lint_mc_name_spam(beats, bible, config), "fixture must start in violation"

    out = enforce_mc_name_budget(beats, bible, config)

    assert not lint_mc_name_spam(out, bible, config)
    total = sum(b.narration.count("Sung Jin-Woo") for b in out)
    assert total == 3, f"hook anchor + 2 allowance, got {total}"
    assert out[-1].narration.startswith("He "), "later beats must read as pronouns"


def test_name_budget_preserves_beat_one_anchor() -> None:
    """Beat 1 must still name the protagonist — that's the anchor the rest rotates against."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, ScriptBeat, SeriesBible
    from manhwa2vid.script.lint import enforce_mc_name_budget

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="Sung Jin-Woo", tier=CharacterTier.MAIN, pronoun="he"
    )
    beats = [ScriptBeat(beat_id=1, panel_ids=["p0001_01"], narration="Sung Jin-Woo bleeds out.")]

    out = enforce_mc_name_budget(beats, bible, {})

    assert out[0].narration == "Sung Jin-Woo bleeds out."


def test_bible_role_grounds_intro_clause() -> None:
    """The recap prompt REQUIRES an intro clause from the cast list; lint must allow it.

    'Lee Joo-hee, the party's healer' was flagged ungrounded:healer because panel art
    never contains the word 'healer' — punishing the exact clause the prompt mandates.
    """
    from manhwa2vid.models import (
        CharacterProfile,
        CharacterRef,
        PanelCast,
        SceneCard,
        ScriptBeat,
        SeriesBible,
    )
    from manhwa2vid.script.lint import lint_panel_grounding

    bible = SeriesBible(series_slug="s", title="S")
    bible.characters["char_joo"] = CharacterProfile(
        id="char_joo", canonical_name="Lee Joo-hee", role="party healer"
    )
    attribution = [PanelCast(panel_id="p0001_01", people=[CharacterRef(ref="char_joo")])]
    cards = [SceneCard(panel_ids=["p0001_01"], action="a woman scolds a man", dialogue_summary="")]
    beats = [
        ScriptBeat(
            beat_id=1,
            panel_ids=["p0001_01"],
            narration="Lee Joo-hee, the party's healer, snaps at him.",
        )
    ]

    assert lint_panel_grounding(beats, cards), "without the bible it must still flag"
    assert not lint_panel_grounding(beats, cards, bible=bible, attribution=attribution)


def test_invented_healer_still_flagged_when_absent() -> None:
    """The grounding rule must keep catching a healer nobody in the beat actually is."""
    from manhwa2vid.models import (
        CharacterProfile,
        CharacterRef,
        PanelCast,
        SceneCard,
        ScriptBeat,
        SeriesBible,
    )
    from manhwa2vid.script.lint import lint_panel_grounding

    bible = SeriesBible(series_slug="s", title="S")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="Sung Jin-Woo", role="E-Rank hunter"
    )
    attribution = [PanelCast(panel_id="p0001_01", people=[CharacterRef(ref="char_mc")])]
    cards = [SceneCard(panel_ids=["p0001_01"], action="a man walks alone", dialogue_summary="")]
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p0001_01"], narration="A healer patches him up.")
    ]

    flagged = lint_panel_grounding(beats, cards, bible=bible, attribution=attribution)
    assert flagged.get(1) == ["ungrounded:healer"]


@pytest.mark.parametrize(
    "text,expected",
    [
        # Object slot after a transitive verb — the ch1 bug ("tells he to stay").
        ("Sung Jin-Woo waits. Kim tells Sung Jin-Woo to stay back.", "tells him to stay back."),
        # Object slot after a preposition.
        ("Sung Jin-Woo waits. She walks with Sung Jin-Woo.", "walks with him."),
        # Subject slot stays nominative.
        ("Sung Jin-Woo waits. Sung Jin-Woo enters the gate.", "He enters the gate."),
        # Possessive still wins over both.
        ("Sung Jin-Woo waits. Sung Jin-Woo's leg bleeds.", "His leg bleeds."),
    ],
)
def test_rotation_uses_object_case_where_required(text, expected) -> None:
    """Rotated narration is SPOKEN — a case error is audible, not cosmetic."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import rotate_protagonist_name

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="Sung Jin-Woo", tier=CharacterTier.MAIN, pronoun="he"
    )

    out = rotate_protagonist_name(text, bible)

    assert expected in out, out
    assert "tells he " not in out and "with he." not in out
