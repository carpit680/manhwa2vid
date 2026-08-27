"""Read the chapter's pages and record what they actually SAY.

This is the story-first architecture's only perception stage, and it is deliberately
much smaller than the scene-card pass it replaces. It does not describe artwork, does
not attribute speakers to panels, and does not try to build a character bible. It
extracts the things a recap is *accountable* to — verbatim on-screen system messages,
the dialogue that carries plot, explicit time markers, and the names in play — so that
a later audit can ask "did the narration deliver this?" without re-reading the pages.

The writer does NOT consume this file. That is the point: the 2x2 experiment showed
that a writer fed descriptions of panels writes captions, while a writer fed the pages
themselves writes a story (`experiments/oneshot-fp-ch1-2/comparison.md`). Perception
here exists to hold the writing accountable afterwards, not to feed it.

Notably, Frozen Player's OCR artifact is entirely empty — PaddleOCR extracts nothing
from those pages — and the one-shot arms still recovered every system message by
reading the images. So this stage reads pixels, and treats `ocr.json` as an optional
cross-check rather than a source.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.llm.vision_utils import page_max_width
from manhwa2vid.models import ProjectMeta, save_json

console = Console()

_SYSTEM = """You are cataloguing what a manhwa chapter's pages literally show, for a
fact-check that runs after someone else writes the recap. You are not writing prose and
not describing artwork.

Return JSON only, with this shape:

{
  "system_messages": ["[YOU HAVE COMPLETELY ABSORBED THE FROST QUEEN'S NUCLEUS.]", ...],
  "key_dialogue": [{"page": "0012", "speaker": "Deok-gu", "line": "humanity has only cleared the second floor"}],
  "time_markers": [{"page": "0009", "text": "76 HOURS EARLIER"}],
  "cast": [{"name": "Seo Jun-Ho", "aliases": ["Specter"], "first_page": "0001", "note": "protagonist"}],
  "plot_spine": ["one short sentence per genuine story turn, in page order"]
}

Rules:
- system_messages: transcribe bracketed/boxed game-like text VERBATIM, including
  brackets and capitalisation. These are the chapter's spine and the single most
  common thing a recap drops. Include every one.
- key_dialogue: only lines that change what the viewer knows. Skip greetings, reaction
  noises, and banter that carries no information. Quote the meaningful clause; do not
  paraphrase numbers.
- time_markers: any explicit on-page time reference ("25 YEARS LATER", "76 HOURS
  EARLIER", a dated caption). Chapters routinely jump, and a recap that flattens two
  jumps into one is telling a different story.
- cast: only characters actually named or clearly addressed on the page. Use the name
  as printed. Do not invent names for unnamed characters — describe them in `note` and
  leave `name` as the printed descriptor.
- plot_spine: 8-25 entries, each a plain sentence, in the order events occur ON THE
  PAGE (not story chronology). This is a checklist, not narration.
Report only what is on the pages. If you cannot read something, omit it rather than
guessing."""


def read_chapter_facts(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Extract the accountable facts from the chapter's pages."""
    out_path = paths["chapter_facts_json"]
    if out_path.exists() and not force:
        console.print("[dim]Using cached chapter facts[/]")
        return json.loads(out_path.read_text(encoding="utf-8"))

    pages = sorted(paths["pages"].glob("*.png"))
    if not pages:
        raise FileNotFoundError(f"no pages in {paths['pages']} — run ingest first")

    from manhwa2vid.llm.provider import get_llm_provider

    provider = get_llm_provider(get_nested(config, "read", "provider", default=None), config)
    model = get_nested(config, "read", "model", default=None)
    if model:
        provider.vision_model = model
    provider.temperature = 0.0

    console.print(f"[cyan]Reading[/] {len(pages)} page(s) for chapter facts")
    # describe_labeled_panels interleaves each label immediately before its image, so the
    # page binding is positional in the message rather than a count the model has to
    # maintain — the same reason the scene pass uses it (a 59-image run once came back
    # correct but bound three positions off).
    raw = provider.describe_labeled_panels(
        [(f"[page {p.stem}]", p) for p in pages], _SYSTEM, max_width=page_max_width(config)
    )
    facts = json.loads(raw) if isinstance(raw, str) else raw
    facts.setdefault("system_messages", [])
    facts.setdefault("key_dialogue", [])
    facts.setdefault("time_markers", [])
    facts.setdefault("cast", [])
    facts.setdefault("plot_spine", [])

    merge_cast_into_glossary(facts.get("cast", []), paths)
    save_json(out_path, facts)
    console.print(
        f"[green]Chapter facts[/] — {len(facts['system_messages'])} system message(s), "
        f"{len(facts['key_dialogue'])} key line(s), {len(facts['time_markers'])} time "
        f"marker(s), {len(facts['plot_spine'])} spine item(s)"
    )
    return facts


def merge_cast_into_glossary(cast: list[dict[str, Any]], paths: dict[str, Path]) -> dict[str, Any]:
    """Add newly-seen names to the project glossary without overwriting human edits.

    The glossary is the whole identity system in this architecture — replacing the
    scout/quest/consolidate/link machinery whose accumulated state produced a protagonist
    called "large orange demon" and a lead pronounced "they" off 174 polluted
    descriptors. A flat, human-editable name->aliases map cannot drift that way, and
    when it is wrong a person fixes it in one line.

    Human edits always win: an existing entry is never rewritten, only extended with
    aliases it does not already have.
    """
    path = paths["glossary"]
    glossary: dict[str, Any] = (
        json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    )
    characters: dict[str, list[str]] = glossary.setdefault("characters", {})

    added_names, added_aliases = 0, 0
    for entry in cast:
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        # `str(a)` on a JSON null yields the literal "None", which is truthy — a null
        # in the model's alias list became a character alias named "None", and the
        # identity gate then treated "None" as a name it knows.
        aliases = [
            str(a).strip()
            for a in (entry.get("aliases") or [])
            if isinstance(a, str) and a.strip()
        ]
        if name not in characters:
            characters[name] = aliases
            added_names += 1
            continue
        known = characters[name]
        for alias in aliases:
            if alias not in known and alias != name:
                known.append(alias)
                added_aliases += 1

    if added_names or added_aliases:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(glossary, indent=2, ensure_ascii=False), encoding="utf-8")
        console.print(
            f"[dim]Glossary: +{added_names} name(s), +{added_aliases} alias(es)[/]"
        )
    return glossary


def glossary_names(paths: dict[str, Path]) -> set[str]:
    """Every proper name the narration is allowed to use, for the identity gate."""
    path = paths["glossary"]
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for name, aliases in (data.get("characters") or {}).items():
        names.add(name)
        names.update(aliases or [])
    for term, aliases in (data.get("terms") or {}).items():
        names.add(term)
        names.update(aliases or [])
    if data.get("protagonist"):
        names.add(data["protagonist"])
    return {n for n in names if n}
