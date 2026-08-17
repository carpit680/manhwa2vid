"""Visual reference window — identity anchored to pixels instead of prose.

Each panel is analyzed independently, so the only thread tying "the man in the blue cap"
in panel 11 to the same man in panel 15 is a TEXT description in the bible. Text is a lossy
anchor: two dark-haired men in similar jackets read identically, which is how the recap
ended up saying Kim Sangshik hangs his head when it was the protagonist.

A reference IMAGE removes that indirection. But a SINGLE reference introduces a worse
failure over a long series: it silently anchors on whatever the character was wearing that
day. Jin-Woo in a grey hoodie with a green backpack becomes "green backpack = protagonist",
so the anchor actively misfires once he is in armour — and starts attracting any other
character carrying a pack.

So references are kept as a WINDOW of several images per character, deliberately spread
across chapters, and the prompt names which features survive a costume change (face, hair,
eyes, build) versus which do not (clothing, accessories). Seeing the same person in two
different outfits is what teaches the model which features actually identify them. The
window rolls forward as chapters are processed, so the cast stays recognizable as the art
and wardrobe drift.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from manhwa2vid.models import CharacterProfile, CharacterTier, Panel, SceneCard, SeriesBible

# A reference is only useful if the character is actually legible in it.
_USABLE_VISIBILITY = ("face", "partial")
# A reference must LOOK like a portrait, not like a page. Selection originally had no shape
# constraint and picked a 1080x4500 scroll strip containing its own speech bubbles; the
# vision model then transcribed the REFERENCE's bubbles instead of the panel's, and 85% of
# the next chapter's cards inherited that page's narration and injury imagery. A reference
# that carries its own text or spans a whole page is worse than no reference at all.
MAX_REFERENCE_ASPECT = 2.0   # height/width — above this it is a scroll strip, not a portrait
MIN_REFERENCE_ASPECT = 0.4
# How many characters get a reference window at all.
MAX_CHARACTERS = 3
# Images kept per character. >1 is the whole point: one image cannot distinguish a
# permanent feature from that chapter's outfit.
WINDOW_PER_CHARACTER = 3
# Hard ceiling on images prepended to a vision request — past this the panel under
# analysis stops being the focus.
MAX_TOTAL_REFERENCES = 6
_MIN_BASIS_CHARS = 8
# The vision model's own certainty floor for admitting an image to the window. A reference
# built from a shaky identification is worse than none: it becomes the anchor every later
# panel is matched against, so one wrong face propagates through the whole series.
MIN_REFERENCE_CONFIDENCE = 0.75


def reference_dir(series_dir: Path) -> Path:
    return series_dir / "reference"


def _score_candidate(
    basis: str, visibility: str, name_used: str, crowd: int, confidence: float
) -> int:
    """Higher is a better identity anchor.

    `crowd` is how many people share the panel. Whole panels are used as references (no
    per-person bounding boxes exist), so a panel with four figures makes "Image 1: Sung
    Jin-Woo" ambiguous — the model cannot tell which one is meant. A solo panel beats a
    crowded one even when the crowded one carries richer evidence.
    """
    score = 0
    if visibility == "face":
        score += 3
    elif visibility == "partial":
        score += 1
    score += min(len(basis) // 10, 3)  # a specific basis beats a terse one
    if name_used.strip():
        score += 2
    score -= 2 * max(0, crowd - 1)  # every extra body dilutes the anchor
    # The model's own certainty outranks every proxy above it: a self-reported 0.95 is
    # better evidence than a long basis string, which only shows it was verbose.
    score += int(round(confidence * 10))
    return score


def select_reference_panels(
    bible: SeriesBible,
    cards: list[SceneCard],
    *,
    max_refs: int = MAX_CHARACTERS,
    per_character: int = WINDOW_PER_CHARACTER,
    min_confidence: float = MIN_REFERENCE_CONFIDENCE,
    panels: dict[str, Panel] | None = None,
) -> dict[str, list[tuple[str, int]]]:
    """Best reference panels per character id → [(panel_id, score), ...], best first.

    Four filters must all pass: an explicit visual `basis`; the model's own `confidence`
    at or above `min_confidence`; NO dialogue on the panel (its bubbles would be
    transcribed as if they belonged to the panel under analysis); and a portrait-ish
    aspect ratio (a tall scroll strip is a page, not a face). The first two stop a shaky
    identification becoming a self-reinforcing anchor; the last two stop the reference's
    own content bleeding into every downstream card.
    """
    candidates: dict[str, list[tuple[str, int]]] = {}
    for card in cards:
        if not card.is_story or not card.panel_ids:
            continue
        # A reference carrying its own speech bubbles contaminates bubble transcription.
        if card.dialogue_summary.strip() or card.source_text.strip():
            continue
        if panels is not None:
            panel = panels.get(card.panel_ids[0])
            if panel is None:
                continue
            width = panel.bbox.width or 1
            aspect = panel.bbox.height / width
            if not (MIN_REFERENCE_ASPECT <= aspect <= MAX_REFERENCE_ASPECT):
                continue
        crowd = len(card.people)
        for person in card.people:
            ref = (person.ref or "").strip()
            if not ref or ref == "new":
                continue
            profile = bible.characters.get(ref)
            if profile is None or profile.merged_into:
                continue
            basis = (person.notes or "").strip()
            if len(basis) < _MIN_BASIS_CHARS:
                continue
            if person.visibility not in _USABLE_VISIBILITY:
                continue
            if person.confidence < min_confidence:
                continue
            score = _score_candidate(
                basis, person.visibility, person.name_used, crowd, person.confidence
            )
            candidates.setdefault(ref, []).append((card.panel_ids[0], score))

    # Slots are scarce, so rank characters by narrative weight before evidence quality:
    # protagonist first, then main/supporting. Scoring alone once spent a slot on "giant
    # statue on the right" — well-evidenced, but nobody confuses it with anyone.
    def _rank(item: tuple[str, list[tuple[str, int]]]) -> tuple[int, int, int]:
        char_id, entries = item
        profile = bible.characters.get(char_id)
        tier_order = {
            CharacterTier.MAIN: 0,
            CharacterTier.SUPPORTING: 1,
            CharacterTier.MINOR: 2,
            CharacterTier.EXTRA: 3,
        }
        best = max(s for _p, s in entries)
        return (
            0 if char_id == bible.protagonist_id else 1,
            tier_order.get(profile.tier, 3) if profile else 3,
            -best,
        )

    chosen: dict[str, list[tuple[str, int]]] = {}
    for char_id, entries in sorted(candidates.items(), key=_rank)[:max_refs]:
        best_per_panel: dict[str, int] = {}
        for panel_id, score in entries:
            if score > best_per_panel.get(panel_id, -999):
                best_per_panel[panel_id] = score
        ranked = sorted(best_per_panel.items(), key=lambda kv: -kv[1])[:per_character]
        chosen[char_id] = ranked
    return chosen


def _slot_name(char_id: str, chapter: str, index: int) -> str:
    safe_chapter = "".join(c if c.isalnum() else "_" for c in str(chapter))[:12] or "x"
    return f"{char_id}__ch{safe_chapter}_{index}.png"


def build_reference_sheet(
    bible: SeriesBible,
    cards: list[SceneCard],
    panel_paths: dict[str, Path],
    series_dir: Path,
    *,
    chapter: str = "",
    max_refs: int = MAX_CHARACTERS,
    per_character: int = WINDOW_PER_CHARACTER,
    min_confidence: float = MIN_REFERENCE_CONFIDENCE,
    panel_meta: dict[str, Panel] | None = None,
) -> list[tuple[str, Path]]:
    """Fold this chapter's best identifications into the rolling window on disk.

    Entries from OTHER chapters are kept and preferred for diversity — that spread across
    outfits is what makes the window robust to costume changes. Only this chapter's own
    entries are replaced, so re-running a chapter never inflates its share of the window.
    """
    selected = select_reference_panels(
        bible,
        cards,
        max_refs=max_refs,
        per_character=per_character,
        min_confidence=min_confidence,
        panels=panel_meta,
    )
    out_dir = reference_dir(series_dir)
    manifest = _load_manifest(out_dir)
    chapter_key = str(chapter or "?")

    conf_by_panel = _confidence_by_panel(cards)
    for char_id, entries in selected.items():
        prior = [e for e in manifest.get(char_id, []) if e.get("chapter") != chapter_key]
        fresh: list[dict[str, Any]] = []
        for index, (panel_id, score) in enumerate(entries):
            src = panel_paths.get(panel_id)
            if src is None or not src.exists():
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            filename = _slot_name(char_id, chapter_key, index)
            shutil.copyfile(src, out_dir / filename)
            fresh.append(
                {
                    "file": filename,
                    "panel_id": panel_id,
                    "chapter": chapter_key,
                    "score": score,
                    "confidence": round(conf_by_panel.get((char_id, panel_id), 0.0), 3),
                }
            )
        if not fresh and not prior:
            continue
        manifest[char_id] = _roll_window(prior, fresh, per_character)

    _prune_orphans(out_dir, manifest)
    if manifest:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
    return load_reference_sheet(bible, series_dir)


def _roll_window(
    prior: list[dict[str, Any]],
    fresh: list[dict[str, Any]],
    per_character: int,
) -> list[dict[str, Any]]:
    """Keep the window diverse across chapters, then fill remaining slots by score.

    One image per chapter first — a window holding three shots of the same outfit teaches
    nothing about which features are permanent, which is the entire reason for a window.
    """
    combined = [*fresh, *prior]
    kept: list[dict[str, Any]] = []
    seen_chapters: set[str] = set()
    for entry in sorted(combined, key=lambda e: -int(e.get("score", 0))):
        chapter = str(entry.get("chapter", "?"))
        if chapter in seen_chapters:
            continue
        seen_chapters.add(chapter)
        kept.append(entry)
        if len(kept) >= per_character:
            return kept
    for entry in sorted(combined, key=lambda e: -int(e.get("score", 0))):
        if entry in kept:
            continue
        kept.append(entry)
        if len(kept) >= per_character:
            break
    return kept


def _confidence_by_panel(cards: list[SceneCard]) -> dict[tuple[str, str], float]:
    """(char_id, panel_id) → best reported confidence, recorded in the manifest so a
    reference's provenance stays auditable after the fact."""
    out: dict[tuple[str, str], float] = {}
    for card in cards:
        if not card.panel_ids:
            continue
        for person in card.people:
            key = (person.ref, card.panel_ids[0])
            if person.confidence > out.get(key, -1.0):
                out[key] = person.confidence
    return out


def _load_manifest(out_dir: Path) -> dict[str, list[dict[str, Any]]]:
    path = out_dir / "manifest.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    if not isinstance(raw, dict):
        return {}
    manifest: dict[str, list[dict[str, Any]]] = {}
    for char_id, value in raw.items():
        if isinstance(value, list):
            manifest[char_id] = [e for e in value if isinstance(e, dict) and e.get("file")]
        elif isinstance(value, str):
            # Pre-window manifest: {char_id: panel_id} with an image at <char_id>.png.
            legacy = out_dir / f"{char_id}.png"
            if legacy.exists():
                manifest[char_id] = [
                    {"file": legacy.name, "panel_id": value, "chapter": "?", "score": 0}
                ]
    return manifest


def _prune_orphans(out_dir: Path, manifest: dict[str, list[dict[str, Any]]]) -> None:
    """Delete image files no longer referenced, so the window cannot grow without bound."""
    if not out_dir.exists():
        return
    live = {entry["file"] for entries in manifest.values() for entry in entries}
    for path in out_dir.glob("*.png"):
        if path.name not in live:
            path.unlink(missing_ok=True)


def load_reference_sheet(
    bible: SeriesBible,
    series_dir: Path,
    *,
    max_total: int = MAX_TOTAL_REFERENCES,
) -> list[tuple[str, Path]]:
    """Reference images cached by earlier runs/chapters, best-ranked first."""
    out_dir = reference_dir(series_dir)
    manifest = _load_manifest(out_dir)
    if not manifest:
        return []

    def _char_rank(char_id: str) -> tuple[int, int]:
        profile = bible.characters.get(char_id)
        tier_order = {
            CharacterTier.MAIN: 0,
            CharacterTier.SUPPORTING: 1,
            CharacterTier.MINOR: 2,
            CharacterTier.EXTRA: 3,
        }
        return (
            0 if char_id == bible.protagonist_id else 1,
            tier_order.get(profile.tier, 3) if profile else 3,
        )

    sheet: list[tuple[str, Path]] = []
    for char_id in sorted(manifest, key=_char_rank):
        label = _label_for(bible.characters.get(char_id), char_id, bible)
        for entry in manifest[char_id]:
            path = out_dir / str(entry.get("file", ""))
            if path.exists():
                sheet.append((label, path))
    return sheet[:max_total]


def _label_for(profile: CharacterProfile | None, char_id: str, bible: SeriesBible) -> str:
    name = profile.canonical_name if profile else char_id
    tag = " (PROTAGONIST)" if char_id == bible.protagonist_id else ""
    return f"{name}{tag}"


def format_reference_preamble(sheet: list[tuple[str, Path]]) -> str:
    """Prompt text explaining the leading images. Empty when there is no window."""
    if not sheet:
        return ""
    lines = [f"  Image {i}: {label}" for i, (label, _p) in enumerate(sheet, 1)]
    multi = len({label for label, _p in sheet}) < len(sheet)
    outfit_note = (
        "Several images show the SAME character in different scenes or chapters — compare "
        "them to work out which features are permanent and which are just that day's "
        "outfit.\n"
        if multi
        else ""
    )
    return (
        f"REFERENCE IMAGES: the FIRST {len(sheet)} image(s) are reference pictures of known "
        "cast members, not panels to analyze:\n"
        + "\n".join(lines)
        + "\n"
        + outfit_note
        + "Identify by features that SURVIVE a change of outfit: face shape, eyes, hair "
        "colour and style, build, age, scars. Clothing, bags, hats and weapons change "
        "between chapters and scenes — never treat them as proof of identity on their own, "
        "and never rule someone out just because their clothes differ from a reference.\n"
        "The panel(s) to analyze come AFTER these images. If nobody in the panel matches a "
        "reference by those durable features, use ref='new'. Never describe the reference "
        "images themselves, and never list their people in your output.\n\n"
    )
