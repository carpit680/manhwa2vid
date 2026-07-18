"""Story-first script helpers and lint tests."""

from __future__ import annotations

from manhwa2vid.models import CharacterProfile, CharacterTier, ScriptBeat, SeriesBible
from manhwa2vid.script.generate import _attach_missing_panels_to_beats, _panel_sort_key
from manhwa2vid.script.lint import (
    find_hedge_violations,
    lint_aside_overuse,
    lint_hedging,
    lint_mc_name_spam,
    local_sanitize_narration,
)


def test_attach_missing_panels_to_nearest_beat() -> None:
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p0002_01"], narration="Hook."),
        ScriptBeat(beat_id=2, panel_ids=["p0005_01"], narration="Fight."),
        ScriptBeat(beat_id=3, panel_ids=["p0010_01"], narration="City."),
    ]
    all_panels = ["p0002_01", "p0003_01", "p0005_01", "p0006_01", "p0010_01"]
    result = _attach_missing_panels_to_beats(all_panels, beats)
    covered = {pid for beat in result for pid in beat.panel_ids}
    assert covered == set(all_panels)
    assert len(result) == 3  # no caption filler beats
    assert "p0003_01" in result[0].panel_ids or "p0003_01" in result[1].panel_ids


def test_panel_sort_key_orders_pages() -> None:
    ids = ["p0010_02", "p0002_01", "p0010_01"]
    assert sorted(ids, key=_panel_sort_key) == ["p0002_01", "p0010_01", "p0010_02"]


def test_hedge_lint_flags_possibly() -> None:
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="He walks, possibly hurt."),
        ScriptBeat(beat_id=2, panel_ids=["p2"], narration="He joins the party."),
    ]
    report = lint_hedging(beats)
    assert 1 in report
    assert "possibly" in report[1]
    assert 2 not in report


def test_local_sanitize_strips_common_hedges() -> None:
    text = local_sanitize_narration("He is seen sitting, possibly recovering, highlighting the risks.")
    assert "possibly" not in text.lower()
    assert "highlighting" not in text.lower()
    assert "is seen" not in text.lower()


def test_mc_name_spam_after_hook() -> None:
    bible = SeriesBible(
        series_slug="solo-leveling",
        title="Solo Leveling",
        protagonist_id="char_sung_jin_woo",
        characters={
            "char_sung_jin_woo": CharacterProfile(
                id="char_sung_jin_woo",
                canonical_name="Sung Jin-Woo",
                tier=CharacterTier.MAIN,
            )
        },
    )
    config = {"script": {"max_mc_full_name_after_hook": 2}}
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="Sung Jin-Woo is the weakest hunter."),
        ScriptBeat(beat_id=2, panel_ids=["p2"], narration="Sung Jin-Woo walks home."),
        ScriptBeat(beat_id=3, panel_ids=["p3"], narration="Sung Jin-Woo meets Song."),
        ScriptBeat(beat_id=4, panel_ids=["p4"], narration="Sung Jin-Woo enters the gate."),
    ]
    report = lint_mc_name_spam(beats, bible, config)
    assert 4 in report
    assert "mc_full_name_spam" in report[4]


def test_aside_overuse() -> None:
    config = {"script": {"max_narrator_asides": 1}}
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="He survives. NGL that was rough."),
        ScriptBeat(beat_id=2, panel_ids=["p2"], narration="And look, bro, he is still going."),
    ]
    report = lint_aside_overuse(beats, config)
    assert 2 in report
    assert find_hedge_violations("He may be dying") == ["may be"]
