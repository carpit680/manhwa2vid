"""Narrator-to-viewer address, and the metric mistake that nearly shipped as a gap.

A raw count of "you" put Mamoru's 5.2M video at 17.74 per 1000 words against our 3.88,
which read as a large deficit and was nearly implemented as one. Looking at the actual
frames killed it: that video's second person is overwhelmingly characters talking to
each other — "why are you...", "you want to...", "you doing here..." — because it
carries more direct dialogue, not because the narrator turns outward more.

On address proper the same video runs 1.01/1k, the field median is ~0.16, and our FP
script runs 0.75 — second in the corpus. The real finding was an inconsistency between
our OWN scripts: SL measured 0.00.

Frame-matching rather than quote-stripping, because competitor auto-captions carry no
quotation marks at all — their dialogue and their address cannot be told apart by
punctuation, so the metric has to work without it.
"""

from __future__ import annotations

from manhwa2vid.measure.script_text import narrator_address_rate


class TestAddressIsNotDialogue:
    def test_character_dialogue_does_not_count(self):
        """The exact frames that inflated the raw count on the 5.2M video."""
        dialogue = (
            "He asks why are you here. She says what do you want. "
            "He tells her you need to leave and you are going to regret this."
        )
        assert narrator_address_rate(dialogue)["address_frames"] == 0

    def test_narrator_turning_outward_counts(self):
        assert narrator_address_rate("If you are keeping count, that is three.")["address_frames"] == 1
        assert narrator_address_rate("You already know how that ends.")["address_frames"] == 1
        assert narrator_address_rate("Imagine being the guy who signed that off.")["address_frames"] == 1

    def test_rate_is_per_thousand_words(self):
        text = "If you are keeping count. " + "filler word here again now. " * 40
        r = narrator_address_rate(text)
        assert r["address_frames"] == 1
        assert r["per_1k"] == round(1000 / r["words"], 2)

    def test_empty_text_is_safe(self):
        assert narrator_address_rate("")["per_1k"] == 0.0


class TestShippedScripts:
    """The measured state that motivated the gate, pinned so a regression is visible."""

    def _text(self, path):
        from pathlib import Path

        from manhwa2vid.script.beats import _parse_markdown_beats

        p = Path(path)
        if not p.exists():
            import pytest

            pytest.skip(f"{path} not present")
        return "\n\n".join(b.narration for b in _parse_markdown_beats(p))

    def test_fp_already_sits_near_the_top_of_the_field(self):
        r = narrator_address_rate(
            self._text("projects/return-of-the-frozen-player-ch1-2/script.final.md")
        )
        assert r["per_1k"] > 0.3, "FP measured 0.75 — near the field's highest (1.01)"


def test_gate_band_brackets_the_field_not_the_raw_you_count():
    """0.3-2.0 brackets the corpus (median 0.16, top 1.01) with room either side. A band
    derived from the raw "you" count would have demanded ~17/1k — a number no narrator
    in the field actually produces."""
    from manhwa2vid.script.story_first import _ADDRESS_MAX_PER_1K, _ADDRESS_MIN_PER_1K

    assert _ADDRESS_MIN_PER_1K < 0.75 < _ADDRESS_MAX_PER_1K, "our FP script must pass"
    assert _ADDRESS_MAX_PER_1K >= 1.01, "the field's highest video must pass"
    assert _ADDRESS_MAX_PER_1K < 5.0, "a tic ceiling, not a raw-you target"
