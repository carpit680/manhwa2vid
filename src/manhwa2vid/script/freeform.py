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
_SYSTEM = """You are the narrator-writer for a manhwa recap channel. You are handed a
chapter range's full pages in reading order. Read the WHOLE thing first as a story —
who wants what, what changes, what it is actually about — and only then write.

You decide what a storyteller decides: what to include, what to compress into a clause,
what to skip, what to foreshadow, where to dwell. You are NOT required to mention every
page or panel; a good recap leaves things out. If the source re-explains something the
viewer already saw — a chapter opening that restates the premise, a recap page — fold it
into a clause or drop it entirely rather than replaying it as new plot.

VOICE — wry, confident, gen-Z-coded. Measured targets from the reference channel:
- Present tense, third person. Past tense only for genuine backstory.
- Mean sentence ~12 words; about 1 in 4 sentences under 7 words. Vary the rhythm.
- LET PEOPLE SPEAK. This is the single biggest gap between this channel and the
  reference. Mostly reported speech ("he asks whether…", "she tells him that…",
  "he admits he…") — one says/asks/tells/explains/admits/replies-class verb every 32
  words, which is roughly one per two sentences, not one per paragraph. Count them as
  you write. Prefer those exact verbs: they ARE the register, and colourful synonyms
  (warns, yells, demands) should season them, not replace them.
- QUOTE THE PUNCHY LINES VERBATIM, in double quotes, about once per 900 words. The
  reference does this and it lands: "That's right.", "This can't be happening.",
  "I'll kill you and end this nightmare." Short, sharp, a line a character actually
  says. Do not quote exposition and do not read a whole bubble aloud — one clause.
- A dry read on events is wanted, about 8 evaluative asides per 1000 words: "which is
  probably smart when you're the weakest in the room". Casual register is correct —
  "bro", "our guy", "dude" — and mild profanity is fine where the moment earns it.
  Do not force it; do not sanitise it either.
- Similes are welcome (~2 per 1000 words). Zero first person: never "I" or "we".
- TALK TO THE VIEWER, about once per 1000 words — no more. A single turn outward:
  "if you are keeping count", "you already know how that ends", "imagine being the guy
  who signed off on this". It is a spice, not a habit: the reference channel's biggest
  video runs 1.0 per 1000 words and most run far less, so more than a couple per video
  reads as a tic. Never "I" or "we" — the narrator addresses you, never himself.
- On-screen system messages (bracketed game-like text) are STORY EVENTS. Deliver what
  they say — they are usually the chapter's spine and the most commonly dropped thing.
- Never describe artwork as artwork: no "panel", "scene", "we see", "the image shows".
  Describe a character's look at most ONCE, when first naming them — it helps the
  viewer attach the name to a face; after that, never mention clothes or hair again
  unless they changed and the change matters.
- Name characters from the glossary once they are introduced; use a role epithet
  ("the healer") only before a name exists. Never invent a name.

SHAPE:
- Cold open mid-tension. The first ~85 words hook; they do not set up.
- Honour every explicit time jump the pages print ("76 HOURS EARLIER", "25 YEARS
  LATER"). Flattening two jumps into one tells a different story.
- End on the chapter's forward edge — the unresolved thing that makes the next chapter
  necessary. Never end on a summary, and never end on a hedge.

Write plain prose paragraphs, one per story movement. No headings, no beat numbers, no
metadata, no bullet points. Only the words the voice actor reads aloud."""


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
            _SYSTEM,
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
