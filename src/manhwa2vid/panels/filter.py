"""Exclude non-story panels (ads, credits, posters, scanlation pages)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.models import Panel, SceneCard, save_json

console = Console()

_FILENAME_EXCLUDE_RE = re.compile(
    r"(thanks|credit|credits|poster|cover|advert|promo|patreon|discord|"
    r"donate|support|banner|meraki|jaimini|raw|preview|extra|omake|"
    r"notice|announcement|info|faq|help)",
    re.IGNORECASE,
)


def _source_path_for_panel(panel: Panel, sources: list[dict[str, Any]]) -> str:
    for row in sources:
        if int(row.get("page_num", -1)) == panel.page_num:
            return str(row.get("source_path", ""))
    return ""


_CREDIT_TERMS_RE = re.compile(
    r"(meraki|jaimini|scan\s*group|scanlation|discord\.gg|patreon|"
    r"join\s+our\s+discord|visit\s+our\s+site|thank\s+you\s+for\s+reading)",
    re.IGNORECASE,
)

_NON_STORY_ACTION_RE = re.compile(
    r"^(none|no specific action|no action|n/?a\.?|informative|promotional).*$",
    re.IGNORECASE,
)

_TITLE_SPLASH_RE = re.compile(
    r"(title\s*splash|chapter\s*title|title\s*page|cover\s*page|"
    r"large\s*(korean|stylized)\s*text|decorative\s*title|splash\s*page)",
    re.IGNORECASE,
)

_EXCLUDED_PANEL_TYPES = frozenset({"title_splash", "credit", "ad", "other"})


def exclude_by_scene_content(card: SceneCard, panel: Panel | None = None) -> str | None:
    if card.panel_type in _EXCLUDED_PANEL_TYPES:
        label = card.panel_type.replace("_", " ")
        return card.exclude_reason or f"{label} panel"

    if not card.is_story:
        return card.exclude_reason or "non-story panel (vision)"

    blob = " ".join(
        [
            card.dialogue_summary,
            card.action,
            card.mood,
            " ".join(card.speakers),
            " ".join(card.key_terms),
        ]
    )
    if not _CREDIT_TERMS_RE.search(blob):
        return None
    if _NON_STORY_ACTION_RE.match(card.action.strip()) or not card.dialogue_summary.strip():
        return "scanlation credits or promo page"

    if panel and not card.speakers:
        blob_lower = blob.lower()
        if _TITLE_SPLASH_RE.search(blob_lower) and card.panel_type == "title_splash":
            return "chapter title splash"

    return None


def exclude_by_filename(source_path: str) -> str | None:
    name = Path(source_path).name
    if _FILENAME_EXCLUDE_RE.search(name):
        return f"filename match: {name}"
    return None


def is_blank_panel(panel: Panel, config: dict[str, Any]) -> bool:
    """Near-white page-transition sliver, by pixel stats stamped at split time.

    False when stats are absent (pre-change cached panels.json) — apply_panel_filter
    backfills stats before mapping, so builders that call this directly stay pure.
    """
    if not get_nested(config, "panels", "exclude_blank_panels", default=True):
        return False
    if panel.ink_ratio is None or panel.dark_ratio is None:
        return False
    max_ink = float(get_nested(config, "panels", "blank_max_ink_ratio", default=0.30))
    max_dark = float(get_nested(config, "panels", "blank_max_dark_ratio", default=0.10))
    if panel.ink_ratio < max_ink and panel.dark_ratio < max_dark:
        return True
    # The symmetric case: a solid BLACK transition sliver. Dark-page titles separate
    # panels with black bands, and by the ink definition (gray < 245) solid black scores
    # ink = 1.0 — the opposite of what "blank" was tuned for. Pure black is ink ≈ 1.0 AND
    # dark ≈ 1.0 simultaneously; a black CAPTION panel keeps white text pixels, which pull
    # ink measurably below 1.0, so the thresholds sit deliberately high — wrongly keeping
    # a blank sliver costs tokens, wrongly dropping a caption panel loses story.
    return panel.ink_ratio > 0.995 and panel.dark_ratio > 0.995


def build_exclusion_map(
    panels: list[Panel],
    scene_cards: list[SceneCard],
    sources: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, str]:
    """Return panel_id -> exclude reason for panels that should not appear in the video."""
    excluded: dict[str, str] = {}
    use_vision = bool(get_nested(config, "panels", "filter_non_story", default=True))
    use_filename = bool(get_nested(config, "panels", "filter_by_filename", default=True))

    scene_by_panel: dict[str, SceneCard] = {}
    for card in scene_cards:
        for pid in card.panel_ids:
            scene_by_panel[pid] = card

    manual = get_nested(config, "panels", "exclude_panel_ids", default=[]) or []
    for pid in manual:
        excluded[str(pid)] = "manual exclude list"

    for panel in panels:
        if panel.id in excluded:
            continue

        # Pixel rule first: a blank sliver is blank regardless of what any scene card
        # claims about it (a hallucinated card must not rescue an empty image).
        if is_blank_panel(panel, config):
            excluded[panel.id] = "blank transition sliver"
            continue

        if use_filename:
            source_path = _source_path_for_panel(panel, sources)
            reason = exclude_by_filename(source_path) if source_path else None
            if reason:
                excluded[panel.id] = reason
                continue

        if use_vision:
            card = scene_by_panel.get(panel.id)
            if card:
                reason = exclude_by_scene_content(card, panel)
                if reason:
                    excluded[panel.id] = reason

    return excluded


def apply_panel_filter(
    paths: dict[str, Path],
    panels: list[Panel],
    scene_cards: list[SceneCard],
    config: dict[str, Any],
) -> list[Panel]:
    sources: list[dict[str, Any]] = []
    sources_path = paths["pages"] / "sources.json"
    if sources_path.exists():
        sources = json.loads(sources_path.read_text(encoding="utf-8"))

    # Backfill ink stats for panels persisted before stats existed, so the blank rule
    # applies to cached projects without forcing a panels re-run.
    needs_backfill = [
        p for p in panels
        if p.ink_ratio is None or p.dark_ratio is None or p.content_area_ratio is None
    ]
    if needs_backfill:
        from manhwa2vid.models import PanelBBox
        from manhwa2vid.panels.split import content_bbox_from_file, panel_ink_stats_from_file

        for panel in needs_backfill:
            path = paths["root"] / panel.image_path
            stats = panel_ink_stats_from_file(path)
            if stats is not None:
                panel.ink_ratio, panel.dark_ratio = stats
            result = content_bbox_from_file(path)
            if result is not None:
                box, (img_w, img_h) = result
                if box is not None:
                    x, y, w, h = box
                    panel.content_box = PanelBBox(x=x, y=y, width=w, height=h)
                    area = img_w * img_h
                    panel.content_area_ratio = round((w * h) / area, 4) if area else 0.0
                else:
                    # Readable image with zero content: an all-white sliver.
                    panel.content_area_ratio = 0.0
        save_json(paths["panels_json"], panels)

    excluded = build_exclusion_map(panels, scene_cards, sources, config)
    save_json(paths["excluded_panels_json"], excluded)

    active = [p for p in panels if p.id not in excluded]
    if excluded:
        console.print(
            f"[yellow]Excluded {len(excluded)} non-story panel(s):[/] "
            + ", ".join(sorted(excluded.keys()))
        )
    else:
        console.print("[dim]No panels excluded[/]")

    save_json(paths["panels_story_json"], active)
    return active


def load_story_panels(paths: dict[str, Path]) -> list[Panel]:
    if paths["panels_story_json"].exists():
        return [Panel.model_validate(p) for p in json.loads(paths["panels_story_json"].read_text())]
    return [Panel.model_validate(p) for p in json.loads(paths["panels_json"].read_text())]


def apply_corrections(paths: dict[str, Path], cards: list[SceneCard]) -> list[SceneCard]:
    """Overlay human-verified panel facts onto the vision pass's cards.

    Vision is re-run whenever perception changes, and it is non-deterministic: a gesture
    read correctly on one run ("Bak points at Jin-Woo") comes back wrong on the next
    ("Bak gives a thumbs up"). Without this file, every fix the reviewer signs off on is
    a fresh coin-flip on the following run, and the same note gets written twice.

    corrections.json is hand-maintained and authoritative:

        {"panels": {"p0015_01": {"action": "...", "source_text": "...", "note": "why"}}}

    Only the fields present are overridden; "note" is documentation and never reaches a
    prompt. A panel id that no longer exists is ignored rather than raising, so a re-split
    cannot break the build.
    """
    if not paths["corrections_json"].exists():
        return cards
    try:
        data = json.loads(paths["corrections_json"].read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return cards
    by_panel = data.get("panels", {})
    if not isinstance(by_panel, dict) or not by_panel:
        return cards
    fields = {"action", "source_text", "dialogue_summary", "mood"}
    out: list[SceneCard] = []
    for card in cards:
        patch: dict[str, object] = {}
        for pid in card.panel_ids:
            entry = by_panel.get(pid)
            if isinstance(entry, dict):
                patch.update({k: v for k, v in entry.items() if k in fields and isinstance(v, str)})
        out.append(card.model_copy(update=patch) if patch else card)
    return out


def load_story_scene_cards(paths: dict[str, Path]) -> list[SceneCard]:
    source = paths["scene_enriched_json"] if paths["scene_enriched_json"].exists() else paths["scene_json"]
    cards = [SceneCard.model_validate(s) for s in json.loads(source.read_text(encoding="utf-8"))]
    cards = apply_corrections(paths, cards)
    if not paths["excluded_panels_json"].exists():
        return cards
    excluded = set(json.loads(paths["excluded_panels_json"].read_text()).keys())
    filtered: list[SceneCard] = []
    for card in cards:
        story_ids = [pid for pid in card.panel_ids if pid not in excluded]
        if not story_ids:
            continue
        filtered.append(
            SceneCard(
                panel_ids=story_ids,
                speakers=card.speakers,
                dialogue_summary=card.dialogue_summary,
                action=card.action,
                mood=card.mood,
                key_terms=card.key_terms,
                source_text=card.source_text,
                is_story=card.is_story,
                exclude_reason=card.exclude_reason,
                panel_type=card.panel_type,
                people=card.people,
            )
        )
    return filtered
