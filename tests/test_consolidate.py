"""Character consolidation tests."""

from __future__ import annotations

from manhwa2vid.characters.consolidate import consolidate_profiles, merge_profiles_into
from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible


def test_merge_profiles_into() -> None:
    bible = SeriesBible(
        series_slug="test",
        title="Test",
        characters={
            "char_sung_jin_woo": CharacterProfile(
                id="char_sung_jin_woo",
                canonical_name="Sung Jin-Woo",
                tier=CharacterTier.MAIN,
                appearances=["p001"],
            ),
            "char_jin_woo": CharacterProfile(
                id="char_jin_woo",
                canonical_name="Jin-Woo",
                tier=CharacterTier.MINOR,
                appearances=["p002"],
            ),
        },
        protagonist_id="char_jin_woo",
    )
    merge_profiles_into(bible, "char_sung_jin_woo", "char_jin_woo")
    assert "char_jin_woo" not in bible.characters
    assert bible.protagonist_id == "char_sung_jin_woo"
    assert "p002" in bible.characters["char_sung_jin_woo"].appearances


def test_max_main_enforced() -> None:
    bible = SeriesBible(
        series_slug="test",
        title="Test",
        characters={
            "char_a": CharacterProfile(id="char_a", canonical_name="A", tier=CharacterTier.MAIN, appearances=["p1"] * 5),
            "char_b": CharacterProfile(id="char_b", canonical_name="B", tier=CharacterTier.MAIN, appearances=["p2"]),
        },
    )
    config = {"characters": {"max_main": 1}}
    consolidate_profiles(bible, config)
    mains = [p for p in bible.characters.values() if p.tier == CharacterTier.MAIN]
    assert len(mains) == 1
