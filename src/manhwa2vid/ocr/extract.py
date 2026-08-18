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
from manhwa2vid.config import find_repo_root, get_nested, load_config
from manhwa2vid.llm.provider import apply_stage_model, get_stage_llm
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

    import os

    config = load_config()
    if os.getenv("MANHWA2VID_OCR", "") == "0":
        _ocr_engine = False  # test/CI kill-switch — avoids model downloads
        return None
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


# Cross-card self-similarity. Healthy chapters score 0% by this measure (ch1 and ch2 both);
# a chapter whose vision pass collapsed into one repeated description scored ~85%. Every
# other scene gate checks a card against its own panel — none asks whether the cards are
# distinguishable FROM EACH OTHER, so a whole chapter of near-identical cards passed all
# seven gates while being unusable.
_DIVERSITY_SIMILARITY = 0.6   # Jaccard over >3-char tokens: near-duplicate wording
_DIVERSITY_WARN_FRAC = 0.15
_DIVERSITY_FAIL_FRAC = 0.30


def _content_tokens(text: str) -> set[str]:
    import re

    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 3}


def _duplicate_card_ratio(cards: list[SceneCard]) -> tuple[float, list[str]]:
    """Fraction of story cards that have a near-duplicate sibling, plus example panel ids."""
    story = [c for c in cards if c.is_story]
    sigs = [
        (c, _content_tokens(c.action) | _content_tokens(c.dialogue_summary)) for c in story
    ]
    dupes: list[str] = []
    for i, (card, a) in enumerate(sigs):
        if not a:
            continue
        for j, (_other, b) in enumerate(sigs):
            if i == j or not b:
                continue
            overlap = len(a & b) / len(a | b)
            if overlap >= _DIVERSITY_SIMILARITY:
                dupes.append(card.panel_ids[0] if card.panel_ids else "?")
                break
    return (len(dupes) / len(story) if story else 0.0), dupes


def _normalize_bubbles(value: Any) -> tuple[list[str], list[str]]:
    """Returns (verbatim_texts, attributed_lines).

    Speech attribution is decided at PERCEPTION time — bubble tails, gaze and vocatives
    are visible there and nowhere later. Previously only the paraphrase reached the
    writer, so it guessed: one man's line about "MY sick mother's medical bills" became a
    whole crowd's motivation, and "TAKE CARE OF US, MR. SONG CHI-YUL" was narrated as
    Jin-Woo addressing someone else entirely.

    Accepts the attributed object shape and bare strings alike, so legacy cards and the
    mock keep working.
    """
    texts: list[str] = []
    attributed: list[str] = []
    if not isinstance(value, list):
        return texts, attributed
    for item in value:
        if isinstance(item, str):
            if item.strip():
                texts.append(item.strip())
                attributed.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        texts.append(text)
        speaker = str(item.get("speaker", "")).strip()
        addressee = str(item.get("to", "")).strip()
        if _is_nullish_name(speaker):
            speaker = ""
        if _is_nullish_name(addressee):
            addressee = ""
        if speaker and addressee:
            attributed.append(f'{speaker} -> {addressee}: "{text}"')
        elif speaker:
            attributed.append(f'{speaker}: "{text}"')
        else:
            attributed.append(f'"{text}"')
    return texts, attributed


def _coerce_confidence(value: Any) -> float:
    """Parse the model's self-reported certainty into 0.0-1.0.

    Models return this as a float, a string, or occasionally a percentage ("85%" / 85),
    so normalize all three rather than discarding the signal on a formatting whim.
    """
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 0.0
    try:
        if isinstance(value, str):
            text = value.strip().rstrip("%")
            number = float(text)
            if "%" in value:
                number /= 100.0
        else:
            number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number > 1.0:  # 85 meaning 85%
        number /= 100.0
    return max(0.0, min(1.0, number))


# Serializers stringify null in several dialects, and a vision model asked for a name it
# does not know will happily answer with one of these. Slugified, "None" became char_none —
# a bible profile that then absorbed a pale silhouette, an orange-haired man, and two other
# unrelated people into a single fake identity that passed every downstream id check.
_NULLISH_NAMES = frozenset(
    {"none", "null", "nil", "n/a", "na", "unknown", "unnamed", "undefined", "-", "?"}
)


def _is_nullish_name(value: str) -> bool:
    return value.strip().strip(".").lower() in _NULLISH_NAMES


def _normalize_people(value: Any) -> tuple[list[CharacterRef], int]:
    """Returns (people, demoted_count).

    A named identification (ref != 'new' or a name_used) must carry a `basis` — the
    specific visual evidence in THIS panel. Cast-list priming makes vision models
    distribute known names onto back-turned strangers (four named characters were once
    'identified' in an anonymous crosswalk crowd); an identification that cannot say
    WHY is demoted to an unnamed person rather than trusted.
    """
    if not value or not isinstance(value, list):
        return [], 0
    people: list[CharacterRef] = []
    demoted = 0
    for item in value:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref", "new"))
        name_used = str(item.get("name_used", ""))
        if _is_nullish_name(name_used):
            name_used = ""
        if _is_nullish_name(ref) or _is_nullish_name(ref.removeprefix("char_")):
            ref = "new"
        basis = str(item.get("basis", "")).strip()
        notes = str(item.get("notes", ""))
        confidence = _coerce_confidence(item.get("confidence"))
        visibility = str(item.get("visibility", "face"))
        if (ref != "new" or name_used) and len(basis) < 4:
            ref, name_used = "new", ""
            confidence = 0.0
            demoted += 1
        elif (ref != "new" or name_used) and visibility == "crowd":
            # Nobody is identifiable "in a crowd" by definition — a named crowd figure is
            # roster priming, the same failure that put Lee Joo-hee at a crosswalk she
            # was never in (a back-turned extra "identified" by hair colour alone).
            ref, name_used = "new", ""
            confidence = 0.0
            demoted += 1
        people.append(
            CharacterRef(
                ref=ref,
                name_used=name_used,
                descriptor=str(item.get("descriptor", "")),
                visibility=visibility,
                notes=f"basis: {basis}" if basis else notes,
                confidence=confidence,
            )
        )
    return people, demoted


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


def _speaker_matches_person(speaker: str, person: CharacterRef) -> bool:
    s = speaker.strip().lower()
    if not s:
        return False
    for label in (person.name_used, person.descriptor, person.ref.removeprefix("char_").replace("_", " ")):
        candidate = label.strip().lower()
        if candidate and (s in candidate or candidate in s):
            return True
    return False


_GROUNDING_STOP = frozenset(
    "the a an and or to of in on at for with his her he she they them it is are was were be as by "
    "from that this into about someone people person says asks tells said".split()
)


def _content_words(text: str) -> set[str]:
    import re

    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _GROUNDING_STOP and len(t) > 3}


def _normalize_scene_data(
    data: dict[str, Any],
    batch: list[Panel],
    *,
    ocr_text: str = "",
    known_ids: set[str] | None = None,
) -> dict[str, Any]:
    is_story = data.get("is_story", True)
    if isinstance(is_story, str):
        is_story = is_story.strip().lower() in ("true", "yes", "1", "story")
    panel_type = _as_str(data.get("panel_type", "story")).strip().lower() or "story"
    if panel_type in ("title_splash", "credit", "ad", "other"):
        is_story = False

    people, demoted_identifications = _normalize_people(data.get("people"))
    if known_ids is not None:
        # The VLM may only RESOLVE to ids the bible already holds — asked for
        # "char_id or 'new'" it happily mints descriptor-shaped ids
        # (char_person_with_short_black_hair_...), and seeding those downstream
        # flooded the bible with per-panel junk profiles that drowned the real cast.
        for person in people:
            if person.ref != "new" and person.ref not in known_ids:
                person.ref = "new"
    # Bubbles arrive either as the attributed object shape (current prompt) or as bare
    # strings (legacy cards, the mock, and any provider that ignores the schema). Keep
    # both: `bubbles` stays a list[str] for every existing consumer/gate, while
    # `attributed_lines` carries speaker→addressee for the writer's evidence.
    bubbles, attributed = _normalize_bubbles(data.get("bubbles"))

    # Gate: a speaker must be one of the people visible in this panel. This is where the
    # "Sung Jin-Woo speaks in a panel he is not in" class of hallucination is stopped.
    raw_speakers = [
        s
        for s in _as_str_list(data.get("speakers"))
        if s.lower() not in ("unknown", "unnamed", "unnamed character", "unnamed characters")
    ]
    speakers = [s for s in raw_speakers if any(_speaker_matches_person(s, p) for p in people)]

    # Gate: dialogue claims must be grounded in text we can actually see (OCR + verbatim
    # bubble transcription). A summary whose content words barely overlap the visible text
    # is invented — drop the claim rather than let it poison every later stage.
    dialogue = _sanitize_scene_text(_as_str(data.get("dialogue_summary")))
    visible_blob = " ".join([ocr_text, *bubbles])
    claim_words = _content_words(dialogue)
    if claim_words:
        visible_words = _content_words(visible_blob)
        if not visible_words:
            dialogue = ""  # no visible text at all — nothing to summarize
        elif len(claim_words & visible_words) / len(claim_words) < 0.2:
            dialogue = ""

    # Clamp panel_ids to the batch actually shown: the model echoes ids and an off-by-one
    # echo would strand the real panel with no card while crediting a neighbor.
    batch_ids = [p.id for p in batch]
    batch_id_set = set(batch_ids)
    model_ids = [i for i in _as_str_list(data.get("panel_ids")) if i in batch_id_set]

    return {
        "panel_ids": model_ids or batch_ids,
        "speakers": speakers,
        "dropped_speakers": [s for s in raw_speakers if s not in speakers],
        "demoted_identifications": demoted_identifications,
        "bubbles": bubbles,
        # Must be in the RETURNED dict: this function builds a fresh one, so setting the
        # key on the input silently dropped every speaker/addressee.
        "attributed_lines": attributed,
        "dialogue_summary": dialogue,
        "action": _sanitize_scene_text(_as_str(data.get("action"))),
        "mood": _as_str(data.get("mood")),
        "key_terms": _as_str_list(data.get("key_terms")),
        "is_story": bool(is_story),
        "exclude_reason": _as_str(data.get("exclude_reason")),
        "panel_type": panel_type,
        "people": people,
    }


def demote_unintroduced_back_views(cards: list[SceneCard]) -> int:
    """A character cannot be INTRODUCED from behind. Returns how many were demoted.

    Cards are walked in panel order. The first time a named character appears they must be
    face-on or clearly partial; a back-turned or crowd figure claimed before any face
    sighting is roster priming, not recognition. That is precisely how Lee Joo-hee ended
    up "standing in a crowd" at a crosswalk one scene before she actually appears — a
    back-turned pedestrian matched on hair colour alone at 0.95 confidence, which then
    reached the narration as an introduction.

    Once a character HAS been seen face-on in the chapter, later back views are credible
    (the protagonist is legitimately recognizable from behind by his green backpack), so
    this only rejects the introduction case.
    """
    seen_face: set[str] = set()
    demoted = 0
    for card in sorted(cards, key=lambda c: c.panel_ids[0] if c.panel_ids else ""):
        for person in card.people:
            ref = (person.ref or "").strip()
            if not ref or ref == "new":
                continue
            if person.visibility in ("face", "partial"):
                seen_face.add(ref)
                continue
            if ref not in seen_face:
                person.ref = "new"
                person.name_used = ""
                person.confidence = 0.0
                demoted += 1
    return demoted


def _card_from_entry(
    entry: dict[str, Any],
    panel: Panel,
    pid: str,
    ocr_map: dict[str, PanelOCR],
    known_ids: set[str],
    counters: dict[str, int],
) -> SceneCard:
    """One annotation -> one SceneCard, through the shared normalization.

    Used by both the window path and its single-panel retry so a retried panel gets the
    identical guards (panel-id clamping, off-panel speakers, dialogue grounding,
    basis-required identification, nullish-name rejection).
    """
    ocr = ocr_map.get(pid)
    panel_ocr = (ocr.translated_text or ocr.full_text) if ocr else ""
    entry["panel_ids"] = [pid]
    data = _normalize_scene_data(entry, [panel], ocr_text=panel_ocr, known_ids=known_ids)
    counters["dropped_speakers"] += len(data.get("dropped_speakers", []))
    counters["demoted"] += int(data.get("demoted_identifications", 0))
    if not data["dialogue_summary"] and data.get("bubbles"):
        counters["grounded_from_bubbles"] += 1
    # Prefer the ATTRIBUTED lines in source_text: this is the field the writer's evidence
    # is built from, and "Kim -> Bak: \"...\"" is the difference between a line having an
    # owner and the writer guessing one. Falls back to bare bubbles for legacy shapes.
    spoken = data.get("attributed_lines") or data.get("bubbles", [])
    source_text = " | ".join(filter(None, [panel_ocr.strip(), " / ".join(spoken)]))
    return SceneCard(
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


def _normalize_panel_ref(value: Any, panels: list[Panel]) -> str:
    """Coerce a model-reported panel reference to a real panel id, else "".

    The chapter read answered "11" for present_starts_at_panel — a page number, not an
    id — so the panel-aware lookup silently found no owner. Match exact ids first, then a
    bare page number, and give up honestly rather than half-matching.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    ids = [p.id for p in panels]
    if text in ids:
        return text
    import re as _re

    digits = _re.sub(r"\D", "", text)
    if digits:
        page = int(digits)
        for pid in ids:
            m = _re.match(r"p(\d+)_", pid)
            if m and int(m.group(1)) == page:
                return pid
    return ""


def _run_chapter_scene_pass(
    analysis_panels: list[Panel],
    paths: dict[str, Path],
    ocr_map: dict[str, PanelOCR],
    glossary: dict,
    bible: Any,
    llm: Any,
    config: dict[str, Any],
) -> tuple[list[SceneCard], dict[str, int], dict[str, str]]:
    """Read the chapter whole, then annotate it in small LABELED windows.

    Pass 1 gives the model the thing the per-panel loop destroyed: the chapter as one
    story, so identity is tracked across panels by sight rather than reconstructed from
    prose downstream. Pass 2 annotates in windows whose images carry their panel id
    inline — a single 59-image pass produced correct annotations bound to the wrong ids
    (measured shift of +3), because a model cannot reliably count images. The chapter
    understanding rides along as text, so windows lose nothing but the counting burden.

    Every annotation is pushed through the same `_normalize_scene_data` the per-panel path
    uses, so all existing guards and scene gates apply unchanged.
    """
    window_size = int(get_nested(config, "scene", "chapter_window_panels", default=12))
    if hasattr(llm, "MAX_VISION_TOKENS"):
        llm.MAX_VISION_TOKENS = int(
            get_nested(config, "scene", "chapter_max_output_tokens", default=16384)
        )

    # --- Pass 1: read the whole chapter -------------------------------------------------
    story_map: dict[str, str] = {}
    roster_text = ""
    try:
        raw = llm.describe_panels(
            [paths["root"] / p.image_path for p in analysis_panels],
            _build_chapter_read_prompt(analysis_panels),
        )
        read = json.loads(raw)
        story_map = {
            "summary": str(read.get("summary", "")),
            "temporal_devices": str(read.get("temporal_devices", "")),
            # WHERE the present begins, not just that it does. The rewind line has to be
            # spoken while the transition panel is on screen; announced a beat early it
            # plays over dungeon art, and the panel that actually shows the shift passes
            # in silence.
            # The END of the flashforward, not the start of the present: asked the
            # other way the model named a construction site two beats into the present
            # day, which moved the rewind line after the story had already returned.
            # "Last panel of the opening flashforward" is a boundary it can see.
            "last_flashforward_panel": _normalize_panel_ref(
                read.get("last_flashforward_panel", ""), analysis_panels
            ),
            # Written once, from whole-chapter context, then locked deterministically so
            # the narration pass cannot embellish it. Asking the writer for this line in
            # the same breath as 18 beats produced "Away from the trials of him, the sky
            # clears over the peaceful bridges of present-day Seoul."
            "return_to_present_line": " ".join(
                str(read.get("return_to_present_line", "") or "").split()
            )[:160],
        }
        roster = read.get("roster") or []
        roster_text = "\n".join(
            f"  - {r.get('who','?')}: {r.get('looks','')}"
            for r in roster if isinstance(r, dict)
        )
        console.print(f"[dim]Chapter read:[/] {story_map['summary'][:110]}")
    except Exception as exc:
        console.print(f"[yellow]Chapter read failed ({type(exc).__name__}) — annotating without it[/]")

    # --- Pass 2: annotate in labeled windows --------------------------------------------
    by_id = {p.id: p for p in analysis_panels}
    known_ids = set(bible.characters)
    cards: list[SceneCard] = []
    counters = {"dropped_speakers": 0, "demoted": 0, "grounded_from_bubbles": 0, "missing": 0}
    windows = _chapter_windows(analysis_panels, window_size)

    with Progress() as progress:
        task = progress.add_task("Chapter scene analysis", total=len(windows))
        for window in windows:
            prompt = _build_window_prompt(
                window, ocr_map, glossary,
                format_cast_context(bible, cards[-3:]), story_map, roster_text,
            )
            labeled = [
                (f"PANEL {p.id}:", paths["root"] / p.image_path) for p in window
            ]
            try:
                payload = json.loads(llm.describe_labeled_panels(labeled, prompt))
            except json.JSONDecodeError:
                console.print("[yellow]Window returned unparseable JSON[/]")
                payload = {}

            entries = payload.get("panels")
            entries = entries if isinstance(entries, list) else []
            window_ids = [p.id for p in window]
            seen: set[str] = set()
            for position, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                pid = str(entry.get("panel_id", "")).strip()
                if pid not in by_id:
                    # Unknown id: fall back to this entry's POSITION in the window, which
                    # is the order the labeled images were sent in.
                    pid = window_ids[position] if position < len(window_ids) else ""
                panel = by_id.get(pid)
                if panel is None or pid in seen or pid not in window_ids:
                    continue
                seen.add(pid)
                card = _card_from_entry(
                    entry, panel, pid, ocr_map, known_ids, counters
                )
                update_bible_from_scene(bible, card, pid)
                cards.append(card)

            missing = [pid for pid in window_ids if pid not in seen]
            if missing:
                # A window can come back empty — an empty completion parses to {} and
                # yields zero entries, silently dropping 12 panels (ch2 lost its first
                # 24 that way; only cards-coverage caught it). Retry the stragglers one
                # at a time: a single panel is a smaller, safer request and its id is
                # unambiguous, so partial perception beats none.
                console.print(f"[yellow]Window left {len(missing)} panel(s) — retrying singly[/]")
                for pid in list(missing):
                    panel = by_id.get(pid)
                    if panel is None:
                        continue
                    try:
                        solo = json.loads(
                            llm.describe_labeled_panels(
                                [(f"PANEL {pid}:", paths["root"] / panel.image_path)],
                                _build_window_prompt(
                                    [panel], ocr_map, glossary,
                                    format_cast_context(bible, cards[-3:]),
                                    story_map, roster_text,
                                ),
                            )
                        )
                    except Exception:
                        continue
                    solo_entries = solo.get("panels")
                    entry = None
                    if isinstance(solo_entries, list) and solo_entries:
                        entry = solo_entries[0] if isinstance(solo_entries[0], dict) else None
                    elif isinstance(solo, dict) and solo.get("action"):
                        entry = solo  # some replies answer a single panel unwrapped
                    if not isinstance(entry, dict):
                        continue
                    entry["panel_ids"] = [pid]
                    card = _card_from_entry(
                        entry, panel, pid, ocr_map, known_ids, counters
                    )
                    update_bible_from_scene(bible, card, pid)
                    cards.append(card)
                    seen.add(pid)
                missing = [pid for pid in window_ids if pid not in seen]
            counters["missing"] += len(missing)
            if missing:
                console.print(f"[yellow]Window skipped {len(missing)} panel(s):[/] {missing[:8]}")
            save_json(paths["scene_partial_json"], cards)
            progress.advance(task)

    # A vision pass that produced NOTHING is a failed run, not an empty chapter. Without
    # this the stage returns quietly, downstream reuses whatever is on disk, and every
    # gate reports green on stale artifacts — exactly what three credit-exhausted runs
    # did while reporting EXIT=0.
    if analysis_panels and not cards:
        raise RuntimeError(
            f"Vision pass produced no scene cards for {len(analysis_panels)} panel(s). "
            "The provider returned nothing usable — check credits/quota and re-run; "
            "existing artifacts were left untouched."
        )

    cards.sort(key=lambda c: c.panel_ids[0] if c.panel_ids else "")
    intro_demoted = demote_unintroduced_back_views(cards)
    if intro_demoted:
        counters["demoted"] += intro_demoted
        console.print(
            f"[dim]Demoted {intro_demoted} back-turned/crowd figure(s) claimed before "
            f"their first face-on appearance[/]"
        )
    return cards, counters, story_map


def _build_chapter_read_prompt(panels: list[Panel]) -> str:
    """Pass 1: understand the chapter. No per-panel output, so nothing can misbind."""
    return (
        f"You are reading ONE COMPLETE manhwa chapter: {len(panels)} panels attached in "
        "reading order. Read it as a story before anything is described panel by panel.\n\n"
        "Work out:\n"
        "- what happens, in order, as a connected sequence of events\n"
        "- WHO recurs. Track each person across panels by face, hair, build and clothing. "
        "The same person seen from behind, in shadow, or in a different outfit is still "
        "that person; two people who dress alike are still two people.\n"
        "- any flashforward, flashback or time skip, and where the frame shifts\n\n"
        'Return ONE JSON object:\n'
        '{"summary": "what happens in this chapter, in order", '
        '"temporal_devices": "devices used and where they shift, or empty string", '
        '"last_flashforward_panel": "the id of the LAST panel that still belongs to the '
        'opening flashforward — the final image before the story returns to the present. '
        'A wide establishing shot of the city that follows the flashforward IS the '
        'return, so the panel BEFORE it is the answer. Empty string if the chapter is '
        'strictly chronological", '
        '"return_to_present_line": "ONE short present-tense sentence, in recap-narration '
        'voice, marking the return from that flashforward as an IMAGE CHANGE rather than '
        'an announcement — name the place the story returns to. Empty string if the '
        'chapter is strictly chronological", '
        '"roster": [{"who": "name if the chapter names them, else a stable visual label", '
        '"looks": "the features that identify them across panels", '
        '"first_seen": "roughly where they first appear"}]}'
    )


def _build_window_prompt(
    panels: list[Panel],
    ocr_map: dict[str, PanelOCR],
    glossary: dict,
    cast_context: str,
    story_map: dict[str, str],
    roster_text: str,
) -> str:
    """Pass 2: annotate a small window whose images are LABELED inline.

    Each image is preceded by its own panel id in the message, so the binding is
    positional rather than a count the model has to maintain. Windows stay small for the
    same reason; the chapter-level understanding is carried in as text.
    """
    ocr_lines = []
    for p in panels:
        ocr = ocr_map.get(p.id)
        if ocr and ocr.full_text.strip():
            ocr_lines.append(f"  {p.id}: {ocr.full_text[:300]}")
    ocr_block = "\n".join(ocr_lines) or "  (none — transcribe bubbles yourself)"

    return (
        "You have already read this whole chapter. Here is what you established:\n"
        f"  STORY: {story_map.get('summary', '(none)')}\n"
        f"  TEMPORAL: {story_map.get('temporal_devices', '') or '(strictly chronological)'}\n"
        f"  WHO RECURS:\n{roster_text or '  (none)'}\n\n"
        f"Now annotate ONLY these {len(panels)} panels. Each image below is preceded by a "
        "line naming its panel id — use that id for that image, and annotate each image "
        "from what is in THAT image alone. Knowing the story does not let you describe "
        "events from other panels.\n\n"
        "For each panel return:\n"
        "- bubbles: one object per speech bubble/caption in reading order:\n"
        '    {"text": verbatim words, "speaker": who says it, "to": who they say it to}\n'
        "  Judge speaker from the bubble TAIL (which body it points at) and 'to' from gaze,\n"
        "  body facing, and the words themselves — a vocative ('MR. SONG, ...') names the\n"
        "  listener, 'YOU' addresses whoever the previous line concerned. Use the same\n"
        "  name/descriptor you used in `people`. Leave either field \"\" when the panel does\n"
        "  not show it — an honest blank is far better than a guess, because every later\n"
        "  stage trusts this attribution and cannot re-derive it.\n"
        "  Thought bubbles and narration boxes: speaker = the thinker, to = \"\".\n"
        "- people: every VISIBLE person as {ref, name_used, descriptor, visibility, "
        "basis, confidence}. ref = a char_id from the cast list, or 'new'. visibility = "
        "face|back_turned|partial|crowd. basis = the specific visual evidence IN THIS "
        "PANEL. confidence = 0.0-1.0, below 0.5 when guessing from posture or clothing.\n"
        "IDENTIFICATION DISCIPLINE: the cast roster exists to RESOLVE people you can "
        "already recognize — it is NOT a list of who to expect. Unnamed strangers vastly "
        "outnumber the cast: street crowds, pedestrians and background figures are almost "
        "never cast members. NEVER name a back-turned, partial, or crowd figure from "
        "position or a common trait (hair colour alone is a common trait) — knowing a "
        "cast member is nearby in the story does not put them in this panel. Naming "
        "requires a marker unique to that person. When unsure use ref='new': an unnamed "
        "extra is always correct; a wrongly named one corrupts every later stage.\n"
        "- speakers: which of THIS panel's people speak a bubble here\n"
        "- dialogue_summary: reported speech from this panel's bubbles only\n"
        "- action, mood, key_terms, panel_type (story|title_splash|credit|ad|other), "
        "is_story, exclude_reason\n\n"
        "A panel with no people gets an empty people list — many panels are scenery, "
        "close-ups, or pure effect. Never write 'a character' or 'unnamed character'.\n\n"
        f"{cast_context}\n\n"
        f"OCR already extracted (ground truth where present):\n{ocr_block}\n\n"
        f"Glossary: {json.dumps(glossary, ensure_ascii=False)}\n\n"
        # The EXAMPLE governs, not the prose: with `"bubbles": []` here the model returned
        # bare strings and every speaker/addressee was silently lost.
        'Return ONE JSON object: {"panels": [{"panel_id": "...", '
        '"bubbles": [{"text": "verbatim words", "speaker": "who says it", '
        '"to": "who they say it to"}], '
        '"people": [], "speakers": [], "dialogue_summary": "", "action": "", "mood": "", '
        '"key_terms": [], "panel_type": "story", "is_story": true, "exclude_reason": ""}]}'
    )


def _chapter_windows(panels: list[Panel], max_per_call: int) -> list[list[Panel]]:
    """Split a chapter that is too large for one call, keeping windows big.

    Continuity is the whole point, so windows are as large as the budget allows rather
    than uniform — a 70-panel chapter is one window, not two of 35.
    """
    if len(panels) <= max_per_call:
        return [panels]
    windows: list[list[Panel]] = []
    for i in range(0, len(panels), max_per_call):
        windows.append(panels[i : i + max_per_call])
    return windows


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
    reference_preamble: str = "",
) -> str:
    ocr_block = []
    for p in batch:
        ocr = ocr_map.get(p.id)
        text = ocr.full_text if ocr else ""
        ocr_block.append(f"{p.id}: {text[:500]}")
    glossary_text = json.dumps(glossary, ensure_ascii=False)
    panel_ids = [p.id for p in batch]
    return (
        reference_preamble
        + "Analyze this manhwa panel in TWO STEPS — first transcribe what is literally visible, "
        "then infer from the transcription only.\n\n"
        "STEP 1 — TRANSCRIBE (only what you can literally see):\n"
        "- bubbles: verbatim text of every speech bubble / caption, in reading order\n"
        "- people: every VISIBLE person: {ref, name_used, descriptor, visibility, basis, "
        "confidence, notes}; "
        "ref=known char_id from the cast list below OR ref='new'; "
        "descriptor = appearance you can see; visibility=face|back_turned|partial|crowd; "
        "basis = the SPECIFIC visual evidence in THIS image that identifies the person "
        "(e.g. 'the scar across his left cheek', 'the red armband, clearly visible') — required whenever "
        "ref is not 'new' or name_used is set; "
        "confidence = number 0.0-1.0, how certain you are this is that SPECIFIC named cast "
        "member. Use 0.9+ only when the face is clear and unmistakable, 0.6-0.8 when "
        "reasonably sure, and below 0.5 when you are guessing from posture, clothing, or "
        "context — be honest, a low number is far more useful than a confident mistake.\n"
        "IDENTIFICATION DISCIPLINE: the cast list below exists to RESOLVE people you can "
        "already identify from this image alone — it is NOT a roster of who is expected "
        "to appear. Most panels contain NONE of the cast. Naming a back-turned, distant, "
        "or generic figure because a similar person exists in the cast list is an ERROR; "
        "use ref='new' with a plain descriptor instead. An unnamed person is always "
        "correct; a wrongly named one poisons every later stage.\n\n"
        "STEP 2 — INFER (from step 1 only):\n"
        "- speakers: the subset of people (by name_used or descriptor) who speak a bubble. "
        "A speaker MUST be one of the people visible in THIS panel — never name someone off-panel.\n"
        "- dialogue_summary: reported-speech summary of the bubbles ONLY — no invented lines\n"
        "- action, mood, key_terms (list), panel_ids, "
        "panel_type (story | title_splash | credit | ad | other), "
        "is_story (boolean), exclude_reason (string, empty if is_story is true)\n\n"
        "Return JSON with keys: bubbles, people, speakers, dialogue_summary, action, mood, "
        "key_terms, panel_ids, panel_type, is_story, exclude_reason.\n"
        "CRITICAL naming rules for action and dialogue_summary:\n"
        "- NEVER write 'a character', 'two characters', 'unnamed character', or 'the character'\n"
        "- Use canonical names, role descriptors (the caravan medic), or visual tags (the man with the red armband)\n"
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
            active = apply_panel_filter(paths, panels, scene_cards, config)
            # Cheap re-filter path: still verify every surviving story panel has a card,
            # so stale cached cards can't hide dropped panels.
            from manhwa2vid.qa import QAReport, enforce, qa_forced

            carded = {pid for c in scene_cards for pid in c.panel_ids}
            uncarded = sorted(p.id for p in active if p.id not in carded)
            report = QAReport(stage="scene")
            report.add(
                "cards-coverage",
                not uncarded,
                f"{len(uncarded)} story panel(s) with no scene card: {uncarded[:10]}"
                if uncarded else "",
                uncarded=uncarded,
            )
            enforce(report, paths["root"], force=qa_forced(config))
        return ocr_results, scene_cards

    paths["scene_normalized_json"].unlink(missing_ok=True)
    paths["scene_enriched_json"].unlink(missing_ok=True)
    paths["cast_attribution_json"].unlink(missing_ok=True)
    paths["panels_story_json"].unlink(missing_ok=True)
    paths["excluded_panels_json"].unlink(missing_ok=True)
    if force:
        # --force means re-analyze: a leftover checkpoint from a previous (possibly
        # misassigned) run must not be resumed into fresh output.
        paths["scene_partial_json"].unlink(missing_ok=True)

    seed_series_bible(meta, paths["glossary"], config)
    bible = load_series_bible(meta.series_slug, meta.title)

    # Visual identity anchors cached by earlier runs/chapters. Absent on a first-ever run
    # (nothing has been identified yet) — the sheet is rebuilt at the end of this stage.
    reference_sheet: list[tuple[str, Path]] = []
    reference_preamble = ""
    if get_nested(config, "scene", "use_reference_images", default=True):
        from manhwa2vid.characters.reference import format_reference_preamble, load_reference_sheet
        from manhwa2vid.models import series_paths as _series_paths

        _series_dir = _series_paths(find_repo_root(), meta.series_slug)["series_dir"]
        reference_sheet = load_reference_sheet(bible, _series_dir)
        reference_preamble = format_reference_preamble(reference_sheet)
        if reference_sheet:
            console.print(
                f"[dim]Identity references: {', '.join(l for l, _ in reference_sheet)}[/]"
            )

    panels = [Panel.model_validate(p) for p in json.loads(paths["panels_json"].read_text())]
    threshold = float(get_nested(config, "ocr", "confidence_threshold", default=0.5))
    glossary = json.loads(paths["glossary"].read_text()) if paths["glossary"].exists() else {}

    # Blank transition slivers never reach OCR or the vision model: they cost tokens and
    # bait hallucinated cards ("the sky clears...") for images with no content.
    from manhwa2vid.panels.filter import is_blank_panel
    from manhwa2vid.panels.split import panel_ink_stats_from_file

    for panel in panels:
        if panel.ink_ratio is None or panel.dark_ratio is None:
            stats = panel_ink_stats_from_file(paths["root"] / panel.image_path)
            if stats is not None:
                panel.ink_ratio, panel.dark_ratio = stats
    blank_panels = [p for p in panels if is_blank_panel(p, config)]
    analysis_panels = [p for p in panels if not is_blank_panel(p, config)]
    if blank_panels:
        console.print(
            f"[yellow]Skipping {len(blank_panels)} blank sliver panel(s) before OCR/vision:[/] "
            + ", ".join(p.id for p in blank_panels)
        )

    ocr_results: list[PanelOCR] = []
    with Progress() as progress:
        task = progress.add_task("OCR panels", total=len(analysis_panels))
        for panel in analysis_panels:
            ocr = ocr_panel(panel, paths["root"], threshold, meta.source_lang)
            if meta.source_lang == SourceLanguage.KO and ocr.full_text:
                ocr.translated_text = translate_ko_en(ocr.full_text)
            elif ocr.full_text:
                ocr.translated_text = ocr.full_text
            ocr_results.append(ocr)
            progress.advance(task)

    save_json(paths["ocr_json"], ocr_results)
    ocr_map = {o.panel_id: o for o in ocr_results}

    llm = apply_stage_model(get_stage_llm("scene", config), "scene", config)
    console.print(f"[dim]Scene LLM:[/] {type(llm).__name__} ({getattr(llm, 'vision_model', '?')})")
    # Prove the key can spend BEFORE ~60 vision calls, not after.
    from manhwa2vid.llm.provider import preflight_check

    preflight_check(llm, label="scene stage")

    scene_cards: list[SceneCard] = []

    # Chapter mode: one multimodal request carrying the whole chapter, so identity and
    # causality are PERCEIVED rather than reconstructed from per-panel prose downstream.
    # per_panel remains available for providers with small per-request caps.
    if str(get_nested(config, "scene", "mode", default="per_panel")).lower() == "chapter":
        scene_cards, counters, story_map = _run_chapter_scene_pass(
            analysis_panels, paths, ocr_map, glossary, bible, llm, config
        )
        dropped_speakers_total = counters["dropped_speakers"]
        demoted_ids_total = counters["demoted"]
        grounded_from_bubbles = counters["grounded_from_bubbles"]
        if story_map:
            save_json(paths["scene_story_map_json"], story_map)
            console.print(f"[dim]Chapter read:[/] {story_map.get('summary','')[:120]}")
        save_json(paths["scene_json"], scene_cards)
        paths["scene_partial_json"].unlink(missing_ok=True)
        return _finish_scene_stage(
            meta, paths, config, panels, blank_panels, scene_cards, ocr_results,
            bible, dropped_speakers_total, grounded_from_bubbles, demoted_ids_total,
        )

    batch_size = int(get_nested(config, "scene", "batch_size", default=1))
    batches = _batch_panels(analysis_panels, batch_size=batch_size)
    recent_cards: list[SceneCard] = []
    dropped_speakers_total = 0
    grounded_from_bubbles = 0
    demoted_ids_total = 0

    # Resume from a partial checkpoint: vision calls are the most expensive and
    # rate-limited step, so a crash mid-loop must never discard completed analyses.
    done_panels: set[str] = set()
    if paths["scene_partial_json"].exists():
        partial = [SceneCard.model_validate(s) for s in json.loads(paths["scene_partial_json"].read_text())]
        scene_cards.extend(partial)
        recent_cards.extend(partial[-2:])
        for card in partial:
            done_panels.update(card.panel_ids)
        console.print(f"[dim]Resuming scene analysis — {len(partial)} card(s) from checkpoint[/]")

    with Progress() as progress:
        task = progress.add_task("Scene analysis", total=len(batches))
        for batch in batches:
            if all(p.id in done_panels for p in batch):
                progress.advance(task)
                continue
            image_paths = [paths["root"] / p.image_path for p in batch]
            cast_context = format_cast_context(bible, recent_cards)
            # Reference images lead the request so identity is judged against pixels of
            # the actual character, not a text description two similar men both match.
            prompt = _build_scene_prompt(
                batch, ocr_map, glossary, cast_context, reference_preamble
            )
            raw = llm.describe_panels(
                [path for _label, path in reference_sheet] + image_paths, prompt
            )
            batch_ocr = " ".join(
                ocr_map[p.id].translated_text or ocr_map[p.id].full_text
                for p in batch
                if p.id in ocr_map
            )
            try:
                data = _normalize_scene_data(json.loads(raw), batch, ocr_text=batch_ocr, known_ids=set(bible.characters))
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
                    ocr_text=batch_ocr,
                )
            dropped_speakers_total += len(data.get("dropped_speakers", []))
            demoted_ids_total += int(data.get("demoted_identifications", 0))
            if not data["dialogue_summary"] and data.get("bubbles"):
                grounded_from_bubbles += 1
            # Ground truth for grounding: OCR where available, else the VLM's verbatim
            # bubble transcription — never its summary.
            spoken = data.get("attributed_lines") or data.get("bubbles", [])
            source_text = " | ".join(filter(None, [batch_ocr.strip(), " / ".join(spoken)]))
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
            save_json(paths["scene_partial_json"], scene_cards)  # checkpoint every batch
            progress.advance(task)

    save_json(paths["scene_json"], scene_cards)
    paths["scene_partial_json"].unlink(missing_ok=True)  # checkpoint fulfilled
    return _finish_scene_stage(
        meta, paths, config, panels, blank_panels, scene_cards, ocr_results,
        bible, dropped_speakers_total, grounded_from_bubbles, demoted_ids_total,
    )


def _finish_scene_stage(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    panels: list[Panel],
    blank_panels: list[Panel],
    scene_cards: list[SceneCard],
    ocr_results: list[PanelOCR],
    bible: Any,
    dropped_speakers_total: int,
    grounded_from_bubbles: int,
    demoted_ids_total: int,
) -> tuple[list[PanelOCR], list[SceneCard]]:
    """Reference refresh, panel filter, and the scene QA gates.

    Shared by both perception modes so chapter mode cannot silently bypass a gate the
    per-panel path enforces.
    """

    # Refresh the identity anchors from THIS chapter's best-evidenced identifications, so
    # each run (and each later chapter) starts from a stronger reference than the last.
    if get_nested(config, "scene", "use_reference_images", default=True):
        from manhwa2vid.characters.reference import build_reference_sheet
        from manhwa2vid.models import series_paths as _series_paths

        try:
            _sheet = build_reference_sheet(
                bible,
                scene_cards,
                {p.id: paths["root"] / p.image_path for p in panels},
                _series_paths(find_repo_root(), meta.series_slug)["series_dir"],
                chapter=meta.chapters,  # keeps the window spread across chapters/outfits
                min_confidence=float(
                    get_nested(config, "scene", "reference_min_confidence", default=0.75)
                ),
                panel_meta={p.id: p for p in panels},  # enforces the portrait-shape guard
            )
            if _sheet:
                console.print(
                    f"[dim]Identity references updated: "
                    f"{', '.join(label for label, _ in _sheet)}[/]"
                )
        except Exception as exc:  # never block the stage on a cache refresh
            console.print(f"[yellow]Reference sheet not updated:[/] {type(exc).__name__}")
    active = apply_panel_filter(paths, panels, scene_cards, config)
    console.print(f"[green]OCR:[/] {len(ocr_results)} panels, [green]scenes:[/] {len(scene_cards)} cards")

    from manhwa2vid.qa import QAReport, enforce, qa_forced

    report = QAReport(stage="scene")
    report.add(
        "blank-panels-excluded",
        "warn" if blank_panels else True,
        f"{len(blank_panels)} blank sliver(s) excluded: {[p.id for p in blank_panels]}"
        if blank_panels else "",
        blanks={p.id: {"ink": p.ink_ratio, "dark": p.dark_ratio} for p in blank_panels},
    )
    carded = {pid for c in scene_cards for pid in c.panel_ids}
    uncarded = sorted(p.id for p in active if p.id not in carded)
    report.add(
        "cards-coverage",
        not uncarded,
        f"{len(uncarded)} story panel(s) with no scene card: {uncarded[:10]}" if uncarded else "",
        uncarded=uncarded,
    )
    ocr_hits = sum(1 for o in ocr_results if o.full_text.strip())
    report.add(
        "ocr-coverage",
        True if ocr_hits else "warn",
        "" if ocr_hits else "no OCR text extracted — dialogue grounding relies on VLM transcription only",
        panels_with_text=ocr_hits, total=len(ocr_results),
    )
    report.add(
        "speakers-visible",
        True,
        f"dropped {dropped_speakers_total} off-panel speaker claim(s)" if dropped_speakers_total else "",
        dropped=dropped_speakers_total,
    )
    report.add(
        "dialogue-grounding",
        True,
        f"cleared {grounded_from_bubbles} ungrounded dialogue summar(ies)" if grounded_from_bubbles else "",
        cleared=grounded_from_bubbles,
    )
    report.add(
        "identification-basis",
        "warn" if demoted_ids_total else True,
        f"demoted {demoted_ids_total} named identification(s) with no visual basis"
        if demoted_ids_total else "",
        demoted=demoted_ids_total,
    )
    dup_frac, dup_panels = _duplicate_card_ratio(scene_cards)
    report.add(
        "card-diversity",
        True if dup_frac < _DIVERSITY_WARN_FRAC
        else ("warn" if dup_frac < _DIVERSITY_FAIL_FRAC else False),
        f"{dup_frac:.0%} of story cards duplicate another card's wording "
        f"(e.g. {dup_panels[:6]}) — the vision pass likely described one thing repeatedly"
        if dup_frac >= _DIVERSITY_WARN_FRAC else "",
        duplicate_fraction=round(dup_frac, 3), examples=dup_panels[:20],
    )
    story = sum(1 for c in scene_cards if c.is_story)
    report.add("story-cards", story > 0, f"{story}/{len(scene_cards)} story cards")
    enforce(report, paths["root"], force=qa_forced(config))
    return ocr_results, scene_cards


