"""Rolling cast state during sequential scene analysis."""

from __future__ import annotations

from manhwa2vid.characters.bible import merge_profile
from manhwa2vid.characters.resolve import resolve_character_ref
from manhwa2vid.models import CharacterProfile, CharacterRef, CharacterTier, SceneCard, SeriesBible, VisualProfile


def format_cast_context(bible: SeriesBible, recent_cards: list[SceneCard]) -> str:
    lines = [f"Known cast:\n{bible_characters_summary(bible)}"]
    if bible.protagonist_id and bible.protagonist_id in bible.characters:
        mc = bible.characters[bible.protagonist_id]
        lines.append(f"Protagonist (MC): {mc.id} = {mc.canonical_name}")
    if recent_cards:
        lines.append("Recent panels:")
        for card in recent_cards[-2:]:
            pid = card.panel_ids[0] if card.panel_ids else "?"
            people = ", ".join(
                p.name_used or p.descriptor or p.ref for p in card.people
            ) or ", ".join(card.speakers) or "(none identified)"
            lines.append(f"  {pid}: {card.action[:120]} | people: {people}")
    return "\n".join(lines)


def bible_characters_summary(bible: SeriesBible) -> str:
    if not bible.characters:
        return "(none yet)"
    parts = []
    for profile in bible.characters.values():
        if profile.merged_into:
            continue
        desc = profile.descriptors[0] if profile.descriptors else ""
        visual = profile.visual
        visual_hint = visual.hair or visual.outfit or ""
        extra = f", {desc or visual_hint}" if (desc or visual_hint) else ""
        parts.append(f"{profile.id}={profile.canonical_name}{extra}")
    return "; ".join(parts[:15])


def _upsert_profile(
    bible: SeriesBible,
    char_id: str,
    *,
    name: str,
    descriptor: str,
    panel_id: str,
    tier: CharacterTier = CharacterTier.MINOR,
) -> None:
    if char_id in bible.characters:
        existing = bible.characters[char_id]
        merge_profile(
            bible,
            CharacterProfile(
                id=char_id,
                canonical_name=existing.canonical_name or name,
                tier=existing.tier,
                aliases=list(dict.fromkeys([*existing.aliases, name])) if name and name != existing.canonical_name else existing.aliases,
                descriptors=list(dict.fromkeys([*existing.descriptors, descriptor])) if descriptor else existing.descriptors,
                pronoun=existing.pronoun,
                role=existing.role,
                first_seen_panel=existing.first_seen_panel or panel_id,
                appearances=list(dict.fromkeys([*existing.appearances, panel_id])),
                visual=existing.visual,
                narration_labels=existing.narration_labels,
                sufficiency=existing.sufficiency,
                confidence=existing.confidence,
                source_chapters=existing.source_chapters,
            ),
        )
        return

    merge_profile(
        bible,
        CharacterProfile(
            id=char_id,
            canonical_name=name or descriptor,
            tier=tier,
            descriptors=[descriptor] if descriptor else [],
            pronoun="he",
            first_seen_panel=panel_id,
            appearances=[panel_id],
            sufficiency="pending",
        ),
    )


def update_bible_from_scene(
    bible: SeriesBible,
    card: SceneCard,
    panel_id: str,
) -> None:
    if not card.is_story or card.panel_type != "story":
        return

    for person in card.people:
        name = person.name_used.strip()
        descriptor = person.descriptor.strip()

        if person.ref != "new" and person.ref in bible.characters:
            char_id = person.ref
        else:
            resolved = resolve_character_ref(name, descriptor, bible)
            if resolved:
                char_id = resolved
            elif person.ref != "new" and person.ref in bible.characters:
                char_id = person.ref
            else:
                from manhwa2vid.characters.bible import slugify_char_id

                label = name or descriptor
                if not label:
                    continue
                char_id = slugify_char_id(label)

        person.ref = char_id
        tier = CharacterTier.SUPPORTING if name and name[0].isupper() else CharacterTier.MINOR
        _upsert_profile(bible, char_id, name=name or descriptor, descriptor=descriptor, panel_id=panel_id, tier=tier)

    for speaker in card.speakers:
        if not speaker or speaker.lower() in ("unknown", "unnamed", "unnamed character"):
            continue
        char_id = resolve_character_ref(speaker, "", bible)
        if not char_id:
            from manhwa2vid.characters.bible import slugify_char_id

            char_id = slugify_char_id(speaker)
        _upsert_profile(
            bible,
            char_id,
            name=speaker,
            descriptor="",
            panel_id=panel_id,
            tier=CharacterTier.SUPPORTING,
        )
