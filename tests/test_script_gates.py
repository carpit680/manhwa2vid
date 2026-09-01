"""Prose-texture gates on the narration, and name-integrity now that it blocks.

The hardening brief ranks these highest, from ~950 comments across 16 videos and 6
channels: viewers punish script errors roughly two orders of magnitude harder than voice
quality. The top craft complaint in the niche is a name-consistency failure; the second is
noun repetition. Complaints about robotic TTS timbre drew 0-2 likes.

Every band here is measured with the same counters used on the reference SRT — parity with
reference/profile_srt.py is pinned in tests/test_measure.py — because a threshold derived
from one counter and enforced by another is a mistake this project has already made.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manhwa2vid.qa import FAIL, PASS, WARN


def _report(tmp_path: Path, narration: str, *, glossary: dict | None = None,
            title: str = "Test Series") -> dict:
    """Run the script-stage gates over one narration and return {gate: result}."""
    from manhwa2vid.models import ProjectMeta, SourceLanguage, SourceType, project_paths, save_json
    from manhwa2vid.qa import QAGateFailure, QAReport, enforce
    from manhwa2vid.script.read import glossary_names
    from manhwa2vid.script.story_first import (
        _QUOTED_MIN_PER_1K, _SHORT_MIN_PCT, _VERBS_MIN_PER_1K,
    )
    from manhwa2vid.measure.script_text import (
        dialogue_verb_density, noun_repetition, quoted_span_rate, sentence_length_stats,
    )
    from manhwa2vid.script.story_first import unknown_names

    paths = project_paths(tmp_path)
    (tmp_path / "glossary.json").write_text(json.dumps(
        glossary or {"characters": {"Hero": ["the hero"]}, "terms": {}}
    ))
    allowed = glossary_names(paths) | {title, *title.split()}

    out: dict[str, tuple[str, dict]] = {}
    out["name-integrity"] = (unknown_names(narration, allowed), {})
    out["dialogue-verb-density"] = (dialogue_verb_density(narration), {})
    out["quoted-dialogue"] = (quoted_span_rate(narration), {})
    out["sentence-length"] = (sentence_length_stats(narration), {})
    out["noun-repetition"] = (noun_repetition(narration, exempt=allowed), {})
    return {k: v[0] for k, v in out.items()}


def test_the_series_title_is_not_an_unknown_name(tmp_path: Path) -> None:
    """Regression from promoting name-integrity to blocking: it immediately flagged the
    project's own TITLE. The closing ask names the series ("Where <title> goes from
    here...", script/outro.py) and the title lives in meta, not the glossary."""
    r = _report(tmp_path, "Where Test Series goes from here is worth waiting for.",
                title="Test Series")
    assert r["name-integrity"] == []


def test_name_integrity_still_catches_an_invented_name(tmp_path: Path) -> None:
    r = _report(tmp_path, "Then Roland Vex drew his blade against the crowned monster.")
    assert "Roland Vex" in r["name-integrity"]


def test_the_two_historical_false_positives_stay_dead(tmp_path: Path) -> None:
    """Both audited videos shipped while this gate was failing, and section G3 of the
    2026-08-26 audit blamed exactly these: a grade prefix and a noun-boundary merge."""
    glossary = {"characters": {"Jun-Ho": [], "Sung Jin-Woo": []}, "terms": {"E-Rank": []}}
    r = _report(tmp_path, "He is an E-Rank Hunter now.", glossary=glossary)
    assert r["name-integrity"] == []
    r = _report(tmp_path, "He sees the affluent modern Earth Jun-Ho sees outside his window.",
                glossary=glossary)
    assert r["name-integrity"] == []


def test_dialogue_verb_floor_is_a_fraction_of_the_reference() -> None:
    """Reference measures 31.34/1k with this counter. The floor is 18 — a floor, not a
    target. Frozen Player ships 6.98 and Solo Leveling 2.77."""
    from manhwa2vid.script.story_first import _REF_VERBS_PER_1K, _VERBS_MIN_PER_1K

    assert _VERBS_MIN_PER_1K < _REF_VERBS_PER_1K
    from manhwa2vid.measure.script_text import dialogue_verb_density

    silent = "The blade fell. The room went cold. Nothing moved for a long moment. " * 8
    assert dialogue_verb_density(silent)["per_1k"] < _VERBS_MIN_PER_1K


def test_short_sentence_floor_does_not_fail_the_reference() -> None:
    """The brief proposed 25% of sentences under 8 words. The reference measures 21.5%, so
    25% would fail the channel being imitated — and Solo Leveling at 23.7% would fail while
    being MORE reference-like than the reference."""
    from manhwa2vid.script.story_first import _REF_SHORT_PCT, _SHORT_MIN_PCT

    assert _SHORT_MIN_PCT < _REF_SHORT_PCT, "the floor must sit below the reference"
    assert _SHORT_MIN_PCT < 23.7, "Solo Leveling must not fail a floor it already beats"


def test_noun_repetition_finds_the_apothecary_case(tmp_path: Path) -> None:
    """The second-most-liked craft complaint in the niche: a bare noun repeated where a
    pronoun belonged, with a viewer offering to count it."""
    r = _report(tmp_path, "The apothecary moved. " * 7 + "Something else happened later.")
    assert r["noun-repetition"]["findings"][0]["word"] == "apothecary"


def test_noun_repetition_exempts_the_cast(tmp_path: Path) -> None:
    """A recap MUST repeat its protagonist's name; the reference channel does."""
    glossary = {"characters": {"Sung Jin-Woo": ["Jin-Woo"]}, "terms": {}}
    text = ("Sung Jin-Woo ran. Sung Jin-Woo turned. Sung Jin-Woo waited. "
            "Sung Jin-Woo left. Sung Jin-Woo returned. Sung Jin-Woo stopped.")
    assert _report(tmp_path, text, glossary=glossary)["noun-repetition"]["findings"] == []


def test_quoted_dialogue_counts_actual_quotes(tmp_path: Path) -> None:
    r = _report(tmp_path, 'He says, "Then leave." She does not answer him at all.')
    assert r["quoted-dialogue"]["quoted_spans"] == 1


def test_quoted_span_counter_ignores_apostrophes(tmp_path: Path) -> None:
    """The counter originally treated the ASCII apostrophe as a quote delimiter, so every
    contraction matched. It reported the reference channel at 1.62 "quoted spans" per 1000
    words when the spans it found were fragments like "re nothing" out of "they're
    nothing" — and that number nearly rewrote the writer's prompt."""
    from manhwa2vid.measure.script_text import quoted_span_rate

    contractions = "They're nothing. He's done. It isn't over. She'd know. We'll see."
    assert quoted_span_rate(contractions)["quoted_spans"] == 0

    real = 'He turns and says, "This can\'t be happening." Then he runs.'
    assert quoted_span_rate(real)["quoted_spans"] == 1
    assert quoted_span_rate('She whispers “That’s right.”')["quoted_spans"] == 1


def test_the_writer_is_told_to_quote_because_the_reference_does(tmp_path: Path) -> None:
    """The prompt used to forbid verbatim quotes outright. Re-measuring the reference with
    a working counter found 87 real double-quoted lines in 75k words — short, sharp ones
    like "That's right." — so the instruction contradicted the channel being imitated.

    Pinned across EVERY persona (2026-08-31): the voice block is selectable now, and a
    new narrator that quietly reinstated the ban would undo this silently."""
    from manhwa2vid.script.freeform import _system_for
    from manhwa2vid.script.personas import PERSONAS

    for name in PERSONAS:
        system = _system_for(name)
        assert "Never quote a line" not in system, name
        lowered = system.lower()
        assert "verbatim" in lowered and "quote" in lowered, name
