"""Series-level memory: what carries from one chapter range to the next.

A recap channel does not restart at chapter 21. It continues, and the viewer who
watched part one already knows who these people are. Two things therefore have to
outlive a single project, and exactly two:

**Identity.** The glossary is this architecture's whole identity system — a flat,
human-editable name->aliases map that replaced the scout/quest/consolidate machinery
whose accumulated state elected a protagonist called "large orange demon". It was
per-project, so chapters 21-40 re-derived every name from scratch and a human's one-line
repair had to be made again for every part. It now lives at the SERIES level: seeded
into each new project at init, merged back after the read pass. A fix applied once holds
for every future part.

**Story so far.** The writer is told what the viewer already knows, so part two opens on
chapter 21 instead of re-establishing the premise. Deliberately a short prose summary
per part, not a structured state machine: the failure mode this architecture exists to
avoid is accumulated state drifting, and prose that a person can read and correct is the
same repair surface the glossary is.

Nothing else crosses. Panels, timings, audit findings and QA reports are properties of
one range and are meaningless to the next.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.config import find_repo_root
from manhwa2vid.models import series_paths

console = Console()


def parse_range(chapters: str) -> tuple[int, int]:
    """"1-20" -> (1, 20); "7" -> (7, 7). Tolerant of whitespace and junk."""
    text = (chapters or "").strip()
    try:
        if "-" in text:
            lo, _, hi = text.partition("-")
            return int(lo.strip()), int(hi.strip())
        value = int(text)
        return value, value
    except ValueError:
        return 0, 0


def _paths(series_slug: str) -> dict[str, Path]:
    p = series_paths(find_repo_root(), series_slug)
    p["series_glossary"] = p["series_dir"] / "glossary.json"
    p["story_so_far"] = p["series_dir"] / "story_so_far.json"
    return p


# --------------------------------------------------------------------------- glossary
def load_series_glossary(series_slug: str) -> dict[str, Any]:
    path = _paths(series_slug)["series_glossary"]
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def seed_project_glossary(series_slug: str, project_glossary: Path) -> int:
    """Copy the series' known cast into a new project. Returns names seeded.

    Runs at init, before anything has read a page, so the read pass starts from names
    the series already agreed on instead of inventing its own.
    """
    series = load_series_glossary(series_slug)
    if not series:
        return 0
    project_glossary.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        json.loads(project_glossary.read_text(encoding="utf-8"))
        if project_glossary.exists()
        else {}
    )
    merged = {
        "characters": {**(series.get("characters") or {}), **(existing.get("characters") or {})},
        "terms": {**(series.get("terms") or {}), **(existing.get("terms") or {})},
        "protagonist": existing.get("protagonist") or series.get("protagonist") or "",
        "notes": existing.get("notes") or series.get("notes") or "",
    }
    project_glossary.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(merged["characters"]) + len(merged["terms"])


def promote_to_series(series_slug: str, project_glossary: Path) -> int:
    """Merge a project's glossary UP into the series. Returns entries added.

    Additive only, and the same rule the project-level merge follows: an existing entry
    is extended with aliases it does not have, never rewritten. A human edit made in any
    part survives every later one.
    """
    if not project_glossary.exists():
        return 0
    try:
        project = json.loads(project_glossary.read_text(encoding="utf-8"))
    except ValueError:
        return 0

    paths = _paths(series_slug)
    paths["series_dir"].mkdir(parents=True, exist_ok=True)
    series = load_series_glossary(series_slug)
    added = 0
    for section in ("characters", "terms"):
        target = series.setdefault(section, {})
        for name, aliases in (project.get(section) or {}).items():
            if name not in target:
                target[name] = list(aliases or [])
                added += 1
                continue
            for alias in aliases or []:
                if alias not in target[name] and alias != name:
                    target[name].append(alias)
                    added += 1
    if project.get("protagonist") and not series.get("protagonist"):
        series["protagonist"] = project["protagonist"]
    paths["series_glossary"].write_text(
        json.dumps(series, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return added


# --------------------------------------------------------------------------- story
def load_parts(series_slug: str) -> list[dict[str, Any]]:
    path = _paths(series_slug)["story_so_far"]
    if not path.exists():
        return []
    try:
        return list(json.loads(path.read_text(encoding="utf-8")).get("parts") or [])
    except ValueError:
        return []


def preceding_parts(series_slug: str, chapters: str) -> list[dict[str, Any]]:
    """Parts strictly before this range, in chapter order.

    Strictly before, so re-running an existing range does not feed a part its own
    summary — which would tell the writer the chapter it is about to write has already
    been seen.
    """
    start, _end = parse_range(chapters)
    earlier = [p for p in load_parts(series_slug) if int(p.get("end", 0)) < start]
    return sorted(earlier, key=lambda p: int(p.get("start", 0)))


def record_part(series_slug: str, chapters: str, summary: str, slug: str = "") -> None:
    """Store what a finished part covered. Re-recording a range replaces it."""
    start, end = parse_range(chapters)
    paths = _paths(series_slug)
    paths["series_dir"].mkdir(parents=True, exist_ok=True)
    parts = [p for p in load_parts(series_slug) if p.get("chapters") != chapters]
    parts.append({
        "chapters": chapters,
        "start": start,
        "end": end,
        "slug": slug,
        "summary": (summary or "").strip(),
    })
    parts.sort(key=lambda p: int(p.get("start", 0)))
    paths["story_so_far"].write_text(
        json.dumps({"parts": parts}, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def story_so_far_prompt(series_slug: str, chapters: str) -> str:
    """The block handed to the writer, or "" when this is the first part.

    Phrased as what the VIEWER knows rather than what happened, because that is the
    decision the writer has to make with it: do not re-introduce these people, do not
    re-explain the premise, continue.
    """
    parts = preceding_parts(series_slug, chapters)
    if not parts:
        return ""
    lines = [
        "STORY SO FAR — the viewer has already watched these parts. Do NOT re-introduce",
        "the characters or re-explain the premise. Continue from here; you may refer back",
        "to these events, but never recap them at length.",
        "",
    ]
    for part in parts:
        if part.get("summary"):
            lines.append(f"Chapters {part['chapters']}: {part['summary']}")
    return "\n".join(lines).strip()

def summarise_narration(text: str, max_words: int = 160) -> str:
    """A digest of a finished part, built from the narration itself.

    Deterministic on purpose. An LLM summary would need a mock branch (a prompt without
    one silently returns boilerplate, and this project has shipped that bug), would cost
    a call per part, and would be one more thing that can drift. The opening sentence of
    each beat is already the beat's topic sentence — the writer put it there — so
    stitching them is a faithful spine that a person can read and correct.
    """
    from manhwa2vid.script.freeform import paragraphs
    from manhwa2vid.script.sentences import split_sentences

    heads = []
    for para in paragraphs(text):
        # Defensive: callers pass the freeform prose, but a markdown draft has headings
        # and panel-id comments that are not narration and must never reach a summary.
        body = " ".join(
            ln for ln in para.splitlines()
            if not ln.lstrip().startswith(("#", "<!--", "**", "---"))
        ).strip()
        if not body or "subscri" in body.lower():   # the outro is an ask, not an event
            continue
        sentences = split_sentences(body)
        if sentences:
            heads.append(sentences[0].strip())
    out, used = [], 0
    for head in heads:
        n = len(head.split())
        if used + n > max_words:
            break
        out.append(head)
        used += n
    return " ".join(out)

