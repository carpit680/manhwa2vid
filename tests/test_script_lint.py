"""Script lint tests."""

from __future__ import annotations

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
