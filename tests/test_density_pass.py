"""The targeted dialogue-density pass and its strictly-improves guards.

Solo Leveling's regenerated script carried 15 paragraphs with zero reporting verbs
(~1160 of 2669 words) — the writer summarizes wherever five chapters compress into one
budget. The pass re-voices ONLY those paragraphs, and a rewrite ships only if density
strictly rises, length stays within ±15%, and the paragraph still lints clean.

The offline mock echoes every paragraph back unchanged, which exercises the reject path
(density does not rise -> original kept). The accept path is tested against fabricated
model output, because a mock that "improves" prose would be asserting the LLM's job.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manhwa2vid.script.density import VERBS_MIN_PER_1K, _accept, apply_density_pass

DRY = (
    "The hunters walk into the dungeon and the raid goes badly from the first minute. "
    "One of the healers is attacked and the party loses its nerve completely. "
    "Everyone looks to the leader for a decision about the sealed doors ahead."
)
WET = (
    "The hunters walk into the dungeon and the raid goes badly from the first minute. "
    "Song admits one of the healers is attacked and says the party lost its nerve. "
    "Everyone asks the leader for a decision about the sealed doors ahead."
)


class TestAcceptGuard:
    def test_a_genuine_improvement_is_accepted(self):
        ok, _ = _accept(DRY, WET)
        assert ok

    def test_unchanged_density_is_rejected(self):
        ok, reason = _accept(DRY, DRY)
        assert not ok and "density" in reason

    def test_a_length_blowout_is_rejected_even_with_more_verbs(self):
        """Word count IS runtime — an audio-locked pipeline cannot accept a rewrite
        that mints 30% more narration."""
        bloated = WET + " " + " ".join(["He says more and more and keeps talking."] * 3)
        ok, reason = _accept(DRY, bloated)
        assert not ok and "length" in reason

    def test_a_broken_sentence_is_rejected(self):
        broken = WET + " They grit his teeth."
        ok, reason = _accept(DRY, broken)
        assert not ok and "lint" in reason

    def test_empty_candidate_is_rejected(self):
        assert _accept(DRY, "")[0] is False


@pytest.fixture
def paths(tmp_path: Path) -> dict[str, Path]:
    facts = tmp_path / "chapter_facts.json"
    facts.write_text(json.dumps({"key_dialogue": [
        {"page": "0001", "speaker": "Song", "line": "we lost a healer in there"},
    ]}))
    return {"root": tmp_path, "debug": tmp_path / "debug", "chapter_facts_json": facts}


class TestApplyDensityPass:
    def test_offline_mock_leaves_the_text_byte_identical(self, paths):
        """The mock echoes paragraphs unchanged; every candidate must be rejected by
        the density guard, and the caller gets the original text back."""
        text = f"{DRY}\n\n{WET}"
        out, record = apply_density_pass(text, paths, {})
        assert out == text
        assert record["accepted"] == []
        assert record["targets"] == [0], "only the dry paragraph is a target"
        assert "density" in record["rejected"][0]

    def test_a_passing_paragraph_is_never_sent(self, paths):
        out, record = apply_density_pass(WET, paths, {})
        assert out == WET and record["targets"] == []

    def test_a_short_visual_paragraph_is_never_sent(self, paths):
        short = "He steps into the light. The blade hums."
        out, record = apply_density_pass(short, paths, {})
        assert out == short and record["targets"] == []

    def test_accepted_rewrites_are_spliced_by_index(self, paths, monkeypatch):
        """Fabricated model output: paragraph 0 genuinely improved, paragraph left
        alone elsewhere. The improved one ships, everything else is untouched."""
        from manhwa2vid.llm import provider as provider_mod

        class _Fake:
            def complete(self, system, user):
                return json.dumps({"paragraphs": {"0": WET}})

        monkeypatch.setattr(provider_mod, "get_llm_provider", lambda *a, **k: _Fake())
        tail = "A second paragraph that stays. He says it plainly and she agrees."
        out, record = apply_density_pass(f"{DRY}\n\n{tail}", paths, {})
        assert out == f"{WET}\n\n{tail}"
        assert record["accepted"] == [0]

    def test_the_record_is_persisted_for_diagnosis(self, paths):
        apply_density_pass(DRY, paths, {})
        assert (paths["debug"] / "density_pass.json").exists()

    def test_provider_failure_returns_the_text_untouched(self, paths, monkeypatch):
        from manhwa2vid.llm import provider as provider_mod

        def _boom(*a, **k):
            raise RuntimeError("no key")

        monkeypatch.setattr(provider_mod, "get_llm_provider", _boom)
        out, record = apply_density_pass(DRY, paths, {})
        assert out == DRY and "error" in record


def test_the_gate_floor_is_the_pass_floor():
    """story_first's gate imports the constant from density.py — one number, one
    owner, no drift."""
    from manhwa2vid.script import story_first

    assert story_first._VERBS_MIN_PER_1K is VERBS_MIN_PER_1K


def test_the_outro_is_never_a_rewrite_target(paths):
    """On a cached run script.freeform.md already carries its outro; 40+ words, zero
    reporting verbs — a target by every other rule. The narrator's ask to the viewer
    must not be re-voiced as reported speech."""
    outro = (
        "Whether this desperate gamble will decode the temple's deadly rules remains "
        "to be seen, and subscribing with notifications turned on ensures you are "
        "there the moment the dust settles and the next part of his struggle lands."
    )
    out, record = apply_density_pass(f"{DRY}\n\n{outro}", paths, {})
    assert record["targets"] == [0]
    assert out.endswith(outro)
