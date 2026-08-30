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


class TestReportingVerbsAreNotNounRepetition:
    """`noun-repetition` and `dialogue-verb-density` were pulling against each other.

    After the writer's prompt was changed to demand a reporting verb every ~32 words,
    Frozen Player's script warned "tell x5 in a 200-word window". The reference channel
    does far more of it: its worst window holds "says" NINE times, against this gate's
    limit of four. The gate is for a bare repeated noun a pronoun should have replaced,
    which a speech verb is not.
    """

    def test_a_repeated_reporting_verb_is_not_a_finding(self):
        from manhwa2vid.measure.script_text import noun_repetition

        text = " ".join(["He tells her and she tells him no."] * 12)
        assert noun_repetition(text)["findings"] == []

    def test_a_genuinely_repeated_noun_is_still_caught(self):
        """The exemption must not blunt what the gate is actually for."""
        from manhwa2vid.measure.script_text import noun_repetition

        text = " ".join(["The warehouse burned beside the warehouse gate."] * 12)
        words = [f["word"] for f in noun_repetition(text)["findings"]]
        assert any("warehouse" in w for w in words)

    def test_the_density_gate_still_counts_what_the_repetition_gate_now_ignores(self):
        """Exempting a verb from one gate must not remove it from the other."""
        from manhwa2vid.measure.script_text import dialogue_verb_density

        text = " ".join(["He tells her and she tells him no."] * 12)
        assert dialogue_verb_density(text)["dialogue_verbs"] == 24


class TestGatesThatBlockedALegitimateScript:
    """Both of these failed Solo Leveling's regenerated script on correct narration."""

    def test_a_possessive_in_a_prepositional_phrase_is_not_number_disagreement(self):
        """"they" = the healers, "his" = Jin-Woo. Two people, correct English — and it
        blocked the whole script stage."""
        from manhwa2vid.script.lint import mixed_number_pronouns

        assert mixed_number_pronouns(
            "Song admits there is nothing they can do for his missing arm."
        ) == []

    def test_the_direct_object_defect_is_still_caught(self):
        """The construction the gate exists for never crosses a preposition."""
        from manhwa2vid.script.lint import mixed_number_pronouns

        assert mixed_number_pronouns("They grit his teeth.")
        assert mixed_number_pronouns("They clench his fists.")
        assert mixed_number_pronouns("They lower his head.")
        assert mixed_number_pronouns("They wipe her brow.")

    def test_a_separable_possession_is_two_people_not_one(self):
        """Second false positive to block a script stage, and a direct object, so the
        prepositional narrowing above did not reach it.

        "The group readily agrees. They trust his skills." — they = the party, his =
        Mr. Song. The gate exists for a character called "they" and "his" in one breath,
        and the tell is a possessive of something INALIENABLY that person's own.
        """
        from manhwa2vid.script.lint import mixed_number_pronouns

        assert mixed_number_pronouns("They trust his skills.") == []
        assert mixed_number_pronouns("The group readily agrees. They trust his skills.") == []
        assert mixed_number_pronouns("They follow his lead.") == []
        assert mixed_number_pronouns("They question his judgment.") == []

    def test_the_ambiguous_middle_is_deliberately_not_flagged(self):
        """"They raise his sword" cannot be resolved by a regex. It is left alone on
        purpose: a false positive here blocks the pipeline, a miss is one sentence."""
        from manhwa2vid.script.lint import mixed_number_pronouns

        assert mixed_number_pronouns("They raise his sword.") == []

    def test_an_unknown_real_world_place_warns_rather_than_blocks(self):
        """`unknown_names` documents "real-world places" as false-positive class two and
        calls itself advisory. "South Korea" — the writer completing "Seoul, South
        Korea", absent from the source OCR — blocked a script stage while it was
        promoted to blocking."""
        from manhwa2vid.script.story_first import unknown_names

        strangers = unknown_names(
            'In Seoul, South Korea, Jin-Woo is known as the "World\'s Weakest".',
            {"Seoul", "Jin-Woo"},
        )
        assert "South Korea" in strangers, "still reported — it is worth reading"
        # The gate's severity is asserted where it is raised; see the report status in
        # generate_story_first_script, which passes "warn" rather than False.
