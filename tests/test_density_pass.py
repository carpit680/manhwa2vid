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


def test_fenced_json_with_trailing_text_still_parses(paths, monkeypatch):
    """The first live run: Gemini returned ```json {...}``` and json.loads raised
    "Extra data" on the closing fence — the pass silently no-opped on both titles."""
    from manhwa2vid.llm import provider as provider_mod

    class _Fenced:
        def complete(self, system, user):
            return "```json\n" + json.dumps({"paragraphs": {"0": WET}}) + "\n```\nDone!"

    monkeypatch.setattr(provider_mod, "get_llm_provider", lambda *a, **k: _Fenced())
    out, record = apply_density_pass(DRY, paths, {})
    assert record["accepted"] == [0]
    assert out == WET


class TestGuardsFromReadingTheFirstLiveOutput:
    """Both caught by eye on the first real run, not by any metric."""

    def test_a_candidate_mentioning_the_narrator_is_rejected(self):
        """SL beat 6 came back as "The narrator explains that a magical core…" — the
        pass describing itself, read aloud to the viewer."""
        meta = WET.replace(
            "Song admits one of the healers is attacked",
            "The narrator explains one of the healers is attacked",
        )
        ok, reason = _accept(DRY, meta)
        assert not ok and "narrat" in reason

    def test_a_rewrite_that_loses_a_verbatim_quote_is_rejected(self):
        """SL beat 9: 'shouts, "I'm going!"' became 'tells the group that he is going'
        — density up, quotes down. Quotes are rarer and worth more."""
        original = DRY + ' He shouts, "I am going!"'
        candidate = WET + " He tells the group that he is going."
        ok, reason = _accept(original, candidate)
        assert not ok and "quotes" in reason

    def test_provider_failure_still_writes_the_record(self, paths, monkeypatch):
        """The first live failure left no debug file: the error return path skipped
        the persist. Diagnosing it meant rerunning the pass."""
        from manhwa2vid.llm import provider as provider_mod

        def _boom(*a, **k):
            raise RuntimeError("no key")

        monkeypatch.setattr(provider_mod, "get_llm_provider", _boom)
        apply_density_pass(DRY, paths, {})
        assert (paths["debug"] / "density_pass.json").exists()


def test_the_pass_never_runs_twice(tmp_path, monkeypatch):
    """Measured on Solo Leveling: the second application turned "He explains that it
    is a Double Lair. They actually found a secondary dungeon hidden inside the first."
    into "...the double lair looks like it is actually real" — denser, same length,
    lints clean, and tells the viewer less. The acceptance checks density, words and
    lint, not meaning, so repeat applications ratchet meaning away."""
    import json as _json

    from manhwa2vid.script.density import apply_density_pass

    debug = tmp_path / "debug"
    debug.mkdir()
    (debug / "density_pass.json").write_text(_json.dumps({"targets": []}))
    called = {"n": 0}
    monkeypatch.setattr(
        "manhwa2vid.llm.provider.get_llm_provider",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1),
    )
    text = "A dry paragraph with plenty of words to qualify as a target. " * 5
    out, record = apply_density_pass(text, {"debug": debug}, {})
    assert out == text
    assert record.get("skipped") == "already applied"
    assert called["n"] == 0, "the provider must not even be constructed"


def test_a_writer_narrator_paragraph_is_never_targeted():
    """An explainer or a translation note is verb-poor BY DESIGN — nobody is speaking in
    it. Rewriting it into reported speech would delete exactly what the persona adds,
    which is this project's most repeated defect class."""
    from manhwa2vid.script.density import apply_density_pass

    called = []
    import manhwa2vid.script.density as D

    orig = D._rewrite_paragraphs if hasattr(D, "_rewrite_paragraphs") else None
    para = ("I should explain the ranking system before this gets confusing. "
            "Hunters are graded from E up to S, and the grade decides which gates you "
            "are allowed to walk into and how much the guild pays you for it. "
            "Nobody in this world questions the scale; they just live inside it. "
            "The whole economy of the story rests on that one letter.")
    out, rec = apply_density_pass(para, {}, {})
    assert out == para
    assert rec.get("targets") == [], "a persona paragraph was sent for re-voicing"


def test_a_rewrite_that_drops_the_narrator_is_rejected():
    """Belt and braces with the targeting rule: even a qualifying paragraph may carry
    the writer's voice, and a candidate that launders it out trades persona for metric."""
    from manhwa2vid.script.density import _accept

    original = ("I should explain this: fiends are players who use their powers to "
                "commit crimes, and nobody can contain them now.")
    laundered = ("He explains that fiends are players who use their powers to commit "
                 "crimes, and he says nobody can contain them now.")
    ok, reason = _accept(original, laundered)
    assert not ok
    assert "voice" in reason or "first person" in reason
