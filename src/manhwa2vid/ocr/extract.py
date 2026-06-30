"""OCR extraction and scene card generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress

from manhwa2vid.characters.bible import load_series_bible, save_series_bible
from manhwa2vid.characters.cast_state import format_cast_context, update_bible_from_scene
from manhwa2vid.characters.seed import seed_series_bible
from manhwa2vid.config import get_nested, load_config
from manhwa2vid.llm.provider import get_llm_provider
from manhwa2vid.models import (
    CharacterRef,
    OCRLine,
    Panel,
    PanelOCR,
    ProjectMeta,
    SceneCard,
    SourceLanguage,
    save_json,
)
from manhwa2vid.panels.filter import apply_panel_filter
from manhwa2vid.translate.ko_en import translate_ko_en

console = Console()

_ocr_engine: Any | bool | None = None
_ocr_warning_shown = False


def _get_ocr_engine(source_lang: SourceLanguage) -> Any | None:
    global _ocr_engine
    if _ocr_engine is False:
        return None
    if _ocr_engine is not None and _ocr_engine is not False:
        return _ocr_engine

    config = load_config()
    if not get_nested(config, "ocr", "enabled", default=False):
        _ocr_engine = False
        return None

    try:
        from paddleocr import PaddleOCR

        lang = "korean" if source_lang == SourceLanguage.KO else "en"
        _ocr_engine = PaddleOCR(lang=lang)
        return _ocr_engine
    except Exception as exc:
        console.print(
            f"[yellow]OCR unavailable ({type(exc).__name__}) — "
            "vision LLM will analyze panels without OCR text.[/]"
        )
        _ocr_engine = False
        return None


def _ocr_panel_simple(panel_id: str) -> PanelOCR:
    return PanelOCR(panel_id=panel_id, lines=[], full_text="")


def _parse_ocr_result(result: Any, confidence_threshold: float) -> tuple[list[OCRLine], list[str]]:
    lines: list[OCRLine] = []
    texts: list[str] = []
    if not result:
        return lines, texts

    # PaddleOCR 2.x: [[[bbox], (text, conf)], ...]
    # PaddleOCR 3.x: may return dict or nested structures
    items = result[0] if isinstance(result, list) and result and isinstance(result[0], list) else result
    if isinstance(items, dict):
        rec_texts = items.get("rec_texts") or items.get("texts") or []
        rec_scores = items.get("rec_scores") or items.get("scores") or [1.0] * len(rec_texts)
        for text, conf in zip(rec_texts, rec_scores):
            if float(conf) >= confidence_threshold and str(text).strip():
                lines.append(OCRLine(text=str(text).strip(), confidence=float(conf)))
                texts.append(str(text).strip())
        return lines, texts

    if not isinstance(items, list):
        return lines, texts

    for item in items:
        try:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                bbox, text_part = item[0], item[1]
                if isinstance(text_part, (list, tuple)) and len(text_part) >= 2:
                    text, conf = text_part[0], text_part[1]
                else:
                    text, conf = str(text_part), 1.0
                if float(conf) >= confidence_threshold and str(text).strip():
                    flat_bbox = [int(c) for pt in bbox for c in pt] if bbox else []
                    lines.append(
                        OCRLine(text=str(text).strip(), confidence=float(conf), bbox=flat_bbox)
                    )
                    texts.append(str(text).strip())
        except (TypeError, ValueError):
            continue
    return lines, texts


def ocr_panel(
    panel: Panel,
    project_root: Path,
    confidence_threshold: float,
    source_lang: SourceLanguage,
) -> PanelOCR:
    global _ocr_warning_shown
    engine = _get_ocr_engine(source_lang)
    if engine is None:
        if not _ocr_warning_shown:
            console.print(
                "[dim]Skipping OCR — Groq vision will read panels directly.[/]"
            )
            _ocr_warning_shown = True
        return _ocr_panel_simple(panel.id)

    image_path = project_root / panel.image_path
    try:
        result = engine.ocr(str(image_path))
    except Exception as exc:
        global _ocr_engine
        if not _ocr_warning_shown:
            console.print(f"[yellow]OCR disabled after error: {type(exc).__name__}[/]")
            _ocr_warning_shown = True
        _ocr_engine = False
        return _ocr_panel_simple(panel.id)

    lines, texts = _parse_ocr_result(result, confidence_threshold)
    return PanelOCR(panel_id=panel.id, lines=lines, full_text="\n".join(texts))


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v)
    return str(value)


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_people(value: Any) -> list[CharacterRef]:
    if not value:
        return []
    if not isinstance(value, list):
        return []
    people: list[CharacterRef] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        people.append(
            CharacterRef(
                ref=str(item.get("ref", "new")),
                name_used=str(item.get("name_used", "")),
                descriptor=str(item.get("descriptor", "")),
                visibility=str(item.get("visibility", "face")),
                notes=str(item.get("notes", "")),
            )
        )
    return people


def _sanitize_scene_text(text: str) -> str:
    import re

    if not text:
        return text
    cleaned = text
    cleaned = re.sub(r"\bunnamed characters?\b", "someone", cleaned, flags=re.I)
    cleaned = re.sub(r"\bunnamed\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\btwo characters\b", "two people", cleaned, flags=re.I)
    cleaned = re.sub(r"\ba character\b", "someone", cleaned, flags=re.I)
    cleaned = re.sub(r"\bthe character\b", "they", cleaned, flags=re.I)
    cleaned = re.sub(r"\bcharacters\b", "people", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _normalize_scene_data(data: dict[str, Any], batch: list[Panel]) -> dict[str, Any]:
    is_story = data.get("is_story", True)
    if isinstance(is_story, str):
        is_story = is_story.strip().lower() in ("true", "yes", "1", "story")
    panel_type = _as_str(data.get("panel_type", "story")).strip().lower() or "story"
    if panel_type in ("title_splash", "credit", "ad", "other"):
        is_story = False
    speakers = [
        s
        for s in _as_str_list(data.get("speakers"))
        if s.lower() not in ("unknown", "unnamed", "unnamed character", "unnamed characters")
    ]
    return {
        "panel_ids": _as_str_list(data.get("panel_ids")) or [p.id for p in batch],
        "speakers": speakers,
        "dialogue_summary": _sanitize_scene_text(_as_str(data.get("dialogue_summary"))),
        "action": _sanitize_scene_text(_as_str(data.get("action"))),
        "mood": _as_str(data.get("mood")),
        "key_terms": _as_str_list(data.get("key_terms")),
        "is_story": bool(is_story),
        "exclude_reason": _as_str(data.get("exclude_reason")),
        "panel_type": panel_type,
        "people": _normalize_people(data.get("people")),
    }


def _batch_panels(panels: list[Panel], batch_size: int = 3) -> list[list[Panel]]:
    batches: list[list[Panel]] = []
    for i in range(0, len(panels), batch_size):
        batches.append(panels[i : i + batch_size])
    return batches


def _build_scene_prompt(
    batch: list[Panel],
    ocr_map: dict[str, PanelOCR],
    glossary: dict,
    cast_context: str,
) -> str:
    ocr_block = []
    for p in batch:
        ocr = ocr_map.get(p.id)
        text = ocr.full_text if ocr else ""
        ocr_block.append(f"{p.id}: {text[:500]}")
    glossary_text = json.dumps(glossary, ensure_ascii=False)
    panel_ids = [p.id for p in batch]
    return (
        "Analyze this manhwa panel and return JSON with keys: "
        "people (list of {ref, name_used, descriptor, visibility, notes}), "
        "speakers (list), dialogue_summary, action, mood, key_terms (list), panel_ids, "
        "panel_type (story | title_splash | credit | ad | other), "
        "is_story (boolean), exclude_reason (string, empty if is_story is true).\n"
        "CRITICAL naming rules for action and dialogue_summary:\n"
        "- NEVER write 'a character', 'two characters', 'unnamed character', or 'the character'\n"
        "- Use canonical names, role descriptors (the E-Rank hunter), or visual tags (guy in green backpack)\n"
        "- For people[]: ref=known char_id from cast OR ref='new' with descriptor; visibility=face|back_turned|partial|crowd\n"
        "panel_type=title_splash: large decorative/Korean chapter title, no plot.\n"
        "Set is_story=false for title_splash, credit, ad, or non-plot images.\n"
        f"{cast_context}\n"
        f"Panel IDs: {panel_ids}\n"
        f"OCR text:\n" + "\n".join(ocr_block) + "\n"
        f"Glossary: {glossary_text}"
    )


def run_ocr_and_scenes(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> tuple[list[PanelOCR], list[SceneCard]]:
    if paths["ocr_json"].exists() and paths["scene_json"].exists() and not force:
        ocr_data = json.loads(paths["ocr_json"].read_text(encoding="utf-8"))
        scene_data = json.loads(paths["scene_json"].read_text(encoding="utf-8"))
        console.print("[dim]Using cached OCR and scene cards[/]")
        ocr_results = [PanelOCR.model_validate(o) for o in ocr_data]
        scene_cards = [SceneCard.model_validate(s) for s in scene_data]
        if not paths["panels_story_json"].exists():
            panels = [Panel.model_validate(p) for p in json.loads(paths["panels_json"].read_text())]
            apply_panel_filter(paths, panels, scene_cards, config)
        return ocr_results, scene_cards

    paths["scene_normalized_json"].unlink(missing_ok=True)
    paths["scene_enriched_json"].unlink(missing_ok=True)
    paths["cast_attribution_json"].unlink(missing_ok=True)
    paths["panels_story_json"].unlink(missing_ok=True)
    paths["excluded_panels_json"].unlink(missing_ok=True)

    seed_series_bible(meta, paths["glossary"], config)
    bible = load_series_bible(meta.series_slug, meta.title)

    panels = [Panel.model_validate(p) for p in json.loads(paths["panels_json"].read_text())]
    threshold = float(get_nested(config, "ocr", "confidence_threshold", default=0.5))
    glossary = json.loads(paths["glossary"].read_text()) if paths["glossary"].exists() else {}

    ocr_results: list[PanelOCR] = []
    with Progress() as progress:
        task = progress.add_task("OCR panels", total=len(panels))
        for panel in panels:
            ocr = ocr_panel(panel, paths["root"], threshold, meta.source_lang)
            if meta.source_lang == SourceLanguage.KO and ocr.full_text:
                ocr.translated_text = translate_ko_en(ocr.full_text)
            elif ocr.full_text:
                ocr.translated_text = ocr.full_text
            ocr_results.append(ocr)
            progress.advance(task)

    save_json(paths["ocr_json"], ocr_results)
    ocr_map = {o.panel_id: o for o in ocr_results}

    llm = get_llm_provider(config=config)
    console.print(f"[dim]Scene LLM:[/] {type(llm).__name__}")
    vision_model = get_nested(config, "scene", "model") or get_nested(
        config, "llm", "groq", "vision_model"
    )
    if vision_model and hasattr(llm, "vision_model"):
        llm.vision_model = vision_model

    scene_cards: list[SceneCard] = []
    batch_size = int(get_nested(config, "scene", "batch_size", default=1))
    batches = _batch_panels(panels, batch_size=batch_size)
    recent_cards: list[SceneCard] = []

    with Progress() as progress:
        task = progress.add_task("Scene analysis", total=len(batches))
        for batch in batches:
            image_paths = [paths["root"] / p.image_path for p in batch]
            cast_context = format_cast_context(bible, recent_cards)
            prompt = _build_scene_prompt(batch, ocr_map, glossary, cast_context)
            raw = llm.describe_panels(image_paths, prompt)
            try:
                data = _normalize_scene_data(json.loads(raw), batch)
            except json.JSONDecodeError:
                data = _normalize_scene_data(
                    {
                        "speakers": [],
                        "people": [],
                        "dialogue_summary": raw[:300],
                        "action": "",
                        "mood": "unknown",
                        "key_terms": [],
                        "panel_ids": [p.id for p in batch],
                    },
                    batch,
                )
            source_text = " | ".join(
                ocr_map[p.id].translated_text or ocr_map[p.id].full_text for p in batch if p.id in ocr_map
            )
            card = SceneCard(
                panel_ids=data["panel_ids"],
                speakers=data["speakers"],
                dialogue_summary=data["dialogue_summary"],
                action=data["action"],
                mood=data["mood"],
                key_terms=data["key_terms"],
                source_text=source_text,
                is_story=data["is_story"],
                exclude_reason=data["exclude_reason"],
                panel_type=data["panel_type"],
                people=data["people"],
            )
            panel_id = batch[0].id
            update_bible_from_scene(bible, card, panel_id)
            save_series_bible(bible)
            scene_cards.append(card)
            recent_cards.append(card)
            progress.advance(task)

    save_json(paths["scene_json"], scene_cards)
    apply_panel_filter(paths, panels, scene_cards, config)
    console.print(f"[green]OCR:[/] {len(ocr_results)} panels, [green]scenes:[/] {len(scene_cards)} cards")
    return ocr_results, scene_cards
