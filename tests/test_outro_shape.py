"""The closing ask is the last thing the viewer hears in EVERY video.

Both titles shipped the same construction, which is how it earned a code check rather
than another prompt rule (CLAUDE.md: a rule the model declined twice lives in code):

    FP: "Determining whether Jun-Ho can rapidly increase his magic stats ... is now the
         only question that matters. Subscribing and turning on notifications ensures
         you will be right there ..."
    SL: "... and subscribing with notifications turned on ensures you are there the
         moment the dust settles."

Both are grammatical, both are two sentences, both are under the word cap, and both
passed the old shape check — which tested for the SUBSTRING "subscri", a test that
"subscribing" satisfies. The cause was upstream: the prompt handed the model the ask as
a gerund phrase ("folds in the ask — subscribing and turning on notifications —") and it
used that phrase as written, as a sentence subject.
"""

from __future__ import annotations

import re

import pytest

from manhwa2vid.models import ProjectMeta
from manhwa2vid.script.outro import _NOMINALISED_RE, _fallback

FP_SHIPPED = (
    "Determining whether Jun-Ho can rapidly increase his magic stats to finally awaken "
    "his long-lost comrades is now the only question that matters. Subscribing and "
    "turning on notifications ensures you will be right there the moment he attempts to "
    "break their eternal frost."
)
SL_SHIPPED = (
    "Whether this desperate gamble will decode the temple's deadly rules remains to be "
    "seen, and subscribing with notifications turned on ensures you are there the moment "
    "the dust settles. To see if Jin-Woo survives his face-off against the god's lethal "
    "gaze, make sure you follow along and never miss the next part of his struggle."
)


def _has_imperative_ask(text: str) -> bool:
    """The check the shape gate now applies — the imperative, not the topic."""
    return bool(re.search(r"\bsubscribe\b", text, re.I))


class TestTheShippedOutrosAreRejected:
    def test_a_gerund_subject_hook_is_caught(self):
        assert _NOMINALISED_RE.search(FP_SHIPPED)

    @pytest.mark.parametrize("text", [FP_SHIPPED, SL_SHIPPED])
    def test_neither_states_the_ask_as_an_imperative(self, text):
        assert not _has_imperative_ask(text), "'subscribing' is not the ask, it is a topic"

    def test_the_old_substring_check_accepted_both(self):
        """Pins WHY this went unnoticed, so the weaker test is not reintroduced."""
        for text in (FP_SHIPPED, SL_SHIPPED):
            assert "subscri" in text.lower()


class TestGoodOutrosSurvive:
    def test_the_fallback_passes_its_own_gate(self):
        """The deterministic closing must satisfy the checks it is the fallback for —
        otherwise a rejected outro is replaced by another rejected outro."""
        text = _fallback(ProjectMeta(slug="fp-ch1-2", title="Return of the Frozen Player",
                                    chapters="1-2", source_lang="en"))
        assert _has_imperative_ask(text)
        assert not _NOMINALISED_RE.search(text)

    @pytest.mark.parametrize("text", [
        "Whether he survives the third floor is the only question left. Subscribe and "
        "turn notifications on so the answer reaches you first.",
        "What he does with a nucleus nobody else can find is the part worth waiting for. "
        "Subscribe and switch notifications on for the next one.",
    ])
    def test_a_well_formed_closing_is_not_rejected(self, text):
        assert _has_imperative_ask(text)
        assert not _NOMINALISED_RE.search(text)

    def test_an_ing_word_that_is_not_a_gerund_subject_is_fine(self):
        """The rule targets '-ing + whether/if/how' as a SUBJECT, not every -ing word."""
        text = ("Nothing about the seal makes sense yet, and finding out is the point. "
                "Subscribe and turn notifications on.")
        assert not _NOMINALISED_RE.search(text)
