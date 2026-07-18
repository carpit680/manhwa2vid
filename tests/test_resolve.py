"""Identity resolution tests."""

from __future__ import annotations

from manhwa2vid.characters.resolve import descriptor_overlap_score, resolve_character_ref
from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible


def test_resolve_alias_jin_woo_to_sung_jin_woo() -> None:
    bible = SeriesBible(
        series_slug="solo-leveling",
        title="Solo Leveling",
        protagonist_id="char_sung_jin_woo",
        characters={
            "char_sung_jin_woo": CharacterProfile(
                id="char_sung_jin_woo",
                canonical_name="Sung Jin-Woo",
                tier=CharacterTier.MAIN,
                aliases=["Jin-Woo", "Sung"],
                descriptors=["man with green backpack", "E-Rank hunter"],
            )
        },
    )
    assert resolve_character_ref("Jin-Woo", "", bible) == "char_sung_jin_woo"
    assert resolve_character_ref("", "guy with green backpack", bible) == "char_sung_jin_woo"


def test_generic_descriptor_does_not_resolve_to_mc() -> None:
    bible = SeriesBible(
        series_slug="solo-leveling",
        title="Solo Leveling",
        protagonist_id="char_sung_jin_woo",
        characters={
            "char_sung_jin_woo": CharacterProfile(
                id="char_sung_jin_woo",
                canonical_name="Sung Jin-Woo",
                tier=CharacterTier.MAIN,
                aliases=["Jin-Woo"],
                descriptors=["man with green backpack"],
            ),
            "char_guy_with_sword": CharacterProfile(
                id="char_guy_with_sword",
                canonical_name="guy with sword",
                tier=CharacterTier.MINOR,
                descriptors=["guy with sword"],
            ),
        },
    )
    assert resolve_character_ref("", "guy with sword", bible) == "char_guy_with_sword"
    assert resolve_character_ref("", "guy with black hair", bible) is None


def test_descriptor_fuzzy_match() -> None:
    score = descriptor_overlap_score("guy in green backpack", "man with green backpack")
    assert score >= 0.4
