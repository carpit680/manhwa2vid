"""Sentence identity is load-bearing; the splitter must not invent sentences.

The naive split broke on honorifics: Solo Leveling's shipped script carried EIGHT
phantom "Mr." sentences plus three mid-sentence breaks ("waving Mr. / Song over…"),
each phantom synthesized by Kokoro as a standalone 0.975s "MISTER." utterance with
full terminal prosody, and each a permanent miss in the match-rate denominator.

The identity contract: shot list and TTS sidecar both split with THIS pattern, so any
change here renumbers sentences on both sides together — cached sidecars from before
the change are stale and must be re-synthesized.
"""

from __future__ import annotations

import pytest

from manhwa2vid.script.sentences import split_sentences


class TestHonorifics:
    def test_the_observed_defect(self):
        assert split_sentences(
            "Mr. Song, the highest-ranked hunter present, steps up. The group agrees."
        ) == [
            "Mr. Song, the highest-ranked hunter present, steps up.",
            "The group agrees.",
        ]

    def test_mid_sentence_honorific(self):
        """Three of Solo Leveling's eleven broken splits were mid-sentence."""
        assert split_sentences("He crawls over to check on Mr. Song.") == [
            "He crawls over to check on Mr. Song."
        ]

    @pytest.mark.parametrize("title", ["Mr.", "Mrs.", "Ms.", "Dr.", "St.", "Jr.", "Sr."])
    def test_every_listed_abbreviation(self, title):
        text = f"{title} Kim tells Sung Jin-Woo. He nods."
        assert split_sentences(text) == [f"{title} Kim tells Sung Jin-Woo.", "He nods."]


class TestRealSentencesStillSplit:
    def test_short_sentences_are_not_merged(self):
        """Frozen Player's legitimate two-word sentences must survive."""
        assert split_sentences("Jun-Ho frowns. Jun-Ho laughs. Deok-gu hesitates.") == [
            "Jun-Ho frowns.",
            "Jun-Ho laughs.",
            "Deok-gu hesitates.",
        ]

    def test_exclamation_and_question(self):
        assert split_sentences("He yells that it moved! Does it matter? She stares.") == [
            "He yells that it moved!",
            "Does it matter?",
            "She stares.",
        ]

    def test_a_terminal_quote_does_not_end_a_sentence(self):
        """Pre-existing behaviour, pinned deliberately: the lookbehind sees the closing
        quote, not the punctuation inside it, so a quoted exclamation stays attached to
        what follows. Both shipped scripts were numbered under this rule — "fixing" it
        would renumber every sentence after a mid-beat quotation."""
        assert split_sentences('"What?!" She stares.') == ['"What?!" She stares.']

    def test_a_word_merely_ending_in_a_title_is_still_a_boundary(self):
        # "Mr" as a whole word is guarded; a longer word ending in the same letters
        # is an ordinary sentence end.
        assert split_sentences("They cross the river. The water is cold.") == [
            "They cross the river.",
            "The water is cold.",
        ]


class TestLintUsesTheSameSplitter:
    def test_lint_pattern_is_the_shared_object(self):
        """The private copy in lint is an alias now — drift is impossible, not just
        unlikely."""
        from manhwa2vid.script import lint, sentences

        assert lint._SENTENCE_SPLIT_RE is sentences.SENTENCE_SPLIT_RE
