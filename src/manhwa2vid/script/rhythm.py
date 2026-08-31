"""Break sentence-opener monotony with connective tissue — deterministically.

Measured root cause (2026-08-31, tools/measure_corpus.py detectors on both corpora):
the reference channel opens 25.7% of sentences with a pronoun, ~15% with a connector
("Then" alone is its #3 opener, 438 uses = 7.5%), and repeats an opener back-to-back
4.6% of the time. Our three scripts ran 35.9-48.9% pronoun-open, 2.3-5.3% connector,
11.5-27.3% back-to-back — the same reported-speech chains as the reference ("he tells"
x23 on Solo Leveling) with none of the linking. It reads as a list.

Prompt-only voice changes have failed twice in this project when measured
([[prompt-only-voice-changes-fail]]), and the density pass demonstrated that a free
LLM rewrite ratchets meaning away even when every gate passes. So this pass is CODE:

- **merge**: two adjacent sentences with the SAME pronoun subject and a reporting
  verb fold into one with subject elision — "He asks X. He tells her Y." becomes
  "He asks X, then tells her Y." Only pronoun subjects (a name-subject merge would
  drop a glossary-name occurrence); only reporting verbs (elision of anything else
  risks meaning); never across quoted dialogue; capped at `_MERGE_MAX_WORDS`.
- **insert**: a sentence opening with the word that opened the previous sentence gets
  "Then " — and only "Then": But/So assert contrast/consequence the code cannot
  check, while consecutive recap sentences describe consecutive events, which is
  exactly what "then" says. Stative verbs (is/seems/knows...) are excluded because
  "Then he is terrified" is not English rhythm, it is a mistake.

Every edit adds or removes FUNCTION WORDS ONLY (a connector in, an elided pronoun
out); `_content_words` verifies the multiset at the end and any violation ships the
paragraph verbatim. The pass records itself in debug/rhythm_pass.json (same
idempotency pattern as the density pass) including the merge map — (kept, absorbed)
sentence numbers — so tools/rebind_from_claims.py can renumber persisted matcher
claims instead of re-paying the vision calls.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.script.sentences import split_sentences

console = Console()

#: Subjects a merge may elide. Names are excluded on purpose: dropping one changes
#: the glossary-name count that the audit acceptance and the lint both watch.
_PRONOUN_SUBJECTS = {"he", "she", "they", "it"}

#: Third-person reporting verbs — the "says-dominated" verb class the reference
#: channel runs on ([[reference-channel-measurements]]). Both halves of a merge must
#: open subject+one-of-these for the elision to be meaning-safe.
_REPORTING_VERBS = {
    "asks", "tells", "says", "explains", "warns", "admits", "adds", "replies",
    "answers", "insists", "demands", "wonders", "notes", "orders", "begs",
    "snaps", "mutters", "promises", "claims", "argues", "offers", "suggests",
    "reminds", "yells", "shouts", "whispers", "agrees", "refuses", "confirms",
    "announces", "declares", "reports", "jokes", "teases", "complains",
    "apologizes", "thanks", "greets", "screams", "calls", "points",
}

#: "Then <stative>" is not rhythm, it is a mistake — no insertion before these.
_STATIVE_VERBS = {
    "is", "was", "are", "were", "has", "have", "had", "seems", "looks",
    "feels", "stays", "remains", "wants", "knows", "needs", "means",
}

#: Openers that count as connectors, for measurement and the gate. The conservative
#: reference-derived set — the same one the corpus measurement used.
_CONNECTOR_OPENERS = {"then", "but", "so", "and", "after", "if", "instead", "meanwhile"}

#: Words ignored by the content-multiset safety check: everything this pass is
#: allowed to add or remove, and nothing else.
_EDIT_WORDS = {"then"} | _PRONOUN_SUBJECTS

_MERGE_MAX_WORDS = 28


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


def _content_words(text: str) -> Counter:
    return Counter(w for w in _words(text) if w not in _EDIT_WORDS)


def opener_profile(text: str) -> dict[str, Any]:
    """Opener distribution over the whole text, same detectors as the corpus tool."""
    sents = [s for p in text.split("\n\n") for s in split_sentences(p) if s.strip()]
    if not sents:
        return {"sentences": 0, "pronoun_open_pct": 0.0, "connector_pct": 0.0,
                "b2b_pct": 0.0}
    firsts = []
    for s in sents:
        ws = _words(s)
        firsts.append(ws[0] if ws else "")
    pron = sum(1 for w in firsts if w in _PRONOUN_SUBJECTS | {"his", "her", "their", "its"})
    conn = sum(1 for w in firsts if w in _CONNECTOR_OPENERS)
    b2b = sum(1 for a, b in zip(firsts, firsts[1:]) if a and a == b)
    n = len(sents)
    return {
        "sentences": n,
        "pronoun_open_pct": round(100 * pron / n, 1),
        "connector_pct": round(100 * conn / n, 1),
        "b2b_pct": round(100 * b2b / n, 1),
    }


def _merge_frame(sentence: str) -> tuple[str, str, str] | None:
    """(subject, verb, remainder-after-subject) when the sentence opens
    pronoun-subject + reporting-verb and carries no quoted dialogue."""
    if '"' in sentence or "“" in sentence or "”" in sentence:
        return None
    m = re.match(r"\s*(He|She|They|It)\s+([a-z]+)\b(.*)", sentence)
    if not m:
        return None
    subject, verb, rest = m.group(1), m.group(2), m.group(3)
    if subject.lower() not in _PRONOUN_SUBJECTS or verb not in _REPORTING_VERBS:
        return None
    return subject, verb, (verb + rest).strip()


def _rhythm_paragraph(
    para: str, start_no: int
) -> tuple[str, list[tuple[int, int]], int]:
    """(new paragraph, merges as (kept, absorbed) GLOBAL sentence numbers, edits)."""
    sents = split_sentences(para)
    merges: list[tuple[int, int]] = []
    edits = 0

    # Pass 1 — pairwise merges. After a merge, skip past the absorbed sentence so
    # chains never fold into one endless line.
    out: list[str] = []
    merged_idx: set[int] = set()       # OUT indices that already carry ", then "
    i = 0
    while i < len(sents):
        cur = sents[i]
        if i + 1 < len(sents):
            a, b = _merge_frame(cur), _merge_frame(sents[i + 1])
            if (
                a and b and a[0] == b[0]
                and len(_words(cur)) + len(_words(sents[i + 1])) <= _MERGE_MAX_WORDS
            ):
                merged = re.sub(r"[.!?]\s*$", "", cur) + ", then " + b[2]
                merged_idx.add(len(out))
                out.append(merged)
                merges.append((start_no + i, start_no + i + 1))
                edits += 1
                i += 2
                continue
        out.append(cur)
        i += 1

    # Pass 2 — "Then " where the same opener still repeats back-to-back. Never on the
    # first sentence, never twice in a row, never on a sentence a merge already gave a
    # "then" (read aloud, "Then he tells X, then explains Y" stacks the word), never
    # before a stative verb, and never on an "it" subject — "Then it radiates a heavy
    # pressure" turns scene description into a false event. Same reasoning excludes
    # the naming idiom: "They call him the World's Weakest" states a standing fact,
    # and "Then" would misstate it as something that happens next.
    prev_inserted = False
    for j in range(1, len(out)):
        wa, wb = _words(out[j - 1]), _words(out[j])
        if not wa or not wb or wa[0] != wb[0] or prev_inserted or j in merged_idx:
            prev_inserted = False
            continue
        if wb[0] not in _PRONOUN_SUBJECTS - {"it"} or (
            len(wb) > 1 and wb[1] in _STATIVE_VERBS
        ):
            prev_inserted = False
            continue
        if re.match(r"\s*\w+\s+calls?\s+(him|her|them|it)\b", out[j]):
            prev_inserted = False
            continue
        stripped = out[j].lstrip()
        out[j] = "Then " + stripped[0].lower() + stripped[1:]
        prev_inserted = True
        edits += 1

    return " ".join(out), merges, edits


def apply_rhythm_pass(
    text: str,
    paths: dict[str, Path] | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return (revised text, record). Deterministic; never worsens the text.

    A paragraph whose edited form fails the content-multiset check ships verbatim —
    that check failing means a bug in this file, not in the script, and the failure
    is recorded loudly rather than papered over.
    """
    from manhwa2vid.script.freeform import paragraphs

    debug_dir = (paths or {}).get("debug")
    if debug_dir and (Path(debug_dir) / "rhythm_pass.json").exists():
        console.print("[dim]Rhythm pass already applied — skipping[/]")
        return text, {"skipped": "already applied"}

    paras = paragraphs(text)
    record: dict[str, Any] = {
        "before": opener_profile(text), "merges": [], "insertions": 0, "violations": [],
    }
    new_paras: list[str] = []
    no = 1
    for para in paras:
        n_sents = len(split_sentences(para))
        # The outro talks to the viewer and is not narration rhythm's business —
        # same signature as the density pass's exclusion.
        if "subscri" in para.lower():
            new_paras.append(para)
            no += n_sents
            continue
        new_para, merges, edits = _rhythm_paragraph(para, no)
        if edits and _content_words(new_para) != _content_words(para):
            record["violations"].append({"paragraph": para[:80]})
            new_paras.append(para)
        elif edits:
            new_paras.append(new_para)
            record["merges"].extend(merges)
            record["insertions"] += edits - len(merges)
        else:
            new_paras.append(para)
        no += n_sents

    revised = "\n\n".join(new_paras)
    record["after"] = opener_profile(revised)
    if record["merges"] or record["insertions"]:
        b, a = record["before"], record["after"]
        console.print(
            f"[cyan]Rhythm pass[/] — {len(record['merges'])} merge(s), "
            f"{record['insertions']} connector(s); pronoun-open "
            f"{b['pronoun_open_pct']}%→{a['pronoun_open_pct']}%, b2b "
            f"{b['b2b_pct']}%→{a['b2b_pct']}%, connectors "
            f"{b['connector_pct']}%→{a['connector_pct']}%"
        )
    _persist(paths, record)
    return revised, record


def _persist(paths: dict[str, Path] | None, record: dict[str, Any]) -> None:
    debug_dir = (paths or {}).get("debug")
    if debug_dir:
        Path(debug_dir).mkdir(parents=True, exist_ok=True)
        (Path(debug_dir) / "rhythm_pass.json").write_text(
            json.dumps(record, indent=1), encoding="utf-8"
        )
