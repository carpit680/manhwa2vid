"""Chapter-ahead panel scouting for character enrichment."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from PIL import Image
from rich.console import Console
from rich.progress import Progress

from manhwa2vid.characters.bible import load_series_bible, merge_profile, save_series_bible
from manhwa2vid.characters.consolidate import consolidate_profiles
from manhwa2vid.characters.quest import run_character_quest
from manhwa2vid.characters.resolve import resolve_character_ref
from manhwa2vid.characters.wiki import fetch_wiki_cast, wiki_protagonist_hint
from manhwa2vid.config import find_repo_root, get_nested, load_config
from manhwa2vid.ingest.images import discover_chapter_dirs, iter_image_files, parse_chapter_range
from manhwa2vid.llm.provider import get_llm_provider
from manhwa2vid.models import (
    CharacterProfile,
    CharacterTier,
    ProjectMeta,
    SeriesBible,
    SourceType,
    save_json,
    series_paths,
)

console = Console()

_SCOUT_VISION_PROMPT = """Identify people in this manhwa panel sample.
Return JSON:
{
  "people": [{"name_used": "", "descriptor": "", "visibility": "face|back_turned|partial"}],
  "speakers": [],
  "hair": "",
  "outfit": "",
  "build": "",
  "key_terms": []
}
Never use the word 'character'. Use names, roles, or visual descriptors."""


def _lookahead_range(chapters: str, lookahead: int) -> str:
    start, end = parse_chapter_range(chapters)
    return f"{end + 1}-{end + lookahead}"


def _sample_image_paths(chapter_dir: Path, max_panels: int) -> list[Path]:
    images = iter_image_files(chapter_dir)
    if not images:
        return []
    if len(images) <= max_panels:
        return images
    step = max(1, len(images) // max_panels)
    sampled = [images[0], *images[1::step]]
    return sampled[:max_panels]


def _ingest_scout_page(image_path: Path, dest: Path, page_width: int) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        if img.width > page_width:
            ratio = page_width / img.width
            img = img.resize((page_width, int(img.height * ratio)), Image.Resampling.LANCZOS)
        out = dest / image_path.name
        img.save(out, quality=92)
        return out


def _vision_scout_panel(llm: Any, panel_path: Path, chapter: int) -> dict[str, Any]:
    try:
        raw = llm.describe_panels([panel_path], _SCOUT_VISION_PROMPT)
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"people": [], "speakers": [], "key_terms": []}
    except Exception as exc:
        console.print(f"[yellow]Scout vision skipped for {panel_path.name}:[/] {type(exc).__name__}")
        data = {"people": [], "speakers": [], "key_terms": []}
    data["chapter"] = chapter
    data["panel_path"] = str(panel_path)
    return data


def _merge_scout_into_bible(bible: SeriesBible, sample: dict[str, Any], chapter: int) -> None:
    for person in sample.get("people", []):
        if not isinstance(person, dict):
            continue
        name = str(person.get("name_used", "")).strip()
        descriptor = str(person.get("descriptor", "")).strip()
        if not name and not descriptor:
            continue
        char_id = resolve_character_ref(name, descriptor, bible)
        if char_id and char_id in bible.characters:
            existing = bible.characters[char_id]
            merge_profile(
                bible,
                CharacterProfile(
                    id=char_id,
                    canonical_name=existing.canonical_name,
                    tier=existing.tier,
                    aliases=list(dict.fromkeys([*existing.aliases, name])) if name else existing.aliases,
                    descriptors=list(dict.fromkeys([*existing.descriptors, descriptor])) if descriptor else existing.descriptors,
                    pronoun=existing.pronoun,
                    role=existing.role,
                    first_seen_panel=existing.first_seen_panel,
                    appearances=existing.appearances,
                    visual=existing.visual,
                    source_chapters=list(dict.fromkeys([*existing.source_chapters, chapter])),
                    confidence=max(existing.confidence, 0.5),
                ),
            )
            continue
        from manhwa2vid.characters.bible import slugify_char_id

        label = name or descriptor
        new_id = slugify_char_id(label)
        merge_profile(
            bible,
            CharacterProfile(
                id=new_id,
                canonical_name=name or descriptor,
                tier=CharacterTier.MINOR,
                descriptors=[descriptor] if descriptor else [],
                pronoun="he",
                source_chapters=[chapter],
                confidence=0.4,
                sufficiency="pending",
            ),
        )

    for speaker in sample.get("speakers", []):
        if not speaker:
            continue
        char_id = resolve_character_ref(str(speaker), "", bible)
        if not char_id:
            from manhwa2vid.characters.bible import slugify_char_id

            char_id = slugify_char_id(str(speaker))
            merge_profile(
                bible,
                CharacterProfile(
                    id=char_id,
                    canonical_name=str(speaker),
                    tier=CharacterTier.SUPPORTING,
                    pronoun="he",
                    source_chapters=[chapter],
                    confidence=0.5,
                    sufficiency="pending",
                ),
            )


def run_character_scout(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> SeriesBible:
    spaths = series_paths(find_repo_root(), meta.series_slug)
    if spaths["scout_manifest"].exists() and not force:
        bible = load_series_bible(meta.series_slug, meta.title)
        if bible.quest_completed:
            console.print("[dim]Using cached scout + quest results[/]")
            return bible

    bible = load_series_bible(meta.series_slug, meta.title)
    glossary = json.loads(paths["glossary"].read_text(encoding="utf-8")) if paths["glossary"].exists() else {}

    wiki_profiles = fetch_wiki_cast(meta.title, config)
    wiki_mc_id = wiki_protagonist_hint(wiki_profiles)
    for wp in wiki_profiles:
        merge_profile(bible, wp)

    lookahead = int(get_nested(config, "characters", "lookahead_chapters", default=3))
    panels_per_ch = int(get_nested(config, "characters", "scout_panels_per_chapter", default=20))
    page_width = int(get_nested(config, "ingest", "page_width", default=1080))

    samples: list[dict[str, Any]] = []
    scout_manifest: dict[str, Any] = {"chapters": [], "samples": []}

    if meta.source_type == SourceType.IMAGES and meta.source_path:
        source_root = Path(meta.source_path)
        try:
            la_range = _lookahead_range(meta.chapters, lookahead)
            chapter_dirs = discover_chapter_dirs(source_root, la_range)
        except FileNotFoundError:
            console.print(f"[yellow]No lookahead chapters found for range {la_range}[/]")
            chapter_dirs = []

        llm = get_llm_provider(config=config)
        vision_model = get_nested(config, "scene", "model") or get_nested(config, "llm", "groq", "vision_model")
        if vision_model and hasattr(llm, "vision_model"):
            llm.vision_model = vision_model

        for chapter_num, chapter_dir in chapter_dirs:
            scout_ch_dir = spaths["scout_dir"] / f"ch{chapter_num:02d}"
            scout_ch_dir.mkdir(parents=True, exist_ok=True)
            image_paths = _sample_image_paths(chapter_dir, panels_per_ch)
            scout_manifest["chapters"].append(chapter_num)

            with Progress() as progress:
                task = progress.add_task(f"Scout ch{chapter_num}", total=len(image_paths))
                for image_path in image_paths:
                    cached = _ingest_scout_page(image_path, scout_ch_dir, page_width)
                    sample = _vision_scout_panel(llm, cached, chapter_num)
                    samples.append(sample)
                    _merge_scout_into_bible(bible, sample, chapter_num)
                    progress.advance(task)
                    time.sleep(0.25)

    scout_manifest["samples"] = samples
    save_json(spaths["scout_manifest"], scout_manifest)
    save_series_bible(bible)

    scene_cards: list = []
    ocr_path = paths["ocr_json"] if paths["ocr_json"].exists() else None
    if paths["scene_json"].exists():
        from manhwa2vid.models import SceneCard

        scene_cards = [SceneCard.model_validate(s) for s in json.loads(paths["scene_json"].read_text())]

    consolidate_profiles(bible, config)
    bible = run_character_quest(
        bible,
        meta,
        config,
        glossary=glossary,
        scene_cards=scene_cards,
        ocr_path=ocr_path,
        wiki_mc_id=wiki_mc_id,
    )
    consolidate_profiles(bible, config)
    save_series_bible(bible)

    console.print(
        f"[green]Scout complete[/] — {len(samples)} panel samples, "
        f"protagonist={bible.protagonist_id or 'pending'}"
    )
    return bible
