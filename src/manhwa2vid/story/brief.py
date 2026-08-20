"""The series brief-read pass: skim many chapters once, before writing any of them.

A human narrator reads the whole story first and then narrates each chapter with that
knowledge; the intro gets written last, from everything read. This stage is that first
read. Per chapter it makes ONE cheap vision call over a stride-sample of source pages
and stores a gist — summary, key events, world facts, cliffhanger, hook moments — in
`series/story_map.json`. Script generation then knows the story BEHIND the current
chapter (better continuity than approved-script scraps) and AHEAD of it (the way the
reference channel pulls world mechanics backward to make an arc legible).

Scope is a researched sweet spot, not everything on disk: manhwa arcs run ~10-15
chapters and premise/trajectory are set by the end of arc two, so the dense read covers
the first `story.dense_chapters` (default 24) plus a `story.rolling_ahead` window
(default 12, ~one arc) past the current project's range. The binding cost is prompt
size downstream, not API calls — dozens of summaries would dilute the writer's
attention on the chapter it is actually narrating.

Everything is cached per chapter; nothing is ever read twice unless --force.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.characters.scout import _ingest_scout_page
from manhwa2vid.config import find_repo_root, get_nested
from manhwa2vid.ingest.images import (
    discover_chapter_dirs,
    iter_image_files,
    parse_chapter_range,
)
from manhwa2vid.llm.provider import apply_stage_model, get_stage_llm
from manhwa2vid.models import ProjectMeta, SourceType, series_paths

console = Console()

_STORY_PROMPT = """You are building a series story map by skimming one chapter of a manhwa.
You see a stride-sample of this chapter's pages — enough for the gist, not every panel.

Return ONE JSON object:
{
  "summary": "what happens in this chapter, 2-4 sentences, concrete events in order",
  "key_events": ["the 2-5 events that matter to the larger story"],
  "characters_introduced": [{"name": "name if shown, else a stable visual label", "role": "one clause"}],
  "world_facts": ["rules/mechanics of this world stated or shown here (system messages, rank rules, geography)"],
  "cliffhanger": "what the chapter ends on, one sentence — empty string if it just stops",
  "hook_moments": ["1-3 moments from THIS chapter striking enough to open a recap video with"]
}

Report only what these pages support. Unreadable or ambiguous content is omitted, never guessed."""


def load_story_map(series_slug: str) -> dict[str, Any]:
    paths = series_paths(find_repo_root(), series_slug)
    path = paths.get("story_map")
    if path is None or not path.exists():
        return {"chapters": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"chapters": {}}
    if not isinstance(data.get("chapters"), dict):
        data["chapters"] = {}
    return data


def _target_chapters(meta: ProjectMeta, available: list[int], config: dict[str, Any]) -> list[int]:
    """Which chapters this pass should have read, intersected with what exists."""
    dense = int(get_nested(config, "story", "dense_chapters", default=24))
    ahead = int(get_nested(config, "story", "rolling_ahead", default=12))
    start, end = parse_chapter_range(meta.chapters)
    want: set[int] = set(range(0, dense + 1))            # 0 included: prologue chapters exist
    want |= set(range(start, end + 1))                    # the project's own range, always
    want |= set(range(end + 1, end + ahead + 1))          # one arc of forward knowledge
    return sorted(n for n in available if n in want)


def run_story_pass(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    series = series_paths(find_repo_root(), meta.series_slug)
    map_path = series["story_map"]
    story_map = {"chapters": {}} if force else load_story_map(meta.series_slug)

    if meta.source_type != SourceType.IMAGES or not meta.source_path:
        console.print("[yellow]Story pass needs an image source — skipping[/]")
        return story_map

    root = Path(meta.source_path)
    try:
        chapter_dirs = dict(discover_chapter_dirs(root, "0-99999"))
    except FileNotFoundError:
        console.print("[yellow]No chapter folders found — story pass skipped[/]")
        return story_map

    targets = _target_chapters(meta, sorted(chapter_dirs), config)
    todo = [n for n in targets if str(n) not in story_map["chapters"]]
    if not todo:
        console.print(
            f"[dim]Story map current — {len(story_map['chapters'])} chapter(s) read, nothing new[/]"
        )
        return story_map

    pages_per = int(get_nested(config, "story", "pages_per_chapter", default=12))
    page_width = int(get_nested(config, "ingest", "page_width", default=1080))
    llm = apply_stage_model(get_stage_llm("scene", config), "scene", config)

    series["scout_dir"].mkdir(parents=True, exist_ok=True)
    for n in todo:
        files = iter_image_files(chapter_dirs[n])
        if not files:
            continue
        stride = max(1, len(files) // pages_per)
        sampled = files[::stride][:pages_per]
        cache_dir = series["scout_dir"] / f"ch{n:02d}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        local = [_ingest_scout_page(f, cache_dir, page_width) for f in sampled]
        try:
            raw = llm.describe_panels(local, _STORY_PROMPT)
            from manhwa2vid.llm.provider import _extract_json_object

            data = json.loads(_extract_json_object(raw))
        except Exception as exc:
            console.print(f"[yellow]Story read failed for ch{n} ({type(exc).__name__}) — skipping[/]")
            continue
        entry = {
            "summary": " ".join(str(data.get("summary", "")).split()),
            "key_events": [str(x) for x in data.get("key_events", []) if str(x).strip()][:6],
            "characters_introduced": [
                c for c in data.get("characters_introduced", []) if isinstance(c, dict)
            ][:8],
            "world_facts": [str(x) for x in data.get("world_facts", []) if str(x).strip()][:6],
            "cliffhanger": " ".join(str(data.get("cliffhanger", "")).split()),
            "hook_moments": [str(x) for x in data.get("hook_moments", []) if str(x).strip()][:3],
            "pages_sampled": len(local),
        }
        story_map["chapters"][str(n)] = entry
        console.print(f"[dim]Story ch{n}:[/] {entry['summary'][:90]}")
        map_path.parent.mkdir(parents=True, exist_ok=True)
        map_path.write_text(json.dumps(story_map, indent=2), encoding="utf-8")

    console.print(
        f"[green]Story pass complete[/] — {len(story_map['chapters'])} chapter(s) in the map "
        f"({len(todo)} new)"
    )
    return story_map


def story_so_far_from_map(story_map: dict[str, Any], meta: ProjectMeta) -> dict[str, str]:
    """chapter -> summary for chapters strictly BEFORE the current range."""
    start, _end = parse_chapter_range(meta.chapters)
    out: dict[str, str] = {}
    for key, entry in story_map.get("chapters", {}).items():
        try:
            n = int(key)
        except ValueError:
            continue
        if n < start and entry.get("summary"):
            out[key] = entry["summary"]
    return out


def story_ahead_from_map(story_map: dict[str, Any], meta: ProjectMeta) -> str:
    """Compact forward knowledge for chapters AFTER the current range.

    Summaries and world facts only — the writer may use these to clarify MECHANICS and
    keep naming/emphasis consistent with where the story goes, never to reveal future
    plot events. That distinction is what separates the reference channel's craft
    (pulling "stats reset, every floor gives a boost" backward) from spoiling.
    """
    _start, end = parse_chapter_range(meta.chapters)
    lines: list[str] = []
    for key in sorted(story_map.get("chapters", {}), key=lambda k: int(k) if k.isdigit() else 0):
        try:
            n = int(key)
        except ValueError:
            continue
        if n <= end:
            continue
        entry = story_map["chapters"][key]
        facts = "; ".join(entry.get("world_facts", [])[:3])
        line = f"Ch {n}: {entry.get('summary', '')}"
        if facts:
            line += f" [world: {facts}]"
        lines.append(line)
    return "\n".join(lines[:12])
