"""Cross-panel identity linking and cast attribution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.characters.bible import (
    clean_bible_aliases,
    format_bible_for_prompt,
    load_series_bible,
    merge_profile,
    rebuild_bible_from_glossary,
    save_series_bible,
)
from manhwa2vid.characters.consolidate import apply_id_redirects, consolidate_profiles
from manhwa2vid.characters.resolve import (
    is_mc_visual_signal,
    normalize_descriptor,
    resolve_character_ref,
)
from manhwa2vid.config import get_nested
from manhwa2vid.llm.provider import apply_stage_model, get_stage_llm
from manhwa2vid.models import (
    CharacterProfile,
    CharacterRef,
    CharacterTier,
    PanelCast,
    ProjectMeta,
    SceneCard,
    SeriesBible,
    save_json,
)
console = Console()

_LINK_PROMPT = """You are linking manhwa panel identities across a chapter.

Given scene summaries with people descriptors and a character bible, merge duplicate identities.
Return JSON:
{{
  "merges": [
    {{"descriptor_or_name": "guy in green backpack", "char_id": "char_sung_jin_woo", "reason": "same person"}}
  ],
  "panel_updates": [
    {{"panel_id": "p0012_01", "people": [{{"ref": "char_sung_jin_woo", "name_used": "Sung Jin-Woo", "visibility": "back_turned", "notes": ""}}]}}
  ]
}}

Rules:
- Link back-turned / partial views to known cast when context implies same person
- Do NOT merge different named characters
- Do NOT assign protagonist id to generic descriptors like "guy with black hair" unless green backpack / Jin-Woo signals are present
- Prefer bible char_id when confident
"""


def _speaker_for_card(card: SceneCard) -> str:
    return card.speakers[0] if card.speakers else ""


def _ref_label(ref: str) -> str:
    """Human-readable text hidden inside a VLM-invented ref id.

    The vision model sometimes emits ids that were never minted by the bible
    (e.g. 'char_man_with_green_backpack'). The descriptor buried in the id is often
    the only evidence we have, so recover it for resolution.
    """
    if not ref or ref == "new":
        return ""
    return ref.removeprefix("char_").replace("_", " ").strip()


def _close_ref_against_bible(person: CharacterRef, card: SceneCard, bible: SeriesBible) -> str:
    """Resolve a ref that is not in the bible; return a valid char_id or ''.

    Tries, in order: MC strong visual signals (including the text inside the invented id),
    then normal name/descriptor resolution. Never invents protagonist assignment without
    a visual signal.
    """
    label = _ref_label(person.ref)
    name = person.name_used or ""
    descriptor = person.descriptor or label
    speaker = _speaker_for_card(card)

    if bible.protagonist_id and is_mc_visual_signal(name, descriptor, speaker):
        return bible.protagonist_id
    if bible.protagonist_id and label and is_mc_visual_signal("", label):
        return bible.protagonist_id

    return resolve_character_ref(name or label, descriptor, bible, speaker=speaker) or ""


def _name_match_score(name: str, profile: CharacterProfile) -> float:
    from manhwa2vid.characters.resolve import _name_match_score as score

    return score(name, profile)


def _display_name_for_person(
    person: CharacterRef,
    char_id: str,
    bible: SeriesBible,
    *,
    speaker: str = "",
) -> str:
    if not char_id or char_id not in bible.characters:
        return person.name_used or person.descriptor or char_id

    profile = bible.characters[char_id]
    if char_id == bible.protagonist_id and is_mc_visual_signal(
        person.name_used, person.descriptor, speaker
    ):
        return profile.canonical_name

    if person.name_used and _name_match_score(person.name_used, profile) >= 0.85:
        return profile.canonical_name

    if profile.tier == CharacterTier.SUPPORTING and person.name_used:
        return person.name_used

    return person.descriptor or person.name_used or profile.canonical_name


def _resolve_person_ref(
    person: CharacterRef,
    card: SceneCard,
    bible: SeriesBible,
    merges: dict[str, str],
) -> str | None:
    speaker = _speaker_for_card(card)
    if person.ref != "new" and person.ref in bible.characters:
        return person.ref

    key = normalize_descriptor(person.descriptor or person.name_used)
    if key and key in merges:
        candidate = merges[key]
        if candidate in bible.characters:
            if candidate == bible.protagonist_id:
                if is_mc_visual_signal(person.name_used, person.descriptor, speaker):
                    return candidate
            else:
                return candidate

    return resolve_character_ref(
        person.name_used,
        person.descriptor,
        bible,
        speaker=speaker,
    )


def _heuristic_descriptor_merge(cards: list[SceneCard], bible: SeriesBible) -> dict[str, str]:
    merges: dict[str, str] = {}
    for card in cards:
        speaker = _speaker_for_card(card)
        for person in card.people:
            if person.ref != "new" and person.ref in bible.characters:
                key = normalize_descriptor(person.descriptor or person.name_used)
                if not key:
                    continue
                if person.ref == bible.protagonist_id and is_mc_visual_signal(
                    person.name_used, person.descriptor, speaker
                ):
                    merges[key] = person.ref
                elif person.ref != bible.protagonist_id:
                    merges[key] = person.ref
                continue

            resolved = resolve_character_ref(
                person.name_used,
                person.descriptor,
                bible,
                speaker=speaker,
            )
            if not resolved:
                continue
            key = normalize_descriptor(person.descriptor or person.name_used)
            if not key:
                continue
            if resolved == bible.protagonist_id:
                if is_mc_visual_signal(person.name_used, person.descriptor, speaker):
                    merges[key] = resolved
            elif _name_match_score(person.name_used or person.descriptor, bible.characters[resolved]) >= 0.85:
                merges[key] = resolved
    return merges


def _apply_merges_to_cards(cards: list[SceneCard], merges: dict[str, str], bible: SeriesBible) -> list[SceneCard]:
    enriched: list[SceneCard] = []
    for card in cards:
        speaker = _speaker_for_card(card)
        people: list[CharacterRef] = []
        for person in card.people:
            char_id = _resolve_person_ref(person, card, bible, merges)
            if char_id and char_id in bible.characters:
                people.append(
                    CharacterRef(
                        ref=char_id,
                        name_used=_display_name_for_person(person, char_id, bible, speaker=speaker),
                        descriptor=person.descriptor,
                        visibility=person.visibility,
                        notes=person.notes,
                    )
                )
            else:
                people.append(person)
        enriched.append(
            SceneCard(
                panel_ids=card.panel_ids,
                speakers=card.speakers,
                dialogue_summary=card.dialogue_summary,
                action=card.action,
                mood=card.mood,
                key_terms=card.key_terms,
                source_text=card.source_text,
                is_story=card.is_story,
                exclude_reason=card.exclude_reason,
                panel_type=card.panel_type,
                people=people,
            )
        )
    return enriched


def _apply_panel_updates(cards: list[SceneCard], panel_updates: list[dict[str, Any]], bible: SeriesBible) -> list[SceneCard]:
    original_people: dict[str, list[CharacterRef]] = {}
    for card in cards:
        for panel_id in card.panel_ids:
            original_people[panel_id] = list(card.people)

    update_map: dict[str, list[CharacterRef]] = {}
    for item in panel_updates:
        panel_id = str(item.get("panel_id", ""))
        people_raw = item.get("people", [])
        orig = original_people.get(panel_id, [])
        refs: list[CharacterRef] = []
        for p in people_raw:
            if not isinstance(p, dict):
                continue
            ref = str(p.get("ref", "new"))
            name_used = str(p.get("name_used", ""))
            descriptor = str(p.get("descriptor", ""))
            if ref == "new":
                resolved = resolve_character_ref(name_used, descriptor, bible)
                ref = resolved or ref
            if ref == bible.protagonist_id:
                orig_had_mc = any(
                    op.ref == bible.protagonist_id
                    or is_mc_visual_signal(op.name_used, op.descriptor)
                    for op in orig
                )
                if not orig_had_mc or not is_mc_visual_signal(name_used, descriptor):
                    continue
            if ref not in bible.characters and ref != "new":
                continue
            refs.append(
                CharacterRef(
                    ref=ref,
                    name_used=name_used or descriptor,
                    descriptor=descriptor,
                    visibility=str(p.get("visibility", "face")),
                    notes=str(p.get("notes", "")),
                )
            )
        if panel_id and refs:
            orig_ids = {op.ref for op in orig if op.ref != "new"}
            new_ids = {r.ref for r in refs if r.ref != "new"}
            if len(orig_ids) >= 2 and len(new_ids) < len(orig_ids):
                continue
            update_map[panel_id] = refs

    if not update_map:
        return cards

    updated: list[SceneCard] = []
    for card in cards:
        new_people = list(card.people)
        for panel_id in card.panel_ids:
            if panel_id in update_map:
                new_people = update_map[panel_id]
        updated.append(
            SceneCard(
                panel_ids=card.panel_ids,
                speakers=card.speakers,
                dialogue_summary=card.dialogue_summary,
                action=card.action,
                mood=card.mood,
                key_terms=card.key_terms,
                source_text=card.source_text,
                is_story=card.is_story,
                exclude_reason=card.exclude_reason,
                panel_type=card.panel_type,
                people=new_people,
            )
        )
    return updated


def _dedupe_card_people(cards: list[SceneCard], bible: SeriesBible) -> list[SceneCard]:
    """One identity per panel: collapse people entries that resolve to the same profile."""
    deduped: list[SceneCard] = []
    for card in cards:
        seen: set[str] = set()
        people: list[CharacterRef] = []
        for person in card.people:
            if person.ref != "new" and person.ref in seen:
                continue
            if person.ref != "new":
                seen.add(person.ref)
            people.append(person)
        deduped.append(card.model_copy(update={"people": people}))
    return deduped


def _cast_integrity_report(cards: list[SceneCard], bible: SeriesBible) -> "QAReport":
    """Gates: every ref exists in the bible; no ref points at a merged-away profile."""
    from manhwa2vid.qa import QAReport

    report = QAReport(stage="cast")
    dangling: dict[str, list[str]] = {}
    redirected: dict[str, list[str]] = {}
    for card in cards:
        for person in card.people:
            if person.ref == "new":
                continue
            profile = bible.characters.get(person.ref)
            if profile is None:
                dangling.setdefault(person.ref, []).extend(card.panel_ids)
            elif profile.merged_into:
                redirected.setdefault(person.ref, []).extend(card.panel_ids)

    report.add(
        "referential-integrity",
        not dangling,
        f"{len(dangling)} ref(s) not in bible: {sorted(dangling)[:5]}" if dangling else "",
        dangling={k: v[:8] for k, v in dangling.items()},
    )
    report.add(
        "no-merged-refs",
        "warn" if redirected else True,
        f"{len(redirected)} ref(s) point at merged profiles" if redirected else "",
        redirected={k: v[:8] for k, v in redirected.items()},
    )
    mc = bible.protagonist_id
    if not mc:
        # No protagonist detected: legitimate for sparse/mock content, but worth surfacing.
        report.add("protagonist-exists", "warn", "no protagonist detected")
    else:
        report.add("protagonist-exists", mc in bible.characters,
                   "" if mc in bible.characters else f"protagonist_id={mc!r} not in bible")
    return report


def _build_attribution(cards: list[SceneCard]) -> list[PanelCast]:
    attribution: list[PanelCast] = []
    for card in cards:
        for panel_id in card.panel_ids:
            attribution.append(PanelCast(panel_id=panel_id, people=card.people))
    return attribution


def _seed_minor_profiles_from_cards(cards: list[SceneCard], bible: SeriesBible) -> None:
    for card in cards:
        for panel_id in card.panel_ids:
            for person in card.people:
                if person.ref == "new":
                    continue
                if person.ref in bible.characters:
                    continue
                label = person.descriptor or person.name_used
                if not label:
                    continue
                merge_profile(
                    bible,
                    CharacterProfile(
                        id=person.ref,
                        canonical_name=label,
                        tier=CharacterTier.MINOR,
                        descriptors=[person.descriptor] if person.descriptor else [],
                        first_seen_panel=panel_id,
                        appearances=[panel_id],
                        sufficiency="pending",
                    ),
                )


def _llm_link_pass(
    cards: list[SceneCard],
    bible: SeriesBible,
    config: dict[str, Any],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    evidence_lines = []
    for card in cards:
        if not card.is_story:
            continue
        pid = card.panel_ids[0] if card.panel_ids else "?"
        people = json.dumps([p.model_dump() for p in card.people], ensure_ascii=False)
        evidence_lines.append(
            f"{pid}: speakers={card.speakers}; people={people}; "
            f"action={card.action[:160]}; dialogue={card.dialogue_summary[:160]}"
        )
    if not evidence_lines:
        return {}, []

    llm = apply_stage_model(get_stage_llm("script", config), "script", config)

    user = (
        f"Bible:\n{format_bible_for_prompt(bible)}\n\n"
        f"Chapter scenes:\n" + "\n".join(evidence_lines[:80])
    )
    try:
        raw = llm.complete(_LINK_PROMPT, user, json_mode=True)
        data = json.loads(raw)
    except Exception:
        return {}, []

    merges: dict[str, str] = {}
    for item in data.get("merges", []):
        key = normalize_descriptor(str(item.get("descriptor_or_name", "")))
        char_id = str(item.get("char_id", "")).strip()
        if not key or not char_id or char_id not in bible.characters:
            continue
        if char_id == bible.protagonist_id and not is_mc_visual_signal("", key):
            continue
        merges[key] = char_id
    panel_updates = data.get("panel_updates", [])
    return merges, panel_updates if isinstance(panel_updates, list) else []


def _reset_bible_if_polluted(meta: ProjectMeta, paths: dict[str, Path], bible: SeriesBible) -> SeriesBible:
    glossary = json.loads(paths["glossary"].read_text(encoding="utf-8")) if paths["glossary"].exists() else {}
    mc_id = bible.protagonist_id
    polluted = False
    if mc_id and mc_id in bible.characters:
        mc = bible.characters[mc_id]
        if len(mc.aliases) > 8:
            polluted = True
    if len(bible.characters) == 1 and mc_id:
        polluted = True

    if not polluted:
        clean_bible_aliases(bible)
        return bible

    console.print("[yellow]Resetting polluted series bible from glossary[/]")
    summaries = dict(bible.chapter_summaries)
    bible = rebuild_bible_from_glossary(meta, glossary, chapter_summaries=summaries)
    cards = [SceneCard.model_validate(s) for s in json.loads(paths["scene_json"].read_text(encoding="utf-8"))]
    _seed_minor_profiles_from_cards(cards, bible)
    save_series_bible(bible)
    return bible


def _collapse_mc_duplicates(people: list[CharacterRef], bible: SeriesBible) -> list[CharacterRef]:
    mc_id = bible.protagonist_id
    if not mc_id or mc_id not in bible.characters:
        return people

    mc_profile = bible.characters[mc_id]
    mc_people: list[CharacterRef] = []
    others: list[CharacterRef] = []
    for person in people:
        if person.ref == mc_id or is_mc_visual_signal(person.name_used, person.descriptor):
            mc_people.append(person)
        else:
            others.append(person)

    if not mc_people:
        return people

    descriptor = next((p.descriptor for p in mc_people if p.descriptor), "")
    name_used = mc_profile.canonical_name
    if len(mc_people) == 1 and not is_mc_visual_signal(mc_people[0].name_used, mc_people[0].descriptor):
        if mc_people[0].ref == mc_id:
            return people

    merged_mc = CharacterRef(
        ref=mc_id,
        name_used=name_used,
        descriptor=descriptor,
        visibility=mc_people[0].visibility,
        notes=mc_people[0].notes,
    )
    return [merged_mc, *others]


def _normalize_mc_attribution(cards: list[SceneCard], bible: SeriesBible) -> list[SceneCard]:
    mc_id = bible.protagonist_id
    if not mc_id:
        return cards

    normalized: list[SceneCard] = []
    for card in cards:
        people = _collapse_mc_duplicates(list(card.people), bible)
        promoted: list[CharacterRef] = []
        for person in people:
            if person.ref != mc_id and is_mc_visual_signal(
                person.name_used, person.descriptor or _ref_label(person.ref)
            ):
                promoted.append(
                    CharacterRef(
                        ref=mc_id,
                        name_used=bible.characters[mc_id].canonical_name,
                        descriptor=person.descriptor,
                        visibility=person.visibility,
                        notes=person.notes,
                    )
                )
            else:
                promoted.append(person)
        promoted = _collapse_mc_duplicates(promoted, bible)
        normalized.append(
            SceneCard(
                panel_ids=card.panel_ids,
                speakers=card.speakers,
                dialogue_summary=card.dialogue_summary,
                action=card.action,
                mood=card.mood,
                key_terms=card.key_terms,
                source_text=card.source_text,
                is_story=card.is_story,
                exclude_reason=card.exclude_reason,
                panel_type=card.panel_type,
                people=promoted,
            )
        )
    return normalized


def _load_scene_cards_for_cast(paths: dict[str, Path], *, force: bool) -> list[SceneCard]:
    source = paths["scene_json"] if force else (
        paths["scene_enriched_json"] if paths["scene_enriched_json"].exists() else paths["scene_json"]
    )
    cards = [SceneCard.model_validate(s) for s in json.loads(source.read_text(encoding="utf-8"))]
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


def run_cast_linking(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> tuple[list[SceneCard], SeriesBible]:
    if (
        paths["cast_attribution_json"].exists()
        and paths["scene_enriched_json"].exists()
        and not force
    ):
        console.print("[dim]Using cached cast attribution[/]")
        cards = [SceneCard.model_validate(s) for s in json.loads(paths["scene_enriched_json"].read_text())]
        bible = load_series_bible(meta.series_slug, meta.title)
        return cards, bible

    cards = _load_scene_cards_for_cast(paths, force=force)
    if not cards:
        cards = [SceneCard.model_validate(s) for s in json.loads(paths["scene_json"].read_text())]

    bible = load_series_bible(meta.series_slug, meta.title)
    bible = _reset_bible_if_polluted(meta, paths, bible)
    if force:
        from manhwa2vid.characters.seed import seed_series_bible

        # Glossary sticky names only — avoid re-polluting bible from wiki category pages
        chars_cfg = dict(config.get("characters") or {})
        chars_cfg["wiki_lookup"] = False
        bible = seed_series_bible(meta, paths["glossary"], {**config, "characters": chars_cfg})

    heuristic_merges = _heuristic_descriptor_merge(cards, bible)
    llm_merges, panel_updates = _llm_link_pass(cards, bible, config)
    all_merges = {**heuristic_merges, **llm_merges}

    enriched = _apply_merges_to_cards(cards, all_merges, bible)
    enriched = _apply_panel_updates(enriched, panel_updates, bible)

    for card in enriched:
        for panel_id in card.panel_ids:
            for person in card.people:
                if person.ref == "new":
                    resolved = resolve_character_ref(
                        person.name_used,
                        person.descriptor,
                        bible,
                        speaker=_speaker_for_card(card),
                    )
                    if resolved:
                        person.ref = resolved
                elif person.ref not in bible.characters:
                    # VLM-invented id — close it against the bible or seed it, so every
                    # ref downstream is guaranteed to exist (referential integrity).
                    resolved = _close_ref_against_bible(person, card, bible)
                    if resolved:
                        person.ref = resolved
                    else:
                        label = person.name_used or person.descriptor or _ref_label(person.ref)
                        if label:
                            merge_profile(
                                bible,
                                CharacterProfile(
                                    id=person.ref,
                                    canonical_name=label,
                                    tier=CharacterTier.MINOR,
                                    descriptors=[person.descriptor] if person.descriptor else (
                                        [label] if label != person.name_used else []
                                    ),
                                    first_seen_panel=panel_id,
                                    sufficiency="pending",
                                ),
                            )
                if person.ref == "new":
                    continue
                if person.ref in bible.characters:
                    profile = bible.characters[person.ref]
                    new_descriptors = profile.descriptors
                    if person.descriptor and person.ref == bible.protagonist_id:
                        if is_mc_visual_signal(person.name_used, person.descriptor):
                            new_descriptors = list(dict.fromkeys([*profile.descriptors, person.descriptor]))
                    elif person.descriptor and person.ref != bible.protagonist_id:
                        new_descriptors = list(dict.fromkeys([*profile.descriptors, person.descriptor]))
                    merge_profile(
                        bible,
                        CharacterProfile(
                            id=profile.id,
                            canonical_name=profile.canonical_name,
                            tier=profile.tier,
                            aliases=profile.aliases,
                            descriptors=new_descriptors,
                            pronoun=profile.pronoun,
                            role=profile.role,
                            first_seen_panel=profile.first_seen_panel or panel_id,
                            appearances=list(dict.fromkeys([*profile.appearances, panel_id])),
                            visual=profile.visual,
                            narration_labels=profile.narration_labels,
                            source_chapters=profile.source_chapters,
                        ),
                    )

    consolidate_profiles(bible, config)
    clean_bible_aliases(bible)

    # Elect a protagonist if the bible has none. Election normally happens in the quest
    # stage, so re-running scene/cast alone (or rebuilding a polluted bible) can leave
    # protagonist_id empty — and everything downstream that anchors on the MC silently
    # degrades: naming priority, the MC name budget, MC-off-screen linting, and the
    # verifier's [PROTAGONIST] tag. Cheap to redo here, and it keeps the cast stage's own
    # protagonist-exists gate meaningful rather than merely observational.
    if not bible.protagonist_id and bible.characters:
        from manhwa2vid.characters.quest import detect_protagonist, set_protagonist_labels

        elected = detect_protagonist(bible, config)
        if elected:
            bible.protagonist_id = elected
            profile = bible.characters.get(elected)
            if profile is not None and profile.tier != CharacterTier.MAIN:
                profile.tier = CharacterTier.MAIN
            set_protagonist_labels(bible, elected, config)
            console.print(
                f"[dim]Protagonist elected from appearances:[/] "
                f"{bible.characters[elected].canonical_name} ({elected})"
            )

    enriched = apply_id_redirects(enriched, bible)
    enriched = _normalize_mc_attribution(enriched, bible)
    enriched = _dedupe_card_people(enriched, bible)

    attribution = _build_attribution(enriched)
    save_json(paths["scene_enriched_json"], enriched)
    save_json(paths["cast_attribution_json"], attribution)
    save_series_bible(bible)

    from manhwa2vid.qa import enforce, qa_forced

    enforce(_cast_integrity_report(enriched, bible), paths["root"], force=qa_forced(config))

    console.print(
        f"[green]Cast linking complete[/] — {len(enriched)} scenes, "
        f"{len(bible.characters)} bible entries, MC={bible.protagonist_id or '?'}"
    )
    return enriched, bible
