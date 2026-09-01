"""Targeted dialogue-density pass: turn narrated summary back into reported speech.

The prompt asks the writer for a reporting verb every ~32 words, and long titles ignore
it wherever they compress: Solo Leveling packs five chapters at ~16 words per page and
delivered 15 paragraphs with literally ZERO reporting verbs (~1160 of 2669 words), while
Frozen Player at ~47 words per page mostly complied. The failure is local — identifiable
dry paragraphs — so the repair is local too: one text-only call carrying only the dry
paragraphs, not a regeneration that re-pays every vision call and re-rolls everything
the audit already fixed.

This is a prose-mutating pass, and this project's dominant defect class is a later pass
undoing an earlier one (see script/audit.py's history note). Hence the same doctrine
`revise_once` uses, applied per paragraph: a rewrite is accepted only if it strictly
improves the thing this pass exists for and breaks nothing measurable —

  - reported-speech density strictly rises,
  - word count stays within ±15% (word count IS runtime),
  - the paragraph still lints clean (no fragments, no mixed-number pronouns),

otherwise the original paragraph ships verbatim. The worst possible outcome is the text
unchanged; the pass can only converge toward the register the gate measures.

The raw material is `chapter_facts.json["key_dialogue"]` — verbatim on-page lines the
read pass already extracted — so the model is converting summary into speech the pages
actually contain, not inventing conversations. Feeding it here is consistent with the
"writer never sees panel descriptions" principle: these are printed WORDS, not artwork.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.measure.script_text import dialogue_verb_density

console = Console()

#: Gate floor, owned here so the pass and the gate can never disagree. 18/1k is the
#: hardening brief's number, kept because it sits well under the reference's
#: like-for-like 31.34 — the pass aims at the reference rate, the gate forgives more.
VERBS_MIN_PER_1K = 18.0

#: Only paragraphs with room to actually hold dialogue; a two-line beat with zero verbs
#: is often legitimately visual ("He steps into the light.").
_MIN_WORDS = 40

#: Word-count tolerance for an accepted rewrite. Narration is audio-locked, so word
#: count is runtime; ±15% on a ~70-word paragraph is a couple of seconds.
_LENGTH_TOLERANCE = 0.15

_SYSTEM = """You convert narrated summary into reported speech, in place.

You are given numbered paragraphs from a manhwa recap narration, plus verbatim lines
the manhwa's pages actually print. The paragraphs SUMMARIZE conversations instead of
letting people speak. Rewrite each paragraph so the same events are told through
reported speech.

Rules:
- Use these reporting verbs, present tense: says, asks, tells, explains, admits,
  replies, answers. They are the register. ("He tells Song there has to be a rule.")
- NO new events, no new speakers, no invented facts. Only re-voice what the paragraph
  already says, using the printed lines as raw material where they fit.
- Keep each paragraph within about 10% of its current length.
- Keep the narrator's asides and tone exactly as they are.
- Return JSON only: {"paragraphs": {"<number>": "<rewritten paragraph>", ...}}.
  Every number you were given must appear. No other keys, no commentary."""


def _accept(original: str, candidate: str) -> tuple[bool, str]:
    """The strictly-improves guard. Returns (accepted, reason)."""
    candidate = " ".join((candidate or "").split())
    if not candidate:
        return False, "empty"
    d0 = dialogue_verb_density(original)["per_1k"]
    d1 = dialogue_verb_density(candidate)["per_1k"]
    if d1 <= d0:
        return False, f"density did not rise ({d0} -> {d1})"
    w0, w1 = len(original.split()), len(candidate.split())
    if abs(w1 - w0) > _LENGTH_TOLERANCE * w0:
        return False, f"length moved {w0} -> {w1} words (>±{_LENGTH_TOLERANCE:.0%})"
    # Both of these were caught by READING the first live output, not by any metric.
    # "The narrator explains that a magical core…" — the pass describing itself, read
    # aloud to the viewer. And a rewrite that converts a verbatim quote into reported
    # speech ("shouts, \"I'm going!\"" -> "tells the group that he is going") trades
    # one gate's currency for another's; quotes are rarer and worth more.
    if "the narrat" in candidate.lower():
        return False, "meta: candidate mentions the narrator"
    from manhwa2vid.measure.script_text import quoted_span_rate

    q0 = quoted_span_rate(original)["quoted_spans"]
    q1 = quoted_span_rate(candidate)["quoted_spans"]
    if q1 < q0:
        return False, f"quotes lost ({q0} -> {q1})"
    # Belt and braces with the targeting rule above: even a paragraph that qualified
    # may contain the narrator's own voice, and a rewrite that quietly drops it trades
    # the persona for a metric. Same reasoning as the quote check.
    from manhwa2vid.script.trim import first_person_rate, meta_aside_rate

    if meta_aside_rate(candidate)["count"] < meta_aside_rate(original)["count"]:
        return False, "the narrator's own voice was rewritten away"
    if first_person_rate(candidate)["count"] < first_person_rate(original)["count"]:
        return False, "first person lost"
    from manhwa2vid.models import ScriptBeat
    from manhwa2vid.script.lint import lint_broken_sentences

    broken = lint_broken_sentences(
        [ScriptBeat(beat_id=1, panel_ids=[], narration=candidate)]
    )
    if broken:
        return False, f"lint: {broken[1][0]}"
    return True, ""


def apply_density_pass(
    text: str,
    paths: dict[str, Path],
    config: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Return (possibly revised text, record). Never raises; never worsens the text."""
    from manhwa2vid.script.freeform import paragraphs

    # Idempotency: this pass runs ONCE per script. Its record survives in debug/, and
    # a stage re-run (rebuilding gates, re-aligning) must not apply it a second time —
    # measured on Solo Leveling, the second application turned "He explains that it is
    # a Double Lair. They actually found a secondary dungeon hidden inside the first."
    # into "He explains to the group that the double lair looks like it is actually
    # real": denser, same length, lints clean, and tells the viewer less. The per-
    # paragraph acceptance checks density, words and lint — not meaning — so repeat
    # applications ratchet meaning away. A fresh script (--force upstream) clears
    # debug/ with the other artifacts.
    debug_dir = paths.get("debug")
    if debug_dir and (Path(debug_dir) / "density_pass.json").exists():
        console.print("[dim]Density pass already applied — skipping[/]")
        return text, {"skipped": "already applied"}

    from manhwa2vid.script.trim import meta_aside_rate

    paras = paragraphs(text)
    targets = {
        i: p for i, p in enumerate(paras)
        if len(p.split()) >= _MIN_WORDS
        and dialogue_verb_density(p)["per_1k"] < VERBS_MIN_PER_1K
        # A paragraph carrying the writer-narrator's own voice — an explainer, a
        # translation note, a remark about the art — is verb-poor BY DESIGN: nobody is
        # speaking in it. Rewriting it into reported speech would delete exactly the
        # thing the persona exists to add, which is this project's most repeated defect
        # class (a later pass undoing an earlier pass's work). Its low density is not a
        # fault to repair.
        and meta_aside_rate(p)["count"] == 0
        # The outro is the narrator talking to the viewer — no dialogue to report. The
        # pass runs before append_outro on a fresh run, but a CACHED freeform already
        # carries its outro, so the exclusion must be explicit (same signature as the
        # outro's own idempotency guard).
        and "subscri" not in p.lower()
    }
    record: dict[str, Any] = {
        "targets": sorted(targets), "accepted": [], "rejected": {},
    }
    if not targets:
        return text, record

    lines = []
    facts_path = paths.get("chapter_facts_json")
    if facts_path and Path(facts_path).exists():
        facts = json.loads(Path(facts_path).read_text(encoding="utf-8"))
        lines = [
            f'- {d.get("speaker", "?")}: "{d.get("line", "")}"'
            for d in (facts.get("key_dialogue") or [])
            if d.get("line")
        ]

    numbered = "\n\n".join(f"PARAGRAPH {i}:\n{p}" for i, p in sorted(targets.items()))
    printed = "\n".join(lines) if lines else "(none extracted)"
    payload = (
        f"PRINTED LINES FROM THE PAGES:\n{printed}\n\n"
        f"PARAGRAPHS TO REWRITE:\n\n{numbered}"
    )

    try:
        from manhwa2vid.llm.provider import get_llm_provider

        provider = get_llm_provider(
            get_nested(config, "script", "provider", default=None), config
        )
        raw = provider.complete(_SYSTEM, payload) or ""
        # Real providers fence their JSON in markdown and may append prose after it —
        # json.loads on the tail raises "Extra data" and the whole pass silently
        # no-ops (it did, on both titles, first live run). raw_decode reads the first
        # complete JSON value and ignores whatever follows.
        start = raw.find("{")
        revised = (
            json.JSONDecoder().raw_decode(raw[start:])[0] if start != -1 else {}
        )
        revised = (revised or {}).get("paragraphs") or {}
    except Exception as exc:  # noqa: BLE001 — a density pass is never worth failing a run
        console.print(f"[yellow]Density pass skipped ({exc})[/]")
        record["error"] = str(exc)
        _persist(paths, record)
        return text, record

    out = list(paras)
    for i in sorted(targets):
        candidate = revised.get(str(i)) or revised.get(i) or ""
        ok, reason = _accept(paras[i], str(candidate))
        if ok:
            out[i] = " ".join(str(candidate).split())
            record["accepted"].append(i)
        else:
            record["rejected"][i] = reason

    if record["accepted"]:
        console.print(
            f"[dim]Density pass: {len(record['accepted'])}/{len(targets)} dry "
            f"paragraph(s) re-voiced ({sorted(record['accepted'])})[/]"
        )
    _persist(paths, record)
    return "\n\n".join(out), record


def _persist(paths: dict[str, Path], record: dict[str, Any]) -> None:
    debug_dir = paths.get("debug")
    if debug_dir:
        Path(debug_dir).mkdir(parents=True, exist_ok=True)
        (Path(debug_dir) / "density_pass.json").write_text(
            json.dumps(record, indent=1), encoding="utf-8"
        )
