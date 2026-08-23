"""The pipeline must work on a series that is not the one it was developed against.

Every value here used to be hardcoded to Solo Leveling somewhere: the protagonist's
identity, the phrases that identify him, the grounding vocabulary, the wiki fallback
roster, and the worked examples inside the prompts. Each of those either silently did
nothing for another title or actively seeded the wrong cast, so this file uses a
completely different series throughout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FROZEN_GLOSSARY = {
    "protagonist": "Seo Jun-Ho",
    "characters": {
        "Seo Jun-Ho": ["Jun-Ho", "the man in the frost-scarred parka", "silver-eyed climber"],
        "Han Su-Yeong": ["Su-Yeong", "woman with the brass compass"],
        "Baek Cheol": ["Cheol", "man with the shaved head"],
    },
    "terms": {
        "Frozen Gate": ["ice gate", "the Gate"],
        "Awakening": ["awakened"],
    },
}


@pytest.fixture()
def frozen_bible():
    from manhwa2vid.characters.bible import rebuild_bible_from_glossary
    from manhwa2vid.models import ProjectMeta

    meta = ProjectMeta(
        slug="the-frozen-climb-ch1",
        title="The Frozen Climb",
        series_slug="the-frozen-climb",
        chapters="1",
        source_lang="en",
    )
    return rebuild_bible_from_glossary(meta, FROZEN_GLOSSARY)


def test_protagonist_comes_from_the_glossary(frozen_bible):
    """A hardcoded `== "Sung Jin-Woo"` check elected nobody for any other series."""
    assert frozen_bible.protagonist_id
    mc = frozen_bible.characters[frozen_bible.protagonist_id]
    assert mc.canonical_name == "Seo Jun-Ho"
    assert mc.role == "protagonist"


def test_protagonist_defaults_to_the_first_entry_without_a_declaration():
    from manhwa2vid.characters.bible import rebuild_bible_from_glossary
    from manhwa2vid.models import ProjectMeta

    glossary = {k: v for k, v in FROZEN_GLOSSARY.items() if k != "protagonist"}
    meta = ProjectMeta(slug="t-ch1", title="T", series_slug="t", chapters="1", source_lang="en")
    bible = rebuild_bible_from_glossary(meta, glossary)
    assert bible.characters[bible.protagonist_id].canonical_name == "Seo Jun-Ho"


def test_mc_signals_are_this_series_marks(frozen_bible):
    """The signal list used to be a literal tuple of one title's props."""
    from manhwa2vid.characters.resolve import mc_signals

    signals = mc_signals(frozen_bible)
    assert signals, "a protagonist with aliases must yield signals"
    blob = " ".join(signals)
    assert "frost-scarred" in blob or "frost" in blob
    assert "backpack" not in blob


def test_mc_signal_matching_is_specific_to_this_protagonist(frozen_bible):
    """The whole point of the gate: a generic descriptor must NOT promote to protagonist,
    and another character's distinctive mark must not either."""
    from manhwa2vid.characters.resolve import is_mc_visual_signal

    assert is_mc_visual_signal("", "the man in the frost-scarred parka", "", frozen_bible)
    assert is_mc_visual_signal("Jun-Ho", "", "", frozen_bible)
    assert not is_mc_visual_signal("", "man with black hair", "", frozen_bible)
    assert not is_mc_visual_signal("", "woman with the brass compass", "", frozen_bible)
    assert not is_mc_visual_signal("", "man with the shaved head", "", frozen_bible)


def test_grounding_keywords_come_from_this_glossary():
    """Defaults used to be coffee / food truck / healer / portal — one series' furniture."""
    from manhwa2vid.script import grounding

    try:
        grounding.configure_grounding_keywords({}, FROZEN_GLOSSARY)
        assert set(grounding.GROUNDING_KEYWORDS) == {"frozen_gate", "awakening"}
        assert grounding.narration_grounding_keywords("He steps through the ice gate.") == {"frozen_gate"}
        assert grounding.narration_grounding_keywords("He orders a coffee.") == set()
    finally:
        grounding.configure_grounding_keywords({})


def test_wiki_fallback_seeds_no_cast():
    """It used to return a curated Solo Leveling roster for ANY failed lookup."""
    from manhwa2vid.characters.wiki import _fetch_wiki_fallback

    assert _fetch_wiki_fallback("The Frozen Climb", {}) == []
    assert _fetch_wiki_fallback("Solo Leveling", {}) == []


def test_link_prompt_names_this_series_marks(frozen_bible):
    from manhwa2vid.characters.link import _link_prompt

    prompt = _link_prompt(frozen_bible)
    assert "frost-scarred" in prompt or "silver-eyed" in prompt
    assert "backpack" not in prompt.lower()
    # The mock provider branches on this substring; keep it.
    assert "linking manhwa panel" in prompt.lower()


# Names from the series this pipeline was developed against. None may appear in text that
# is SENT TO A MODEL — a worked example naming another title's cast invites the model to
# look for that cast. Comments and docstrings are exempt: they record why a rule exists.
_DEV_SERIES_NAMES = (
    "jin-woo", "jinwoo", "joo-hee", "joohee", "sangshik", "chi-yul", "chiyul",
    "hae-in", "solo leveling", "green backpack",
)


def _prompt_texts() -> dict[str, str]:
    """Every prompt string the pipeline ships, keyed by where it lives."""
    from manhwa2vid.characters import bible as bible_mod
    from manhwa2vid.characters import link as link_mod
    from manhwa2vid.script import characters as chars_mod
    from manhwa2vid.script import verify as verify_mod

    texts: dict[str, str] = {}
    prompt_dir = Path(__file__).resolve().parents[1] / "src" / "manhwa2vid" / "script" / "prompts"
    for path in sorted(prompt_dir.glob("*.txt")):
        texts[f"prompts/{path.name}"] = path.read_text(encoding="utf-8")
    texts["link._LINK_PROMPT_TEMPLATE"] = link_mod._LINK_PROMPT_TEMPLATE
    texts["verify._VERIFY_PROMPT"] = verify_mod._VERIFY_PROMPT
    texts["script.characters._REGISTRY_PROMPT"] = "\n".join(
        v for v in vars(chars_mod).values() if isinstance(v, str) and "Rules:" in v
    )
    texts["bible.naming_priority_rules"] = bible_mod.naming_priority_rules.__doc__ or ""
    return texts


@pytest.mark.parametrize("name", _DEV_SERIES_NAMES)
def test_no_development_series_names_in_prompts(name: str):
    offenders = [
        where for where, text in _prompt_texts().items() if name in text.lower()
    ]
    assert not offenders, f"{name!r} is sent to the model from: {offenders}"


def test_pipeline_never_reads_the_reference_folder():
    """The gold script and the reference channel's narration are DEVELOPMENT yardsticks;
    neither exists when the pipeline runs on a new manhwa. Constants measured from them
    (target_wpm, words_per_chapter, scorecard bands) travel fine — files do not. A future
    "just peek at the gold" shortcut must fail the build rather than silently make the
    pipeline un-runnable on a new title.
    """
    import ast

    src = Path(__file__).resolve().parents[1] / "src" / "manhwa2vid"
    offenders: list[str] = []
    for py in src.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        # Docstrings legitimately cite reference/style_profile.md as the PROVENANCE of a
        # measured constant; that is documentation, not a dependency. Collect them so
        # they can be excluded, leaving only executable string literals.
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    docstrings.add(doc)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if "reference/" in node.value and node.value not in docstrings:
                    offenders.append(f"{py.relative_to(src)}: {node.value[:70]!r}")
    assert not offenders, f"pipeline code references the dev-only reference/ folder: {offenders}"


def test_sanitize_role_strips_tier_taxonomy():
    """CharacterTier ranks page time; it is not something a narrator can say. The quest
    pass sees the tier in context and answers "supporting hunter", the bible prints
    `role: supporting hunter`, and rule 4 tells the writer to introduce people by role —
    so ch1 shipped "Kim Sangshik, a supporting hunter". Series-agnostic damage: any title
    gets "a supporting knight"."""
    from manhwa2vid.characters.bible import sanitize_role

    assert sanitize_role("supporting hunter") == "hunter"
    assert sanitize_role("supporting knight of the realm") == "knight of the realm"
    assert sanitize_role("minor vendor") == "vendor"
    # Nothing informative survives -> no role clause at all, rather than a pipeline label.
    assert sanitize_role("main character") == ""
    assert sanitize_role("supporting") == ""
    # Genuine roles are untouched, including the one quest.py branches on.
    assert sanitize_role("raid leader") == "raid leader"
    assert sanitize_role("the party's field medic") == "the party's field medic"
    assert sanitize_role("protagonist") == "protagonist"


def test_bible_prompt_never_prints_tier_as_role():
    """The read path must sanitize too: bibles persist at SERIES level across every
    chapter of a title, so state already on disk never rebuilds itself."""
    import json

    from manhwa2vid.characters.bible import format_bible_for_prompt
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible

    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="char_mc",
        characters={
            "char_mc": CharacterProfile(
                id="char_mc", canonical_name="MC", tier=CharacterTier.MAIN, role="protagonist"),
            "char_k": CharacterProfile(
                id="char_k", canonical_name="Kim", tier=CharacterTier.SUPPORTING,
                role="supporting hunter"),
        },
    )
    text = format_bible_for_prompt(bible)
    assert "role: supporting hunter" not in text
    assert "role: hunter" in text


def test_protagonist_signal_uses_the_series_own_word():
    """The +5 bonus was the literal "hunter" — Solo Leveling's noun. Dead weight on most
    titles and actively wrong on one with a large non-protagonist cast sharing it. It is
    now derived from the bible's own roles, so it resolves to whatever the title calls its
    people with no code change."""
    from manhwa2vid.characters.quest import detect_protagonist
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible

    # A title whose people are "knights" and whose protagonist is one.
    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="",
        characters={
            "char_a": CharacterProfile(id="char_a", canonical_name="Rell",
                                       tier=CharacterTier.MAIN, role="wandering knight",
                                       appearances=["p1", "p2", "p3"], confidence=0.9),
            "char_b": CharacterProfile(id="char_b", canonical_name="Vesh",
                                       tier=CharacterTier.SUPPORTING, role="knight",
                                       appearances=["p1"], confidence=0.5),
            "char_c": CharacterProfile(id="char_c", canonical_name="Doran",
                                       tier=CharacterTier.SUPPORTING, role="knight",
                                       appearances=["p2"], confidence=0.5),
        },
    )
    assert detect_protagonist(bible, {}) == "char_a"
    # No franchise term is required for the election to work at all.
    bare = SeriesBible(
        series_slug="s", title="S", protagonist_id="",
        characters={"char_a": CharacterProfile(
            id="char_a", canonical_name="Rell", tier=CharacterTier.MAIN,
            appearances=["p1"], confidence=0.9)},
    )
    assert detect_protagonist(bare, {}) == "char_a"


def test_pronoun_is_inferred_from_the_descriptors_vision_already_wrote():
    """The pronoun field is filled by the quest/search passes and is wrong often enough to
    corrupt narration. Frozen Player recorded Skaya as "he" while three descriptors call
    her a "woman in white robes", and shipped "He nominates Jun-Ho" in one beat with "her
    staff" for the same character two beats later. Solo Leveling had the same bug on its
    healer. The gender words are English, never a title's own vocabulary."""
    from manhwa2vid.characters.bible import effective_pronoun, infer_pronoun_from_descriptors
    from manhwa2vid.models import CharacterProfile, CharacterTier

    woman = CharacterProfile(
        id="a", canonical_name="Skaya", tier=CharacterTier.SUPPORTING, pronoun="he",
        descriptors=["woman in white robes holding a staff",
                     "woman with long light blue hair"])
    man = CharacterProfile(
        id="b", canonical_name="Vesh", tier=CharacterTier.SUPPORTING, pronoun="they",
        descriptors=["man in a cowboy hat and tan coat", "man with long blonde hair"])
    assert effective_pronoun(woman) == "she"
    assert effective_pronoun(man) == "he"

    # One mention decides nothing, and a mixed set is left alone rather than guessed.
    thin = CharacterProfile(id="c", canonical_name="Rell", tier=CharacterTier.SUPPORTING,
                            pronoun="they", descriptors=["woman in a long coat"])
    mixed = CharacterProfile(id="d", canonical_name="Kai", tier=CharacterTier.SUPPORTING,
                             pronoun="they",
                             descriptors=["woman in armour", "man in armour", "figure in armour"])
    assert infer_pronoun_from_descriptors(thin) == ""
    assert infer_pronoun_from_descriptors(mixed) == ""
    assert effective_pronoun(mixed) == "they"      # the recorded value survives
