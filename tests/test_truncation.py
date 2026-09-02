"""Truncated model answers must fail loudly, not salvage into a plausible artifact.

`_extract_json_object` is deliberately salvaging: given a body cut off mid-object it
brace-balances a fragment that parses cleanly. That is right for a 16-panel window and
catastrophic for a stage whose whole output is one object — a truncated read pass hands
back an empty spine, a truncated audit hands back zero findings, and every downstream
gate then reports a clean run.

The provider has recorded `last_finish_reason` since a 28-beat narration was cut at the
4096-token cap and "silently yielded zero beats for three straight runs". Nothing read
it until 2026-09-01. These tests exist so nothing stops reading it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manhwa2vid.llm.provider import TruncatedResponse


class _Truncating:
    """A provider whose answer is a plausible, parseable FRAGMENT of the real thing."""

    temperature = None
    vision_model = "stub-vision"
    model = "stub-text"
    last_finish_reason = "length"
    last_completion_tokens = 4096

    def __init__(self, body: str):
        self.body = body
        self.budget = None

    def set_json_budget(self, tokens):
        self.budget = tokens

    def raise_if_truncated(self, what: str) -> None:
        from manhwa2vid.llm.provider import LLMProvider

        LLMProvider.raise_if_truncated(self, what)

    def describe_labeled_panels(self, labeled, prompt, *, max_width=None):
        return self.body

    def describe_panels(self, paths, prompt, *, max_width=None):
        return self.body

    def complete(self, system, user, *, json_mode=False):
        return self.body


def _pages(tmp_path: Path) -> Path:
    from PIL import Image

    pages = tmp_path / "pages"
    pages.mkdir(exist_ok=True)
    Image.new("RGB", (32, 32)).save(pages / "0001.png")
    return pages


def test_the_checker_fires_only_on_a_length_stop():
    from manhwa2vid.llm.provider import MockLLMProvider

    p = MockLLMProvider()
    p.last_finish_reason = "length"
    p.last_completion_tokens = 4096
    with pytest.raises(TruncatedResponse) as exc:
        p.raise_if_truncated("read pass")
    assert "output cap" in str(exc.value) and "4096" in str(exc.value)

    for reason in ("stop", "", "content_filter"):
        p.last_finish_reason = reason
        p.raise_if_truncated("read pass")  # must not raise


def test_every_provider_has_the_checker():
    """Callers hold a base-class provider and never know which subclass they got."""
    from manhwa2vid.llm.provider import (
        GeminiProvider, GroqProvider, LLMProvider, MistralProvider, MockLLMProvider,
    )

    for cls in (LLMProvider, MockLLMProvider, GeminiProvider, GroqProvider, MistralProvider):
        assert hasattr(cls, "raise_if_truncated"), cls
        assert hasattr(cls, "set_json_budget"), cls


def test_a_truncated_read_pass_raises_instead_of_returning_an_empty_spine(tmp_path, monkeypatch):
    """The salvaged fragment parses and looks like a chapter with no system messages —
    which is exactly what a real chapter with no system messages looks like."""
    from manhwa2vid.script import read as R

    fragment = json.dumps({"cast": [{"name": "A"}], "plot_spine": ["one thing"]})
    provider = _Truncating(fragment)
    monkeypatch.setattr("manhwa2vid.llm.provider.get_llm_provider", lambda *a, **k: provider)
    from manhwa2vid.models import ProjectMeta, SourceLanguage, SourceType, project_paths

    _pages(tmp_path)
    paths = project_paths(tmp_path)
    paths["glossary"].write_text(json.dumps({"characters": {}, "terms": {}}))
    meta = ProjectMeta(slug="t", title="T", chapters="1-2",
                       source_lang=SourceLanguage.EN, source_type=SourceType.IMAGES,
                       source_path=str(tmp_path))
    with pytest.raises(TruncatedResponse):
        R.read_chapter_facts(meta, paths, {}, force=True)


def test_a_truncated_audit_raises_instead_of_reporting_a_clean_script(tmp_path, monkeypatch):
    """Zero findings from a truncated call is indistinguishable from a clean script,
    and produces a green grounding gate over narration nobody checked."""
    from manhwa2vid.script import audit as A

    provider = _Truncating(json.dumps({"findings": []}))
    monkeypatch.setattr("manhwa2vid.llm.provider.get_llm_provider", lambda *a, **k: provider)
    paths = {"pages": _pages(tmp_path), "root": tmp_path}
    with pytest.raises(TruncatedResponse):
        A.audit_script("Some narration.", paths, {})


def test_a_truncated_alignment_map_raises(tmp_path, monkeypatch):
    from manhwa2vid.script import align as AL

    provider = _Truncating(json.dumps({"map": [{"paragraph": 1, "first_page": 1,
                                                "last_page": 2}]}))
    monkeypatch.setattr("manhwa2vid.llm.provider.get_llm_provider", lambda *a, **k: provider)
    with pytest.raises(TruncatedResponse):
        AL.request_alignment(["para one", "para two", "para three"],
                             [_pages(tmp_path) / "0001.png"], {})


def test_the_whole_page_stages_ask_for_a_bigger_output_budget(tmp_path, monkeypatch):
    """4096 was sized for a 16-panel window; these three answer about every page at
    once. Raising the cap does not remove the cliff — the checker does — it moves it
    past the real product size."""
    from manhwa2vid.script import align as AL

    provider = _Truncating(json.dumps({"map": []}))
    provider.last_finish_reason = "stop"
    monkeypatch.setattr("manhwa2vid.llm.provider.get_llm_provider", lambda *a, **k: provider)
    AL.request_alignment(["para one"], [_pages(tmp_path) / "0001.png"], {})
    assert provider.budget and provider.budget > 4096


def test_the_matcher_counts_truncated_windows_instead_of_aborting(tmp_path, monkeypatch, capsys):
    """One call per 16-panel window: a truncated window is a partial loss, and
    abandoning a hundred good calls over it would be worse. It must still be visible —
    the only symptom otherwise is a slightly lower match rate."""
    from manhwa2vid.models import Panel, PanelBBox
    from manhwa2vid.script import match as M

    provider = _Truncating(json.dumps({"claims": [{"sentence": 1, "panels": ["p1"]}]}))
    monkeypatch.setattr("manhwa2vid.llm.provider.get_llm_provider", lambda *a, **k: provider)
    # The matcher caches ONE provider per process for usage accounting; a stub must
    # replace it, not sit behind it.
    monkeypatch.setattr(M, "_MATCHER_PROVIDER", None)
    panels = [Panel(id="p1", page_num=1, bbox=PanelBBox(x=0, y=0, width=9, height=9),
                    image_path="panels/p1.png", ink_ratio=0.5, dark_ratio=0.5)]
    claims = M.collect_claims([(1, "A sentence.")], panels,
                              {"root": tmp_path, "pages": _pages(tmp_path)}, {})
    assert claims == [(1, "p1")], "a truncated window must still yield what it parsed"
    assert "hit the output cap" in capsys.readouterr().out
