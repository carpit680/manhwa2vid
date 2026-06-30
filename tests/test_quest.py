"""Character quest tests."""

from __future__ import annotations

from manhwa2vid.characters.quest import evaluate_sufficiency
from manhwa2vid.models import CharacterProfile, CharacterTier, VisualProfile


def test_evaluate_sufficiency_protagonist_gaps() -> None:
    profile = CharacterProfile(
        id="char_mc",
        canonical_name="Sung Jin-Woo",
        tier=CharacterTier.MAIN,
        role="protagonist",
    )
    gaps = evaluate_sufficiency(profile, protagonist_id="char_mc")
    assert "visual.hair" in gaps
    assert "visual.outfit" in gaps
    assert "narration_labels" in gaps


def test_evaluate_sufficient_when_complete() -> None:
    profile = CharacterProfile(
        id="char_mc",
        canonical_name="Sung Jin-Woo",
        tier=CharacterTier.MAIN,
        aliases=["Jin-Woo"],
        pronoun="he",
        narration_labels=["MC", "Sung Jin-Woo"],
        source_chapters=[1, 2],
        appearances=["p1", "p2", "p3", "p4", "p5"],
        visual=VisualProfile(hair="black", outfit="casual"),
    )
    gaps = evaluate_sufficiency(profile, protagonist_id="char_mc")
    assert gaps == []
