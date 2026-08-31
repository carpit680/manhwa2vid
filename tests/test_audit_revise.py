"""The single revision, and the acceptance that decides whether it ships.

`revise_once` is the only place downstream of the writer that may change a word. Its
acceptance used to be "the audit's finding count strictly shrinks", and that rule
failed in BOTH directions in one day: it rejected a correct Mr. Kim -> Mr. Song fix
because the re-audit's own noise went 1 -> 2, and it accepted a text that went 8 -> 7
while replacing the correct name "Mr. Song" with "the hunter with orange hair" in four
places — seven "wrong name" findings become zero if nobody is named. The count
measures the auditor's noise floor, not the revision's quality.

Acceptance is now `acceptance_failures` (tests/test_revision_acceptance.py pins its
rules; this file pins revise_once's use of it): targeted quotes must change, total
glossary-name occurrences must not drop, no new placeholder descriptors, length within
±15%. No re-audit call at all — which also halves the audit's vision spend.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manhwa2vid.script.audit import revise_once


@pytest.fixture
def paths(tmp_path: Path) -> dict[str, Path]:
    from PIL import Image

    pages = tmp_path / "pages"
    pages.mkdir()
    Image.new("RGB", (32, 32)).save(pages / "0001.png")
    glossary = tmp_path / "glossary.json"
    glossary.write_text(json.dumps({
        "characters": {"Mr. Kim": [], "Mr. Song": [], "Jin-Woo": []},
        "terms": {},
    }), encoding="utf-8")
    return {"root": tmp_path, "pages": pages, "glossary": glossary}


def _audit(majors: list[dict] | int = 0, missing: int = 0) -> dict:
    if isinstance(majors, int):
        majors = [{"quote": f"q{i}", "problem": "wrong", "page": "0001"}
                  for i in range(majors)]
    return {
        "majors": majors,
        "undelivered_system_messages": [f"[MSG {i}]" for i in range(missing)],
    }


def _patch(monkeypatch, *, revision: str):
    class _Provider:
        temperature = None
        vision_model = None

        def describe_labeled_panels_text(self, labeled, system, user, *, max_width=None):
            return revision

    monkeypatch.setattr(
        "manhwa2vid.llm.provider.get_llm_provider", lambda *a, **k: _Provider()
    )


def test_clean_audit_short_circuits(paths):
    text = "The original narration."
    out, report = revise_once(text, _audit(), paths, {})
    assert out == text
    assert report["revised"] is False and report["reason"] == "clean"


def test_a_correct_wrong_name_fix_is_accepted(paths, monkeypatch):
    """The fix the old count rule rejected: quote changed, name total preserved."""
    original = "Mr. Kim holds up a glowing magical core. Jin-Woo watches."
    _patch(monkeypatch, revision="Mr. Song holds up a glowing magical core. Jin-Woo watches.")
    out, report = revise_once(
        original,
        _audit(majors=[{"quote": "Mr. Kim holds up a glowing magical core.",
                        "problem": "it is Mr. Song", "page": "0001"}]),
        paths, {},
    )
    assert report["revised"] is True
    assert "Mr. Song" in out


def test_a_name_to_descriptor_revision_is_rejected(paths, monkeypatch):
    """The regression the old count rule shipped."""
    original = ("Mr. Song strokes his chin. Mr. Song counts the hands. "
                "Jin-Woo watches Mr. Song.")
    _patch(monkeypatch, revision=(
        "The hunter with orange hair strokes his chin. The hunter with orange hair "
        "counts the hands. Jin-Woo watches the man."))
    out, report = revise_once(
        original,
        _audit(majors=[{"quote": "Mr. Song strokes his chin.",
                        "problem": "x", "page": "0001"}]),
        paths, {},
    )
    assert out == original, "the original must survive a name-stripping revision"
    assert report["revised"] is False and report["reason"] == "acceptance failed"
    assert any("glossary names dropped" in f for f in report["failures"])
    assert report["residual"], "what is still wrong has to reach the human"


def test_an_ignored_finding_is_rejected(paths, monkeypatch):
    original = "Mr. Kim holds the core. Jin-Woo watches."
    _patch(monkeypatch, revision="Mr. Kim holds the core. Jin-Woo watches closely.")
    out, report = revise_once(
        original,
        _audit(majors=[{"quote": "Mr. Kim holds the core.", "problem": "x", "page": "0001"}]),
        paths, {},
    )
    assert out == original
    assert any("quote unchanged" in f for f in report["failures"])


def test_empty_revision_keeps_the_original(paths, monkeypatch):
    """A model that returns nothing must not blank the script."""
    _patch(monkeypatch, revision="   ")
    out, report = revise_once("Original.", _audit(majors=2), paths, {})
    assert out == "Original."
    assert report["reason"] == "empty revision"


def test_undelivered_system_messages_alone_trigger_a_revision(paths, monkeypatch):
    """Missing plot-critical system messages count as findings even with zero majors —
    five of them once shipped unnoticed on Frozen Player."""
    _patch(monkeypatch, revision="Now Jin-Woo hears the system message.")
    out, report = revise_once("Jin-Woo waits.", _audit(missing=5), paths, {})
    assert out == "Now Jin-Woo hears the system message."
    assert report["revised"] is True and report["before"] == 5


# --- per-finding verification (2026-08-31) --------------------------------------------

def _verify_paths(tmp_path: Path) -> dict[str, Path]:
    from PIL import Image

    pages = tmp_path / "pages"
    pages.mkdir(exist_ok=True)
    for n in (1, 2, 3):
        Image.new("RGB", (32, 32)).save(pages / f"{n:04d}.png")
    return {"root": tmp_path, "pages": pages}


class _VerifyProvider:
    """Scripted verdicts, plus a record of which pages each call saw."""

    temperature = None
    vision_model = None

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def describe_labeled_panels(self, labeled, prompt, *, max_width=None):
        self.calls.append([label for label, _p in labeled])
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return json.dumps(r)


def test_a_refuted_finding_leaves_majors_but_is_kept_for_the_human(tmp_path):
    """The measured failure: 5 of 8 hand-checked majors were false — a vendor
    inversion, an arm read as a torso. A refuted finding must never reach
    revise_once, and must never silently vanish either."""
    from manhwa2vid.script.audit import verify_majors

    finding = {"quote": "he sells coffee", "problem": "he BUYS coffee", "page": "0002"}
    provider = _VerifyProvider([
        {"verdict": "refuted", "evidence": '"One iced americano, coming up!"'},
    ])
    confirmed, unverified = verify_majors([finding], _verify_paths(tmp_path), {}, provider)
    assert confirmed == []
    assert len(unverified) == 1
    assert unverified[0]["verification"]["verdict"] == "refuted"


def test_a_confirmed_finding_stays_and_carries_the_clean_restatement(tmp_path):
    """Confirmation replaces the stage-1 problem text — one finding shipped with
    leaked chain-of-thought ("...but wait, let me check"), and the re-statement is
    where that dies before reaching the reviser."""
    from manhwa2vid.script.audit import verify_majors

    finding = {"quote": "q", "problem": "wrong, but wait, let me check", "page": "2"}
    provider = _VerifyProvider([
        {"verdict": "confirmed", "evidence": '"RANK: E"',
         "finding": "The narration says D-rank; the card prints E."},
    ])
    confirmed, unverified = verify_majors([finding], _verify_paths(tmp_path), {}, provider)
    assert unverified == []
    assert confirmed[0]["problem"] == "The narration says D-rank; the card prints E."
    assert confirmed[0]["verification"]["evidence"] == '"RANK: E"'


def test_verification_sees_only_the_cited_page_and_neighbours(tmp_path):
    """The whole point: the stage-1 failure is attention across 150 images, so the
    verifier must hold the cited page's small neighbourhood (±2) and nothing else."""
    from manhwa2vid.script.audit import verify_majors

    provider = _VerifyProvider([{"verdict": "refuted", "evidence": "x"}])
    verify_majors(
        [{"quote": "q", "problem": "p", "page": "0002"}],
        _verify_paths(tmp_path), {}, provider,
    )
    assert provider.calls == [["[page 0001]", "[page 0002]", "[page 0003]"]]


def test_a_provider_error_parks_the_finding_never_accepts_it(tmp_path):
    from manhwa2vid.script.audit import verify_majors

    provider = _VerifyProvider([RuntimeError("429")])
    confirmed, unverified = verify_majors(
        [{"quote": "q", "problem": "p", "page": "0001"}],
        _verify_paths(tmp_path), {}, provider,
    )
    assert confirmed == []
    assert "error" in str(unverified[0]["verification"])


def test_a_finding_without_a_locatable_page_is_parked(tmp_path):
    """An unverifiable accusation against narration that survived the writer, the
    facts pass and the density pass is worth a human eye, never an automatic edit."""
    from manhwa2vid.script.audit import verify_majors

    provider = _VerifyProvider([])
    confirmed, unverified = verify_majors(
        [{"quote": "q", "problem": "p", "page": "somewhere"}],
        _verify_paths(tmp_path), {}, provider,
    )
    assert confirmed == [] and provider.calls == []
    assert unverified[0]["verification"] == "no locatable page"
