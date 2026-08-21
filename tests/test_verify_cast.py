"""The verifier's cast sheet: what can and cannot contradict an identity."""

from __future__ import annotations

from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible, VisualProfile
from manhwa2vid.script.verify import _cast_visuals, _split_marks


def _profile(**kw) -> CharacterProfile:
    kw.setdefault("id", "char_x")
    kw.setdefault("canonical_name", "X")
    kw.setdefault("tier", CharacterTier.SUPPORTING)
    return CharacterProfile(**kw)


def test_state_marks_are_separated_from_identity():
    """The two real false-positive sources: a president called "bald" because a joke in
    the dialogue said so, and a protagonist described as a masked swordsman in a coat
    while he sits in hospital pyjamas a chapter later. Both must land in CURRENT-STATE."""
    p = _profile(
        descriptors=["bald association president", "the Player Association president"],
        visual=VisualProfile(hair="black", build="tall", outfit="dark suit"),
    )
    stable, mutable = _split_marks(p)
    assert "black" in stable and "tall" in stable
    assert any("bald" in m for m in mutable)
    assert any("suit" in m for m in mutable)

    q = _profile(descriptors=["masked swordsman in the black coat", "silver-eyed"])
    stable_q, mutable_q = _split_marks(q)
    assert any("masked" in m for m in mutable_q)
    assert "silver-eyed" in stable_q


def test_cast_sheet_labels_both_groups():
    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="char_x",
        characters={"char_x": _profile(
            tier=CharacterTier.MAIN,
            descriptors=["masked swordsman in a black coat"],
            visual=VisualProfile(hair="silver"),
        )},
    )
    sheet = _cast_visuals(bible)
    assert "STABLE: silver" in sheet
    assert "CURRENT-STATE" in sheet
    assert "[PROTAGONIST]" in sheet


def test_cast_sheet_survives_a_profile_with_no_marks():
    bible = SeriesBible(
        series_slug="s", title="S",
        characters={"char_x": _profile(descriptors=[], visual=VisualProfile())},
    )
    assert "do not flag any naming claim" in _cast_visuals(bible)


def test_prompt_forbids_state_contradictions_as_major():
    from manhwa2vid.script.verify import _VERIFY_PROMPT

    assert "STABLE" in _VERIFY_PROMPT
    assert "NEVER a finding" in _VERIFY_PROMPT
