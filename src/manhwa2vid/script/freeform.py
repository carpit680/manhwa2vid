"""Write the recap as a story, in one pass, from the pages themselves.

This is the architecture's single creative act. It replaces synopsis → outline seeding
→ per-beat narration → lint rewrite → story-integrity rounds → dialogue retry → voice
pass → alignment rewrite → polish, and it beat all of them on measured content fidelity
and on a blind read (`experiments/oneshot-fp-ch1-2/comparison.md`, arm B).

Two properties are load-bearing and must survive any future edit here:

1. **The model sees pages, not descriptions.** Arm A gave the same strong model the
   old panel-bound structure and it wrote panel captions, inherited the outline's
   wrong time-jump, and lost the chapter's central irony. Feeding perception output to
   the writer is the defect, not a convenience.
2. **Nothing constrains the shape of the output.** No beat count, no per-beat word cap,
   no panel ids, no required-line list. Omission, compression and reordering are the
   storyteller's levers, and every one of them was previously forbidden by construction.

Multi-chapter ranges are written in sequential windows where each call receives the
FULL text written so far — not a digest. Chunking with a thin running summary is the
documented failure mode: beat 17 could not know beat 18 was about to narrate the same
gate entrance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.llm.vision_utils import page_max_width
from manhwa2vid.models import ProjectMeta

console = Console()

#: Register targets are stated as measured numbers because the reference channel was
#: measured, and because prompt-only voice steering failed twice when it was phrased as
#: vibes (see reference/style_profile.md and the project's voice memos).
_PREAMBLE = """You are the narrator-writer for a manhwa recap channel. You are handed a
chapter range's full pages in reading order. Read the WHOLE thing first as a story —
who wants what, what changes, what it is actually about — and only then write.

You decide what a storyteller decides: what to include, what to compress into a clause,
what to skip, what to foreshadow, where to dwell. You are NOT required to mention every
page or panel; a good recap leaves things out. If the source re-explains something the
viewer already saw — a chapter opening that restates the premise, a recap page — fold it
into a clause or drop it entirely rather than replaying it as new plot."""

#: Structure and output format. Shared by every persona: this is craft, not voice.
_SHAPE = """SHAPE:
- Cold open mid-tension. The first ~85 words hook; they do not set up.
- Honour every explicit time jump the pages print ("76 HOURS EARLIER", "25 YEARS
  LATER"). Flattening two jumps into one tells a different story.
- End on the chapter's forward edge — the unresolved thing that makes the next chapter
  necessary. Never end on a summary, and never end on a hedge.

Write plain prose paragraphs, one per story movement. No headings, no beat numbers, no
metadata, no bullet points. Only the words the voice actor reads aloud."""


def _system_for(persona: str | None) -> str:
    """Preamble + the persona's VOICE block + shape/format.

    The voice section used to be hard-coded here, which meant trying a different
    narrator meant editing this file — global, unversioned and unmeasurable. It now
    comes from `script/personas.py`, selected by `script.persona`, defaulting to the
    block that shipped so an unconfigured run is byte-identical.
    """
    from manhwa2vid.script.personas import voice_block

    return f"{_PREAMBLE}\n\n{voice_block(persona)}\n\n{_SHAPE}"


def _budget_words(meta: ProjectMeta, config: dict[str, Any], n_chapters: int) -> tuple[int, int]:
    per_chapter = int(get_nested(config, "script", "words_per_chapter", default=550))
    target = per_chapter * max(1, n_chapters)
    return int(target * 0.9), int(target * 1.15)


def _glossary_block(paths: dict[str, Path]) -> str:
    path = paths["glossary"]
    if not path.exists():
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    return "CHARACTER / TERM GLOSSARY (use these names):\n" + json.dumps(
        data, indent=1, ensure_ascii=False
    )


#: How many printed lines to offer the writer per call. Enough to choose from, few
#: enough that the list cannot become a script to read aloud.
_QUOTABLE_LINES = 30

#: A bubble split across two balloons reaches us truncated — "THE JOB WHERE YOUR LIFE'S
#: ON THE" is a real example from the shipped scene cards. Offering it to the writer
#: invites quoting half a sentence, so a line ending on a function word is dropped.
_DANGLING_TAIL = {
    "the", "a", "an", "and", "or", "but", "of", "on", "in", "to", "with", "for", "at",
    "from", "my", "your", "his", "her", "their", "its", "is", "was", "that", "this",
}


def _quotable_block(paths: dict[str, Path], pages: list[Path]) -> str:
    """Short printed lines from THESE pages, verbatim, as material the writer may quote.

    The prompt has asked for verbatim quotes for months and the writer lands about one
    per thousand words — right at the reference channel's rate, but always at the
    obvious climaxes, because it is working from the pictures and re-reading lettering
    off an image is the hardest thing we ask of it. Handing it the exact strings is
    giving it DATA it lacks rather than repeating an instruction it already follows.

    It doubles as the raw material for the writer-narrator's source notes: you cannot
    remark that a line reads awkwardly if you never had the line.

    Sourced from `scene_cards.json` (`SceneCard.source_text`), not `ocr.json` — the OCR
    artifact is empty on every project built so far, because dialogue is read by the
    vision pass instead. Absent cards mean no block, never an error.
    """
    cards_path = paths.get("scene_json")
    if not cards_path or not Path(cards_path).exists():
        return ""
    try:
        from manhwa2vid.models import SceneCard
        from manhwa2vid.script.grounding import quoted_lines_for_panels

        raw = json.loads(Path(cards_path).read_text(encoding="utf-8"))
        cards = [SceneCard.model_validate(c) for c in raw]
    except Exception:  # noqa: BLE001 — quotable lines are a bonus, never a blocker
        return ""
    # A card covers one or more panels; panel ids are "p<page>_<n>", so the page stem
    # is what ties a card to this window.
    stems = {p.stem for p in pages}
    ids = [
        pid for c in cards for pid in c.panel_ids
        if pid.split("_")[0].lstrip("p") in stems
    ]
    if not ids:
        ids = [pid for c in cards for pid in c.panel_ids]
    lines = [
        ln for ln in quoted_lines_for_panels(ids, cards)
        if len(ln.split()) <= 12
        and ln.split()[-1].strip(".,!?\"'…").lower() not in _DANGLING_TAIL
    ]
    if not lines:
        return ""
    picked = lines[:_QUOTABLE_LINES]
    return (
        "LINES THESE PAGES ACTUALLY PRINT (a few of them — you may quote one verbatim "
        "when it is sharper than any paraphrase, and you may remark when one reads "
        "awkwardly in English; most of them you will simply not need):\n"
        + "\n".join(f'- "{ln}"' for ln in picked)
    )


def _page_windows(pages: list[Path], max_pages: int) -> list[list[Path]]:
    """Split pages into sequential windows, never mid-chapter if avoidable.

    One call is always preferred — the whole-story property is exactly what makes the
    output coherent. Windows exist only because a 156-page range does not fit.
    """
    if len(pages) <= max_pages:
        return [pages]
    n_windows = (len(pages) + max_pages - 1) // max_pages
    size = (len(pages) + n_windows - 1) // n_windows
    return [pages[i : i + size] for i in range(0, len(pages), size)]


def write_freeform_script(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> str:
    """One creative pass over the pages. Returns the narration as prose."""
    out_path = paths["script_freeform"]
    if out_path.exists() and not force:
        console.print("[dim]Using cached freeform script[/]")
        return out_path.read_text(encoding="utf-8")

    # Earlier chapter ranges of this series, if any — empty string for a first part.
    from manhwa2vid.script.series import story_so_far_prompt

    story_so_far = story_so_far_prompt(meta.series_slug, meta.chapters)
    if story_so_far:
        console.print(
            f"[dim]Continuing a series: {story_so_far.count('Chapters ')} earlier "
            f"part(s) treated as already watched[/]"
        )

    pages = sorted(paths["pages"].glob("*.png"))
    if not pages:
        raise FileNotFoundError(f"no pages in {paths['pages']} — run ingest first")

    n_chapters = _chapter_count(meta)
    lo, hi = _budget_words(meta, config, n_chapters)
    max_pages = int(get_nested(config, "script", "freeform_max_pages_per_call", default=60))
    windows = _page_windows(pages, max_pages)

    from manhwa2vid.llm.provider import get_llm_provider

    provider = get_llm_provider(get_nested(config, "script", "provider", default=None), config)
    model = get_nested(config, "script", "freeform_model", default=None)
    if model:
        provider.vision_model = model
    provider.temperature = float(
        get_nested(config, "script", "narration_temperature", default=0.9)
    )

    from manhwa2vid.script.personas import DEFAULT_PERSONA, PERSONAS

    persona = str(get_nested(config, "script", "persona", default=DEFAULT_PERSONA))
    system = _system_for(persona)
    if persona != DEFAULT_PERSONA:
        known = "" if persona in PERSONAS else " (unknown — using the default voice)"
        console.print(f"[dim]Narrator persona: {persona}{known}[/]")

    glossary = _glossary_block(paths)
    written: list[str] = []
    per_window_lo, per_window_hi = lo // len(windows), hi // len(windows)

    for i, window in enumerate(windows, start=1):
        if len(windows) > 1:
            console.print(
                f"[cyan]Writing[/] window {i}/{len(windows)} "
                f"(pages {window[0].stem}–{window[-1].stem})"
            )
        else:
            console.print(f"[cyan]Writing[/] {len(pages)} page(s) in one pass")

        parts = [glossary] if glossary else []
        quotable = _quotable_block(paths, window)
        if quotable:
            parts.append(quotable)
        # What the viewer already watched, from EARLIER chapter ranges of this series.
        # Distinct from "the recap so far" below, which is this video's own text: that
        # one says "do not repeat yourself", this one says "these people have already
        # been introduced, to a viewer who is continuing".
        if story_so_far:
            parts.append(story_so_far)
        if written:
            # The FULL text so far, never a digest. A thin running summary was measured
            # too weak to stop two beats narrating the same moment.
            parts.append(
                "THE RECAP SO FAR (already written — continue it, never repeat it):\n\n"
                + "\n\n".join(written)
            )
            parts.append(
                f"Continue from exactly where that leaves off. Write {per_window_lo}-"
                f"{per_window_hi} more words covering ONLY the pages below. Do not "
                "re-introduce characters the text above already introduced, and do not "
                "restate anything it already said."
            )
        else:
            parts.append(f"TARGET LENGTH: {per_window_lo}-{per_window_hi} words.")
        parts.append("The chapter pages follow in reading order. Read them all, then write.")

        raw = provider.describe_labeled_panels_text(
            [(f"[page {p.stem}]", p) for p in window],
            system,
            "\n\n".join(parts),
            max_width=page_max_width(config),
        )
        written.append(raw.strip())

    text = "\n\n".join(written).strip()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text + "\n", encoding="utf-8")
    console.print(
        f"[green]Freeform script[/] — {len(text.split())} words, "
        f"{len(paragraphs(text))} paragraph(s) (budget {lo}-{hi})"
    )
    return text


def _chapter_count(meta: ProjectMeta) -> int:
    """How many chapters this project spans, from the '1-5' / '3' chapters string."""
    spec = (meta.chapters or "").strip()
    if "-" in spec:
        first, _, last = spec.partition("-")
        try:
            return max(1, int(last) - int(first) + 1)
        except ValueError:
            return 1
    return 1


def paragraphs(text: str) -> list[str]:
    """The narration's paragraphs — the unit that becomes a beat and gets its own audio."""
    return [p.strip() for p in (text or "").split("\n\n") if p.strip()]
