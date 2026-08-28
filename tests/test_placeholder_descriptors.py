"""A cast label must never be read aloud to the viewer.

`read`'s prompt forbids inventing names for unnamed characters; the model complies by
filing the DESCRIPTOR as the name, so `glossary.json` gained the key
`"Unnamed Man in Cowboy Hat"`. Glossary keys are both the writer's canonical-name list
and the set `name-integrity` scores against, so the label was not merely permitted — it
was the sanctioned way to refer to that character, and Frozen Player's narration said
"the unnamed man in a cowboy hat agreed with her opinion".

Caught by reading the script, not by any metric: every prose gate passed on that draft.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manhwa2vid.script.lint import strip_placeholder_descriptors
from manhwa2vid.script.read import merge_cast_into_glossary


class TestGlossaryKeys:
    """Layer one: the label never becomes a canonical name."""

    @pytest.fixture
    def paths(self, tmp_path: Path) -> dict[str, Path]:
        return {"root": tmp_path, "glossary": tmp_path / "glossary.json"}

    def _chars(self, paths):
        return json.loads(paths["glossary"].read_text())["characters"]

    def test_the_observed_defect(self, paths):
        merge_cast_into_glossary([{"name": "Unnamed Man in Cowboy Hat"}], paths)
        assert "Unnamed Man in Cowboy Hat" not in self._chars(paths)
        assert "Man in Cowboy Hat" in self._chars(paths), "the descriptor is still useful"

    def test_a_bare_placeholder_carries_nothing_and_is_refused(self, paths):
        merge_cast_into_glossary([{"name": "Unnamed"}, {"name": "unidentified"}], paths)
        # Nothing was added, so nothing is written — the file need not even exist.
        assert not paths["glossary"].exists() or self._chars(paths) == {}

    def test_real_names_are_untouched(self, paths):
        merge_cast_into_glossary(
            [{"name": "Seo Jun-Ho", "aliases": ["Specter"]}, {"name": "Frost Queen"}], paths
        )
        assert set(self._chars(paths)) == {"Seo Jun-Ho", "Frost Queen"}

    def test_a_human_glossary_key_is_still_never_rewritten(self, paths):
        """The repair surface outranks the normaliser: if a person decided that key
        stays, it stays."""
        paths["glossary"].write_text(json.dumps({"characters": {"Unnamed Rider": ["x"]}}))
        merge_cast_into_glossary([{"name": "Unnamed Rider", "aliases": ["y"]}], paths)
        chars = self._chars(paths)
        assert "Unnamed Rider" in chars and "x" in chars["Unnamed Rider"]


class TestNarrationStrip:
    """Layer two: the invariant holds on finished prose whatever the glossary says."""

    def test_the_two_frozen_player_sentences(self):
        assert strip_placeholder_descriptors(
            "The unnamed man in a cowboy hat agreed with her opinion."
        ) == "The man in a cowboy hat agreed with her opinion."
        assert strip_placeholder_descriptors(
            "The unnamed woman with a sword added that she believed Specter was best."
        ) == "The woman with a sword added that she believed Specter was best."

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("An unnamed man drew his gun.", "A man drew his gun."),
            ("An unnamed archer fired.", "An archer fired."),
            ("A unnamed rider approached.", "A rider approached."),
        ],
    )
    def test_the_article_re_agrees_with_the_new_head_word(self, text, expected):
        assert strip_placeholder_descriptors(text) == expected

    def test_an_unrelated_article_is_not_re_agreed(self):
        """A blanket a/an fixup pass would rewrite this to 'a hour'."""
        assert (
            strip_placeholder_descriptors("She waited an hour, then an unnamed healer came.")
            == "She waited an hour, then a healer came."
        )

    def test_predicative_use_is_ordinary_english_and_survives(self):
        for t in ("The swordsman stayed unnamed.", "Two of the five remain unnamed."):
            assert strip_placeholder_descriptors(t) == t

    def test_sentence_count_is_preserved(self):
        """`plan_shots` returns None when the sidecar's sentence count diverges from the
        narration's, silently dropping the whole shot plan back to airtime weighting."""
        from manhwa2vid.script.sentences import split_sentences

        text = (
            "The unnamed man in a cowboy hat agreed. He drew. "
            "An unnamed woman with a sword nodded once."
        )
        assert len(split_sentences(strip_placeholder_descriptors(text))) == len(
            split_sentences(text)
        )

    def test_clean_narration_is_returned_byte_identical(self):
        text = "Jun-Ho grips his blade. He tells her they aren't the type to croak.\n\nShe laughs."
        assert strip_placeholder_descriptors(text) == text
