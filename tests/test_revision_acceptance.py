"""revise_once's acceptance: deterministic checks instead of the finding count.

The count comparison failed in both directions in ONE day. It rejected a correct
Mr. Kim -> Mr. Song fix because the re-audit's own noise went 1 -> 2; it accepted a
text that went 8 -> 7 while replacing the correct name "Mr. Song" with "the hunter
with orange hair" in four places and adding clothing descriptions — seven "wrong
name" findings become zero if nobody is named. The count measures the auditor's noise
floor, not the revision's quality.

Both historical cases are pinned below, shapes taken from the real texts.
"""

from __future__ import annotations

from manhwa2vid.script.audit import acceptance_failures

GLOSSARY = {"Sung Jin-Woo", "Jin-Woo", "Mr. Song", "Song Chi-Yul", "Mr. Kim",
            "Kim Sang-Shik", "Ju-Hee"}


class TestTheShippedRegressionIsRejected:
    def test_name_to_descriptor_swaps_are_rejected(self):
        """The 8->7 revision's shape: correct names replaced by descriptions."""
        original = (
            "Mr. Song strokes his chin. Mr. Song counts the raised hands. "
            "Mr. Song looks at the cavern walls. Jin-Woo watches Mr. Song."
        )
        revised = (
            "The hunter with orange hair strokes his chin. The hunter with orange "
            "hair counts the raised hands. The hunter with orange hair looks at the "
            "cavern walls. Jin-Woo watches the man."
        )
        failures = acceptance_failures(
            original, revised,
            [{"quote": "Mr. Song strokes his chin."}], GLOSSARY,
        )
        assert any("glossary names dropped" in f for f in failures)

    def test_an_ignored_finding_is_rejected(self):
        original = "Mr. Kim holds up a glowing magical core. Ju-Hee watches."
        revised = "Mr. Kim holds up a glowing magical core. Ju-Hee watches closely."
        failures = acceptance_failures(
            original, revised,
            [{"quote": "Mr. Kim holds up a glowing magical core."}], GLOSSARY,
        )
        assert any("quote unchanged" in f for f in failures)

    def test_a_length_blowup_is_rejected(self):
        original = "Jin-Woo waits. " * 20
        revised = "Jin-Woo waits and waits and waits some more. " * 20
        failures = acceptance_failures(original, revised, [], GLOSSARY)
        assert any("length moved" in f for f in failures)


class TestTheCorrectFixIsAccepted:
    def test_a_wrong_name_swap_passes(self):
        """The Mr. Kim -> Mr. Song fix the old rule rejected (its re-audit noise went
        1 -> 2). Total glossary-name occurrences are preserved by a swap."""
        original = ("Mr. Kim holds up a glowing magical core from a dead beast. "
                    "Jin-Woo looks at his own palm. Ju-Hee smiles.")
        revised = ("Mr. Song holds up a glowing magical core from a dead beast. "
                    "Jin-Woo looks at his own palm. Ju-Hee smiles.")
        assert acceptance_failures(
            original, revised,
            [{"quote": "Mr. Kim holds up a glowing magical core from a dead beast."}],
            GLOSSARY,
        ) == []

    def test_a_fact_correction_with_names_intact_passes(self):
        original = ("Sung Jin-Woo lies on the floor. He is missing his right arm "
                    "below the elbow. Ju-Hee is not here.")
        revised = ("Sung Jin-Woo lies on the floor. His trouser leg is torn and "
                    "bloodied. Ju-Hee is not here.")
        assert acceptance_failures(
            original, revised,
            [{"quote": "He is missing his right arm below the elbow."}], GLOSSARY,
        ) == []

    def test_no_glossary_is_not_a_veto(self):
        assert acceptance_failures("Alpha beta.", "Alpha gamma.", [], set()) == []
