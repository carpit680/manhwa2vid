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


def test_two_named_characters_never_merge_on_fuzzy_alias():
    """"Jun-Ho's old friend" is a RELATION to Jun-Ho, not Jun-Ho. Fuzzy containment
    merged the Association president into the protagonist; the verifier's cast sheet
    then called the protagonist bald and flagged every beat he appeared in — 61% of a
    script shipped from the fallback path off one corrupted alias."""
    from manhwa2vid.characters.resolve import profiles_are_same_person
    from manhwa2vid.models import CharacterProfile, CharacterTier

    junho = CharacterProfile(
        id="char_seo_jun_ho", canonical_name="Seo Jun-Ho",
        tier=CharacterTier.MAIN, aliases=["Jun-Ho", "Specter"],
    )
    deokgu = CharacterProfile(
        id="char_deok_gu", canonical_name="Deok-gu",
        tier=CharacterTier.SUPPORTING,
        aliases=["the Player Association president", "Jun-Ho's old friend"],
    )
    assert not profiles_are_same_person(junho, deokgu)
    assert not profiles_are_same_person(deokgu, junho)


def test_exact_alias_identity_still_merges_named_profiles():
    """"Specter" as a separate profile IS Seo Jun-Ho — his alias list says so exactly."""
    from manhwa2vid.characters.resolve import profiles_are_same_person
    from manhwa2vid.models import CharacterProfile, CharacterTier

    junho = CharacterProfile(
        id="char_seo_jun_ho", canonical_name="Seo Jun-Ho",
        tier=CharacterTier.MAIN, aliases=["Jun-Ho", "Specter"],
    )
    specter = CharacterProfile(
        id="char_specter", canonical_name="Specter",
        tier=CharacterTier.SUPPORTING, aliases=[],
    )
    assert profiles_are_same_person(junho, specter)


def test_relational_alias_does_not_resolve_panel_refs_to_the_relative():
    """The linking path must not bind a 'his old friend' reference to the possessor."""
    from manhwa2vid.characters.resolve import _name_match_score
    from manhwa2vid.models import CharacterProfile, CharacterTier

    junho = CharacterProfile(
        id="char_seo_jun_ho", canonical_name="Seo Jun-Ho",
        tier=CharacterTier.MAIN, aliases=["Jun-Ho"],
    )
    assert _name_match_score("Jun-Ho's old friend", junho) == 0.0
    assert _name_match_score("Jun-Ho", junho) >= 0.85
