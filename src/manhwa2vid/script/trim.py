"""Delete what the picture already says, and what the narration should not say at all.

Three rules, all SUBTRACTIVE — this pass can remove words and never add them, which is
the safest kind of change in a pipeline whose dominant defect class is "a later pass
undoes an earlier pass's work". It runs after the density pass and before the rhythm
pass, i.e. before `align_script`, so deleting a sentence cannot desynchronise any
numbering ([[sentence-numbering-spaces]] is about tools that run AFTER align).

The rules, each measured on the shipped scripts before being written:

**Appearance the frame already shows.** "He is a scruffy guy with black hair, dressed in
a faded hoodie, sporting bandages on his face" — the viewer is looking at him. The
writer prompt has said "Describe a character's look at most ONCE" for months and this
still shipped, which is why it is code now and not another instruction. The detection
reuses `lint._ANON_APPEARANCE_RE` (already written and tested, previously with no
production caller) plus the predicate shape that regex was never built for.

Clause-stripping, not sentence-deletion, is the default: that same sentence also says he
is bandaged before the fighting starts, which is story. Only a husk with nothing left in
it ("He is a scruffy guy.") is dropped whole.

**Narration stating its own emotional register.** "It is a miserable life." "It is an
ironic title." "The money is terrible." The sentence before each one already did the
work; saying it out loud is the narrator explaining the joke. Deliberately narrow: a
dummy subject, a copula, an evaluative complement, no glossary name and no new fact.
"It is too late." is plot state and must survive; so must "He is an E-Rank hunter."

**Meta-aside budget** (for the writer-narrator persona). This one only REPORTS. An aside
is a sentence the writer built a paragraph around, and auto-deleting it is exactly the
undo-the-previous-pass failure; the record names them and a human cuts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.script.lint import _ANON_APPEARANCE_RE, _GARMENT
from manhwa2vid.script.sentences import split_sentences

console = Console()

#: Participial appearance clauses the noun-phrase regex cannot reach, e.g.
#: ", dressed in a faded hoodie". Only stripped when the clause actually names a
#: garment — ", sporting bandages on his face" carries an injury, which is story.
_APPEARANCE_CLAUSE_RE = re.compile(
    rf",\s*(?:dressed|clad|decked)\s+(?:in|out\s+in)\s+[^,.]*?(?:{_GARMENT})\b[^,.]*"
    rf"|,\s*wearing\s+[^,.]*?(?:{_GARMENT})\b[^,.]*",
    re.I,
)

#: "an orange-haired healer", "the silver-haired villain" — appearance welded onto the
#: noun, so the with/in/wearing pattern never sees it. Only -haired and -eyed: both are
#: unambiguously the picture's job, where "-armed" or "-handed" can carry plot.
_COMPOUND_LOOK_RE = re.compile(r"\b[\w'’-]+-(?:haired|eyed)\s+", re.I)

#: What is left when every appearance clause is gone and the sentence said nothing else:
#: "He is a scruffy guy." Dropped whole. A role noun ("hunter", "healer", "leader") is
#: NOT in this list — "He is a veteran hunter." is information the viewer cannot see.
_HUSK_RE = re.compile(
    r"^(?:he|she|they|it)\s+(?:is|are)\s+(?:a|an|the)\s+"
    r"(?:[\w'’-]+\s+){0,2}(?:guy|man|woman|kid|girl|boy|person|figure|dude)\s*[.!?]?$",
    re.I,
)

#: Evaluative complements that make a copula sentence a verdict on the story rather than
#: a fact in it. Curated from the four real instances plus their obvious neighbours; a
#: word only belongs here if a sentence built on it could never carry plot.
_EVALUATIVE = (
    r"miserable|ironic|terrible|awful|tragic|brutal|bleak|grim|pathetic|depressing|"
    r"nightmare|disaster|mess|joke|travesty|heartbreaking|devastating|rough|bad|sad"
)

#: "It is a miserable life." / "The money is terrible." / "This is an absolute nightmare."
#: Bounded hard: dummy subject, copula, at most two words of hedging, an evaluative head.
_STATED_REGISTER_RE = re.compile(
    rf"^(?:it|this|that|the\s+[\w'’-]+)\s+(?:is|was|are|were)\s+"
    # ",?" because the filler is often a coordinate adjective — "a small, pathetic
    # indignity" slipped through until the writer-narrator arms produced it.
    rf"(?:(?:a|an|the)\s+)?(?:[\w'’-]+,?\s+){{0,2}}(?:{_EVALUATIVE})"
    rf"(?:\s+[\w'’-]+){{0,2}}\s*[.!?]?$",
    re.I,
)

#: Frames that mark a sentence as the narrator talking about the WORK or about
#: themselves, rather than telling the story. Used only for the budget report.
_META_RE = re.compile(
    r"\b(?:i|i'm|i am|i'll|me|my)\b"
    r"|\btranslat(?:ion|ed|ing)\b|\bthe art\b|\bart style\b|\bartwork\b"
    r"|\bthe author\b|\bthe writing\b|\bthis chapter\b|\bthe chapter\b"
    r"|\bthe manhwa\b|\bthe panel work\b|\bpacing\b|\brushes?\b|\bretelling\b",
    re.I,
)

#: Meta-asides allowed in one paragraph before the record flags it for a human cut.
_META_MAX_PER_PARAGRAPH = 1

#: The six moves, as detectable frames, for the one-note report. On the 20-chapter
#: probe all seven asides were "The art…": a tic, not a writer. Report-only, like every
#: other aside rule — the record names it and a human decides.
_MOVE_FRAMES = {
    "art": re.compile(r"\b(?:the art|art style|artwork|the panel work|the drawing)\b", re.I),
    "explain": re.compile(r"\b(?:i should explain|let me explain|to explain|i'll explain|"
                          r"if you are new to|for anyone new)\b", re.I),
    "translation": re.compile(r"\btranslat", re.I),
    "critique": re.compile(r"\b(?:the writing|the chapter|this chapter|pacing|rushes|rushed|"
                           r"the author|the story (?:rushes|fumbles|stumbles))\b", re.I),
    "self": re.compile(r"\b(?:my retelling|i(?:'m| am) (?:skipping|glossing|smoothing)|"
                       r"i(?:'ll| will) (?:skip|spare you))\b", re.I),
}
#: An aside kind may take at most this share of all asides before it is a tic.
_ONE_NOTE_MAX_SHARE = 0.5
_ONE_NOTE_MIN_ASIDES = 4
#: Words at the head of the script where a meta-aside is never appropriate — the cold
#: open has ~85 words to hook and cannot spend them on the narrator.
_HOOK_WORDS = 85


def _strip_quoted(text: str) -> str:
    """Quoted character dialogue is not the narrator speaking — "I'll kill you" must
    never count as the narrator's first person."""
    return re.sub(r"[\"“][^\"“”]*[\"”]", " ", text)


def first_person_rate(text: str) -> dict[str, Any]:
    """Narrator first-person tokens per 1000 words, excluding quoted dialogue.

    The reference channel measures 0.24/1k and the writer prompt has banned the pronoun
    outright; the writer-narrator persona deliberately spends it. Counted here so the
    spend is visible and bandable rather than a matter of impression.
    """
    stripped = _strip_quoted(text or "")
    words = re.findall(r"[\w'’-]+", stripped)
    hits = len(re.findall(r"\b(?:i|i'm|i've|i'd|i'll|me|my|mine)\b", stripped, re.I))
    per_1k = round(1000 * hits / len(words), 2) if words else 0.0
    return {"count": hits, "words": len(words), "per_1k": per_1k}


def meta_aside_rate(text: str) -> dict[str, Any]:
    """Sentences that talk about the work or the narrator, per 1000 words."""
    sents = [s for p in (text or "").split("\n\n") for s in split_sentences(p)]
    words = len(re.findall(r"[\w'’-]+", text or ""))
    hits = [s for s in sents if _META_RE.search(_strip_quoted(s))]
    per_1k = round(1000 * len(hits) / words, 2) if words else 0.0
    return {"count": len(hits), "sentences": len(sents), "per_1k": per_1k}


def _appearance_edit(sentence: str) -> str | None:
    """The sentence with appearance clauses removed, or None if unchanged."""
    edited = _ANON_APPEARANCE_RE.sub(
        lambda m: f"{m.group(1)} {m.group(2)}".strip(), sentence
    )
    edited = _APPEARANCE_CLAUSE_RE.sub("", edited)
    edited = _COMPOUND_LOOK_RE.sub("", edited)
    edited = re.sub(r"\s{2,}", " ", edited).strip()
    edited = re.sub(r"\s+([,.!?])", r"\1", edited)
    # Removing the adjective can strand the wrong article — "an orange-haired healer"
    # would leave "an healer". Same re-agreement lint.strip_placeholder_descriptors
    # does for its own deletions.
    edited = re.sub(
        r"\b([Aa])n\s+(?=[bcdfghjklmnpqrstvwxyz])", r"\1 ", edited
    )
    # "a" -> "an" only before a vowel that is actually pronounced as one. "u" is
    # excluded wholesale (a unique, a university) and so is "one" (a one-armed
    # veteran), which this rule turned into "an one-armed veteran" the first time it
    # ran against a bake-off script.
    edited = re.sub(
        r"\b([Aa])\s+(?=(?!one\b|once\b|eu)[aeio])", r"\1n ", edited
    )
    return edited if edited and edited != sentence else None


def _meta_findings(paras: list[str]) -> list[dict[str, Any]]:
    """Structural over-budget report: too many per paragraph, back-to-back, or in the
    hook. Reported for a human to cut — never deleted here."""
    findings: list[dict[str, Any]] = []
    # One-note check over the whole script first.
    all_meta = [s for p in paras for s in split_sentences(p) if _META_RE.search(_strip_quoted(s))]
    if len(all_meta) >= _ONE_NOTE_MIN_ASIDES:
        kinds: dict[str, int] = {}
        for s in all_meta:
            for kind, rx in _MOVE_FRAMES.items():
                if rx.search(s):
                    kinds[kind] = kinds.get(kind, 0) + 1
                    break
        for kind, n in kinds.items():
            if n / len(all_meta) > _ONE_NOTE_MAX_SHARE:
                findings.append({
                    "rule": "meta-one-note", "kind": kind, "count": n,
                    "of": len(all_meta),
                    "sentences": [s for s in all_meta if _MOVE_FRAMES[kind].search(s)][:6],
                })
    seen_words = 0
    for i, para in enumerate(paras):
        sents = split_sentences(para)
        flags = [bool(_META_RE.search(_strip_quoted(s))) for s in sents]
        if sum(flags) > _META_MAX_PER_PARAGRAPH:
            findings.append({
                "rule": "meta-per-paragraph", "paragraph": i + 1,
                "count": sum(flags),
                "sentences": [s for s, f in zip(sents, flags) if f],
            })
        for a, b in zip(range(len(flags) - 1), range(1, len(flags))):
            if flags[a] and flags[b]:
                findings.append({
                    "rule": "meta-back-to-back", "paragraph": i + 1,
                    "sentences": [sents[a], sents[b]],
                })
        for s, f in zip(sents, flags):
            if f and seen_words < _HOOK_WORDS:
                findings.append({"rule": "meta-in-hook", "paragraph": i + 1,
                                 "sentences": [s]})
            seen_words += len(s.split())
    return findings


def apply_trim_pass(
    text: str,
    paths: dict[str, Path] | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return (trimmed text, record). Deterministic; deletions only; never raises."""
    from manhwa2vid.script.freeform import paragraphs

    debug_dir = (paths or {}).get("debug")
    if debug_dir and (Path(debug_dir) / "trim_pass.json").exists():
        console.print("[dim]Trim pass already applied — skipping[/]")
        return text, {"skipped": "already applied"}

    paras = paragraphs(text)
    record: dict[str, Any] = {"appearance": [], "stated_register": [], "meta": []}
    out_paras: list[str] = []
    for para in paras:
        # The outro talks to the viewer and is not story prose — same exclusion
        # signature the density and rhythm passes use.
        if "subscri" in para.lower():
            out_paras.append(para)
            continue
        kept: list[str] = []
        for sentence in split_sentences(para):
            # A craft remark is not a register statement, and the difference is the
            # subject: "The money is terrible" is the narrator grading the story it
            # just told, while "The translation is rough" is the writer-narrator doing
            # one of the jobs it was asked to do. Without this guard the register rule
            # eats the persona's translation, art-style and pacing notes — caught by
            # tests/test_trim.py before it could reach a script.
            if _META_RE.search(_strip_quoted(sentence)):
                kept.append(sentence)
                continue
            if _STATED_REGISTER_RE.match(sentence.strip()):
                record["stated_register"].append(sentence)
                continue
            edited = _appearance_edit(sentence)
            if edited is not None:
                if _HUSK_RE.match(edited.strip()):
                    record["appearance"].append({"removed": sentence, "rule": "husk"})
                    continue
                record["appearance"].append({"from": sentence, "to": edited})
                kept.append(edited)
            else:
                kept.append(sentence)
        out_paras.append(" ".join(kept) if kept else para)

    trimmed = "\n\n".join(out_paras)
    record["meta"] = _meta_findings(paragraphs(trimmed))
    record["first_person"] = first_person_rate(trimmed)
    record["meta_rate"] = meta_aside_rate(trimmed)
    n_app, n_reg = len(record["appearance"]), len(record["stated_register"])
    if n_app or n_reg or record["meta"]:
        console.print(
            f"[cyan]Trim pass[/] — {n_app} appearance edit(s), {n_reg} register "
            f"statement(s) dropped, {len(record['meta'])} meta-aside finding(s)"
        )
    _persist(paths, record)
    return trimmed, record


def _persist(paths: dict[str, Path] | None, record: dict[str, Any]) -> None:
    debug_dir = (paths or {}).get("debug")
    if debug_dir:
        Path(debug_dir).mkdir(parents=True, exist_ok=True)
        (Path(debug_dir) / "trim_pass.json").write_text(
            json.dumps(record, indent=1), encoding="utf-8"
        )
