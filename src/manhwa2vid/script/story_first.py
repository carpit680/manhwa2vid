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
from manhwa2vid.script.outro import append_outro
from manhwa2vid.script.lint import lint_broken_sentences
from manhwa2vid.script.read import glossary_names, read_chapter_facts
from manhwa2vid.script.sentences import split_sentences

console = Console()

# Prose bands. Reference values measured 2026-08-28 from the Mamoru SRT with the counters
# in measure/script_text.py — see reports/render_audit_2026-08-28.md §3. Floors are a
# fraction of the reference, not the reference itself: this is a floor, not a target.
_REF_VERBS_PER_1K = 31.34
_REF_QUOTED_PER_1K = 1.62
_REF_SHORT_PCT = 21.5
_REF_MEAN_WORDS = 12.76
_VERBS_MIN_PER_1K = 18.0   # brief's number, now justified against a like-for-like 31.34
_QUOTED_MIN_PER_1K = 0.5   # brief's number; reference 1.62
# The brief proposed 25%. The reference is 21.5%, so 25% would fail the channel being
# imitated -- and Solo Leveling at 23.7% would fail while being MORE reference-like than
# the reference. 18% sits below the reference with margin.
_SHORT_MIN_PCT = 18.0

#: Sentence-case words that open a sentence are not evidence of a name.
_CAPITALISED_RE = re.compile(r"\b([A-Z][a-z]+(?:[- ][A-Z][a-z]+)*)\b")
#: "E-Rank Hunter", "S-Class Gate" — a single-letter grade prefix does not match
#: [A-Z][a-z]+, so the scan starts at "Rank" and reports a name nobody wrote. The whole
#: grade token goes: stripping only the "E-" leaves "Rank Hunter", which still matches.
_GRADE_PREFIX_RE = re.compile(r"\b[A-Z]-[A-Z][a-z]+")


def unknown_names(text: str, allowed: set[str]) -> list[str]:
    """Proper-looking names in the narration that the glossary does not know.

    The identity gate. It replaces protagonist election, pronoun inference, alias
    scoring, descriptor consolidation and bible-pollution detection with one question:
    is this name one we actually know? A model that invents "Kang Min-Su" for an unnamed
    bystander gets caught here, and the fix is a one-line glossary edit rather than
    archaeology through a 174-descriptor profile.

    ADVISORY, NOT BLOCKING — and that is a measured conclusion, not a concession.
    Across three real runs on two titles this produced FIVE distinct false-positive
    classes and zero true positives:

      glossary articles/roles  "Player Association" vs "the Player Association president"
      real-world places        "Pacific Ocean", "Seoul History Museum", "Carthenon Temple"
      transcribed system text  caps runs lifted from bracketed windows
      merged proper nouns      "the modern Earth Jun-Ho sees" -> "Earth Jun-Ho"
      grade prefixes           "an E-Rank Hunter" -> "Rank Hunter"

    Each was individually fixable, and fixing three of them did not stop the fourth and
    fifth from appearing on the next title. Separating an invented PERSON from a
    correctly-named place, rank or organisation needs a tagger, not a longer regex, so
    the honest limit is recorded here rather than hidden behind another heuristic.

    The real defence against an invented character is the audit stage, which sees the
    pages and catches misattribution directly — it caught Jun-Ho touching the wrong
    teammate's ice block. This stays as a report worth reading before approving.
    """
    if not allowed:
        return []
    known = {a.lower() for a in allowed}
    # Individual words of a known name: "Jun-Ho" for "Seo Jun-Ho". Split on WHITESPACE
    # only — splitting hyphens too turned "Seo Jun-Ho" into {seo, jun, ho}, so the very
    # common "Jun-Ho" was never recognised as known.
    for name in list(allowed):
        for part in name.split():
            if len(part) > 2:
                known.add(part.lower())
    # Glossary entries carry articles and roles the narration naturally drops: the
    # glossary says "the Nest Attack Team" and "the Player Association president" while
    # the writing says "Nest Attack Team" and "Player Association". Exact matching flagged
    # both as invented on the first real run. A candidate contained inside a known entry
    # is known — a genuinely invented name is not a sub-phrase of anything we have.
    haystack = " || ".join(known)

    found: dict[str, int] = {}
    # Places are not characters. "Pacific Ocean", "Seoul History Museum" and
    # "Antarctica" are real, correct, and will never be in a CHARACTER glossary — the
    # gate exists to catch an invented PERSON, and flagging geography just teaches the
    # reader to ignore it. A name preceded by a locative preposition is a place.
    text = re.sub(
        r"\b(?:in|at|on|to|from|into|across|near|over|under|inside|outside|toward|towards)"
        r"\s+(?:the\s+)?[A-Z][\w'’-]*(?:[- ][A-Z][\w'’-]*)*",
        " ",
        text or "",
    )
    text = _GRADE_PREFIX_RE.sub("", text)
    for sentence in split_sentences(text):
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
            lowered = candidate.lower()
            if lowered in known or lowered in haystack:
                continue
            # A single common word is far more likely sentence-case than a name.
            if " " not in candidate and "-" not in candidate:
                continue
            # Bracketed system text is transcribed in caps and is not a name.
            if candidate.isupper():
                continue
            # Two adjacent proper nouns from DIFFERENT noun phrases merge under a greedy
            # multi-word match: "the modern Earth Jun-Ho sees outside his window" yields
            # the candidate "Earth Jun-Ho". If any word-run inside the candidate is a
            # name we know, this is a merge artifact, not an invention — an invented
            # person contains no known name at all.
            parts = candidate.split()
            if len(parts) > 1 and any(
                " ".join(parts[i:j]).lower() in known
                for i in range(len(parts))
                for j in range(i + 1, len(parts) + 1)
                if (i, j) != (0, len(parts))
            ):
                continue
            found[candidate] = found.get(candidate, 0) + 1
    return sorted(found)


def _beats_markdown(draft: ScriptDraft) -> str:
    from manhwa2vid.script.beats import _beats_to_markdown

    return _beats_to_markdown(draft)


def generate_story_first_script(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> ScriptDraft:
    if paths["script_draft"].exists() and not force:
        from manhwa2vid.script.beats import load_script_beats

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

    # The closing ask, written as a continuation of the last thing said about the
    # story. Appended AFTER the audit so it sees the final sentence it must follow,
    # and so the audit never tries to ground it against panels.
    text = append_outro(text, meta, paths, config)
    paths["script_freeform"].write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")

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
    # The SERIES TITLE is a legitimate proper noun in the narration — the closing ask
    # names it ("Where <title> goes from here...", script/outro.py) — but it lives in
    # meta, not in the glossary's characters or terms. Promoting this gate to blocking
    # surfaced that immediately: it flagged the title of the very project under test.
    allowed = glossary_names(paths) | {meta.title, *meta.title.split()}
    strangers = unknown_names(text, allowed)
    # BLOCKING. It was warn-only, and both audited videos shipped over it. Promoted only
    # after its false-positive rate was driven to zero and pinned: the two known cases
    # ("Rank Hunter" from "E-Rank Hunter", "Earth Jun-Ho" from a correct sentence) have
    # regression tests, and it passes both projects clean.
    #
    # Note what it CANNOT see: the audio. "Carthenon Temple" and its own glossary alias
    # "Cartenon Temple" are both known names, so this passes — and the TTS then speaks
    # them differently (kˈɑɹθɛnən vs kˈɑɹtɛnən). One place, two spoken names. That is a
    # separate failure with a separate guard; see reports/render_audit_2026-08-28.md §8.
    report.add(
        "name-integrity",
        not strangers,
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

    # --- prose texture vs the reference channel -----------------------------------------
    #
    # The brief ranks these highest, from ~950 comments across 16 videos and 6 channels:
    # viewers punish script errors roughly two orders of magnitude harder than voice
    # quality. All bands are measured with the SAME counters used on the reference SRT
    # (reference/profile_srt.py parity is pinned in tests/test_measure.py), because a
    # threshold derived from one counter and enforced by another is a mistake this project
    # has already made.
    from manhwa2vid.measure.script_text import (
        dialogue_verb_density,
        noun_repetition,
        quoted_span_rate,
        sentence_length_stats,
    )

    verbs = dialogue_verb_density(text)
    report.add(
        "dialogue-verb-density",
        True if verbs["per_1k"] >= _VERBS_MIN_PER_1K else "warn",
        f"{verbs['per_1k']} reporting verbs per 1000 words (floor {_VERBS_MIN_PER_1K}, "
        f"reference {_REF_VERBS_PER_1K}) — the reference lets people SPEAK",
        **verbs,
    )

    quoted = quoted_span_rate(text)
    report.add(
        "quoted-dialogue",
        True if quoted["per_1k"] >= _QUOTED_MIN_PER_1K else "warn",
        f"{quoted['per_1k']} quoted spans per 1000 words (floor {_QUOTED_MIN_PER_1K}, "
        f"reference {_REF_QUOTED_PER_1K})",
        **quoted,
    )

    lengths = sentence_length_stats(text)
    report.add(
        "sentence-length",
        True if lengths["under_8_pct"] >= _SHORT_MIN_PCT else "warn",
        f"{lengths['under_8_pct']}% of sentences run under 8 words (floor "
        f"{_SHORT_MIN_PCT}%, reference {_REF_SHORT_PCT}%); mean {lengths['mean_words']}w "
        f"against the reference's {_REF_MEAN_WORDS}w",
        **lengths,
    )

    # The niche's second-most-liked craft complaint is a channel repeating a bare noun
    # where a pronoun belonged (78 likes for a viewer asking them to count it). Character
    # and place names are exempt — a recap MUST repeat its protagonist's name.
    repeats = noun_repetition(text, exempt=allowed)
    report.add(
        "noun-repetition",
        "warn" if repeats["findings"] else True,
        "; ".join(f"{f['word']} x{f['count']}" for f in repeats["findings"][:5])
        + f" in a {repeats['window_words']}-word window (limit {repeats['max_count']})"
        if repeats["findings"] else "",
        worst_count=repeats["worst_count"],
        findings=repeats["findings"][:10],
    )

    residual = (record.get("revision") or {}).get("residual") or []
    report.add(
        "grounding",
        "warn" if residual else True,
        f"{len(residual)} finding(s) survived the single revision — read them in "
        "script.audit.json before approving",
        residual=len(residual),
    )

    # The style scorecard (qa.style.json) lived here. It was report-only — wrapped in a
    # try/except that printed "skipped" and changed nothing — and it was the story-first
    # path's ONLY use of the character bible, i.e. the last thing keeping the scout/quest
    # machinery attached to script generation. Removed with that machinery; narration
    # style is measured against the reference by hand when it matters.

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
