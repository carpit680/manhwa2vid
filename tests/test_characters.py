"""Character bible and normalization tests."""

from __future__ import annotations

from manhwa2vid.characters.bible import merge_profile, naming_priority_rules, slugify_char_id
from manhwa2vid.models import CharacterProfile, CharacterTier, SceneCard, SeriesBible
from manhwa2vid.script.characters import _alias_lookup, _normalize_speakers, normalize_scene_cards


def test_slugify_char_id() -> None:
    assert slugify_char_id("Sung Jin-Woo") == "char_sung_jin_woo"


def test_merge_profile_preserves_appearances() -> None:
    bible = SeriesBible(series_slug="test", title="Test")
    merge_profile(
        bible,
        CharacterProfile(
            id="char_hero",
            canonical_name="Hero",
            tier=CharacterTier.MAIN,
            appearances=["p001"],
        ),
    )
    merge_profile(
        bible,
        CharacterProfile(
            id="char_hero",
            canonical_name="Hero",
            tier=CharacterTier.SUPPORTING,
            appearances=["p002"],
        ),
    )
    profile = bible.characters["char_hero"]
    assert profile.tier == CharacterTier.MAIN
    assert profile.appearances == ["p001", "p002"]


def test_naming_priority_rules_includes_mc_guidance() -> None:
    rules = naming_priority_rules()
    assert "protagonist" in rules.lower() or "mc" in rules.lower()


def test_normalize_speakers_uses_registry() -> None:
    lookup = _alias_lookup(
        {
            "Sung Jin-Woo": ["Jin-Woo", "Sung", "Mr. Sung"],
        }
    )
    assert _normalize_speakers(["Jin-Woo", "Sung"], lookup) == ["Sung Jin-Woo"]


def test_normalize_scene_cards() -> None:
    cards = [
        SceneCard(
            panel_ids=["p0002_01"],
            speakers=["Jin-Woo"],
            action="Intro",
            people=[],
        )
    ]
    lookup = _alias_lookup({"Sung Jin-Woo": ["Jin-Woo"]})
    out = normalize_scene_cards(cards, lookup)
    assert out[0].speakers == ["Sung Jin-Woo"]
