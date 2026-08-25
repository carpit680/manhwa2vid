"""Orchestrate the story-first script stage: read → write → audit → revise → align.

One function, five steps, no loops. Everything that generates or mutates prose happens
in `write` and the single `revise`; nothing downstream of that may touch a word. That
constraint is the architecture — see `audit.py` for why.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.models import ProjectMeta, ScriptDraft, save_json
from manhwa2vid.qa import QAReport, enforce, qa_forced
from manhwa2vid.script.align import align_script
from manhwa2vid.script.audit import audit_and_revise
from manhwa2vid.script.freeform import paragraphs, write_freeform_script
from manhwa2vid.script.lint import lint_broken_sentences
from manhwa2vid.script.read import glossary_names, read_chapter_facts

console = Console()

#: Sentence-case words that open a sentence are not evidence of a name.
_CAPITALISED_RE = re.compile(r"\b([A-Z][a-z]+(?:[- ][A-Z][a-z]+)*)\b")


def unknown_names(text: str, allowed: set[str]) -> list[str]:
    """Proper-looking names in the narration that the glossary does not know.

    The identity gate. It replaces protagonist election, pronoun inference, alias
    scoring, descriptor consolidation and bible-pollution detection with one question:
    is this name one we actually know? A model that invents "Kang Min-Su" for an unnamed
    bystander gets caught here, and the fix is a one-line glossary edit rather than
    archaeology through a 174-descriptor profile.

    Deliberately loose about sentence-initial words — the check is for MULTI-word or
    clearly-foreign names, because flagging every capitalised sentence opener would
    drown the signal.
    """
    if not allowed:
        return []
    known = {a.lower() for a in allowed}
    # Also accept individual words of a known name: "Jun-Ho" for "Seo Jun-Ho".
    for name in list(allowed):
        for part in re.split(r"[\s-]+", name):
            if len(part) > 2:
                known.add(part.lower())

    found: dict[str, int] = {}
    for sentence in re.split(r"(?<=[.!?])\s+", text or ""):
        # Drop the sentence's FIRST WORD before scanning. Testing "does this candidate
        # start the sentence" does not work: the multi-word pattern is greedy, so
        # "Then Kang Min-Su interrupts" matched as the single candidate
        # "Then Kang Min-Su", which then looked sentence-initial and was skipped —
        # hiding exactly the invented name the gate exists to catch.
        body = sentence.strip().split(" ", 1)
        if len(body) < 2:
            continue
        for match in _CAPITALISED_RE.finditer(body[1]):
            candidate = match.group(1)
            if candidate.lower() in known:
                continue
            # A single common word is far more likely sentence-case than a name.
            if " " not in candidate and "-" not in candidate:
                continue
            found[candidate] = found.get(candidate, 0) + 1
    return sorted(found)


def _beats_markdown(draft: ScriptDraft) -> str:
    from manhwa2vid.script.generate import _beats_to_markdown

    return _beats_to_markdown(draft)


def generate_story_first_script(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> ScriptDraft:
    if paths["script_draft"].exists() and not force:
        from manhwa2vid.script.generate import load_script_beats

        console.print(f"[dim]Using existing script draft[/] → {paths['script_draft']}")
        return load_script_beats(paths)

    if force:
        for key in ("chapter_facts_json", "script_freeform", "script_audit_json",
                    "script_alignment_json"):
            paths[key].unlink(missing_ok=True)

    facts = read_chapter_facts(meta, paths, config, force=force)
    text = write_freeform_script(meta, paths, config, force=force)

    if get_nested(config, "script", "audit_enabled", default=True):
        text, record = audit_and_revise(text, paths, config, facts)
        paths["script_freeform"].write_text(text + "\n", encoding="utf-8")
    else:
        record = {"audit": {"majors": [], "undelivered_system_messages": []},
                  "revision": {"revised": False, "reason": "disabled"}}

    beats, align_report = align_script(text, paths, config)

    draft = ScriptDraft(
        title=meta.title,
        chapters=meta.chapters,
        hook=paragraphs(text)[0][:200] if paragraphs(text) else "",
        beats=beats,
    )
    save_json(paths["script_json"], draft)
    paths["script_draft"].write_text(_beats_markdown(draft), encoding="utf-8")
    console.print(f"[green]Script draft written[/] → {paths['script_draft']}")

    report = QAReport(stage="script-story-first")
    for gate in align_report.gates:
        report.gates.append(gate)

    # Identity: every name in the narration must be one the glossary knows.
    strangers = unknown_names(text, glossary_names(paths))
    report.add(
        "name-integrity",
        False if strangers else True,
        f"narration uses name(s) absent from the glossary: {strangers} — either the "
        "writer invented them or the glossary is missing an alias; fix glossary.json",
        unknown=strangers,
    )

    # Deterministic well-formedness — the absolute checks, no rewriting.
    broken = lint_broken_sentences(beats)
    report.add(
        "beats-wellformed",
        False if broken else True,
        "; ".join(f"beat {b}: {v[0]}" for b, v in sorted(broken.items())[:3]),
        broken=sorted(broken),
    )

    residual = (record.get("revision") or {}).get("residual") or []
    report.add(
        "grounding",
        "warn" if residual else True,
        f"{len(residual)} finding(s) survived the single revision — read them in "
        "script.audit.json before approving",
        residual=len(residual),
    )

    from manhwa2vid.script.scorecard import score_script  # report-only

    try:
        from manhwa2vid.characters.bible import load_series_bible

        bible = load_series_bible(meta.series_slug, meta.title)
        style = score_script(beats, bible, {**config, "_n_chapters": _n_chapters(meta)})
        save_json(paths["root"] / "qa.style.json", style)
    except Exception as exc:  # measurement must never block a run
        console.print(f"[dim]Style scorecard skipped ({exc})[/]")

    enforce(report, paths["root"], force=qa_forced(config))
    return draft


def _n_chapters(meta: ProjectMeta) -> int:
    spec = (meta.chapters or "").strip()
    if "-" in spec:
        first, _, last = spec.partition("-")
        try:
            return max(1, int(last) - int(first) + 1)
        except ValueError:
            return 1
    return 1
