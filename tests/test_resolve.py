"""Identity resolution tests."""

from __future__ import annotations

from manhwa2vid.characters.resolve import descriptor_overlap_score, resolve_character_ref
from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible


def test_resolve_alias_jin_woo_to_sung_jin_woo() -> None:
    bible = SeriesBible(
        series_slug="solo-leveling",
        title="Solo Leveling",
        characters={
            "char_sung_jin_woo": CharacterProfile(
                id="char_sung_jin_woo",
                canonical_name="Sung Jin-Woo",
                tier=CharacterTier.MAIN,
                aliases=["Jin-Woo", "Sung"],
            )
        },
    )
    assert resolve_character_ref("Jin-Woo", "", bible) == "char_sung_jin_woo"


def test_descriptor_fuzzy_match() -> None:
    score = descriptor_overlap_score("guy in green backpack", "man with green backpack")
    assert score >= 0.4
