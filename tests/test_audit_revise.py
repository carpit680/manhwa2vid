"""The single revision, and the rule that decides whether it ships.

`revise_once` is the only place downstream of the writer that may change a word, and it
accepts a revision ONLY if the audit's finding count strictly shrinks. That rule is the
project's answer to its most repeated defect class — a later pass undoing an earlier
pass's work — so it is pinned here rather than left to the end-to-end test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from manhwa2vid.script.audit import revise_once


@pytest.fixture
def paths(tmp_path: Path) -> dict[str, Path]:
    from PIL import Image

    pages = tmp_path / "pages"
    pages.mkdir()
    Image.new("RGB", (32, 32)).save(pages / "0001.png")
    return {"root": tmp_path, "pages": pages}


def _audit(majors: int = 0, missing: int = 0) -> dict:
    return {
        "majors": [{"quote": f"q{i}", "problem": "wrong", "page": "0001"} for i in range(majors)],
        "undelivered_system_messages": [f"[MSG {i}]" for i in range(missing)],
    }


def _patch(monkeypatch, *, revision: str, recheck_findings: int):
    """Stub the provider's revision and the re-audit's verdict."""
    import manhwa2vid.script.audit as audit_mod

    class _Provider:
        temperature = None
        vision_model = None

        def describe_labeled_panels_text(self, labeled, system, user, *, max_width=None):
            return revision

    monkeypatch.setattr(audit_mod, "get_llm_provider", lambda *a, **k: _Provider(), raising=False)
    monkeypatch.setattr(
        "manhwa2vid.llm.provider.get_llm_provider", lambda *a, **k: _Provider()
    )
    monkeypatch.setattr(
        audit_mod, "audit_script",
        lambda *a, **k: _audit(majors=recheck_findings),
    )


def test_clean_audit_short_circuits(paths):
    text = "The original narration."
    out, report = revise_once(text, _audit(), paths, {})
    assert out == text
    assert report["revised"] is False and report["reason"] == "clean"


def test_revision_accepted_only_when_findings_shrink(paths, monkeypatch):
    _patch(monkeypatch, revision="A better narration.", recheck_findings=1)
    out, report = revise_once("Original.", _audit(majors=3), paths, {})
    assert out == "A better narration."
    assert report["revised"] is True and report["before"] == 3 and report["after"] == 1


def test_revision_rejected_when_findings_do_not_shrink(paths, monkeypatch):
    """Equal is a rejection, not a tie — a rewrite that fixes one thing and breaks
    another must not ship."""
    _patch(monkeypatch, revision="A differently wrong narration.", recheck_findings=3)
    out, report = revise_once("Original.", _audit(majors=3), paths, {})
    assert out == "Original.", "the original must survive a non-improving revision"
    assert report["revised"] is False and report["reason"] == "no improvement"
    assert report["residual"], "what is still wrong has to reach the human"


def test_revision_rejected_when_findings_grow(paths, monkeypatch):
    _patch(monkeypatch, revision="Much worse.", recheck_findings=9)
    out, report = revise_once("Original.", _audit(majors=2), paths, {})
    assert out == "Original."
    assert report["revised"] is False


def test_empty_revision_keeps_the_original(paths, monkeypatch):
    """A model that returns nothing must not blank the script."""
    _patch(monkeypatch, revision="   ", recheck_findings=0)
    out, report = revise_once("Original.", _audit(majors=2), paths, {})
    assert out == "Original."
    assert report["reason"] == "empty revision"


def test_undelivered_system_messages_alone_trigger_a_revision(paths, monkeypatch):
    """Missing plot-critical system messages count as findings even with zero majors —
    five of them once shipped unnoticed on Frozen Player."""
    _patch(monkeypatch, revision="Now it mentions the system message.", recheck_findings=0)
    out, report = revise_once("Original.", _audit(missing=5), paths, {})
    assert out == "Now it mentions the system message."
    assert report["before"] == 5 and report["after"] == 0
