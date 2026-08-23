"""Series character bible load/save and formatting."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from manhwa2vid.config import find_repo_root
from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible, VisualProfile, save_json, series_paths

_DESCRIPTOR_PREFIXES = ("guy ", "man ", "woman ", "girl ", "boy ", "person ", "blonde ", "bald ", "crowd ")
_JUNK_ALIAS_RE = re.compile(r"(?i)^(template:|user:|category:)|infobox")


def normalize_name(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def is_junk_alias(text: str) -> bool:
    return bool(_JUNK_ALIAS_RE.search(text.strip()))


# Null-ish placeholders a model returns instead of admitting it has no name. Slugified,
# these become real-looking ids ("None" -> char_none) that then absorb every anonymous
# figure into one fake identity — so they must never reach an id.
_NULLISH_NAME_TOKENS = frozenset(
    {"none", "null", "nil", "n_a", "na", "unknown", "unnamed", "undefined"}
)


def slugify_char_id(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not base or base in _NULLISH_NAME_TOKENS:
        return "char_unknown"
    return f"char_{base}"


def is_descriptor_label(text: str) -> bool:
    t = normalize_name(text)
    if not t:
        return False
    if any(t.startswith(prefix) for prefix in _DESCRIPTOR_PREFIXES):
        return True
    if " with " in t and not any(ch.isupper() for ch in text):
        return True
    return False


def clean_profile_aliases(profile: CharacterProfile, *, protagonist_id: str = "") -> CharacterProfile:
    aliases = [a for a in profile.aliases if a.strip() and not is_junk_alias(a)]
    descriptors = list(profile.descriptors)
    if profile.id == protagonist_id:
        real_aliases: list[str] = []
        for alias in aliases:
            if is_descriptor_label(alias):
                if alias not in descriptors:
                    descriptors.append(alias)
            else:
                real_aliases.append(alias)
        aliases = real_aliases
    return CharacterProfile(
        id=profile.id,
        canonical_name=profile.canonical_name,
        tier=profile.tier,
        aliases=aliases,
        descriptors=descriptors,
        pronoun=profile.pronoun,
        role=profile.role,
        first_seen_panel=profile.first_seen_panel,
        appearances=profile.appearances,
        visual=profile.visual,
        narration_labels=profile.narration_labels,
        sufficiency=profile.sufficiency,
        confidence=profile.confidence,
        merged_into=profile.merged_into,
        source_chapters=profile.source_chapters,
    )


def clean_bible_aliases(bible: SeriesBible) -> None:
    for char_id in list(bible.characters):
        bible.characters[char_id] = clean_profile_aliases(
            bible.characters[char_id],
            protagonist_id=bible.protagonist_id,
        )


def load_series_bible(series_slug: str, title: str) -> SeriesBible:
    paths = series_paths(find_repo_root(), series_slug)
    path = paths["character_bible"]
    if path.exists():
        return SeriesBible.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return SeriesBible(series_slug=series_slug, title=title)


def save_series_bible(bible: SeriesBible) -> Path:
    paths = series_paths(find_repo_root(), bible.series_slug)
    paths["series_dir"].mkdir(parents=True, exist_ok=True)
    save_json(paths["character_bible"], bible)
    return paths["character_bible"]


def merge_profile(bible: SeriesBible, profile: CharacterProfile) -> None:
    existing = bible.characters.get(profile.id)
    if existing is None:
        bible.characters[profile.id] = profile
        return
    merged_appearances = list(dict.fromkeys([*existing.appearances, *profile.appearances]))
    merged_aliases = list(dict.fromkeys([*existing.aliases, *profile.aliases]))
    merged_aliases = [a for a in merged_aliases if not is_junk_alias(a)]
    merged_descriptors = list(dict.fromkeys([*existing.descriptors, *profile.descriptors]))
    merged_labels = list(dict.fromkeys([*existing.narration_labels, *profile.narration_labels]))
    merged_chapters = list(dict.fromkeys([*existing.source_chapters, *profile.source_chapters]))
    tier = existing.tier
    if profile.tier == CharacterTier.MAIN or (
        existing.tier != CharacterTier.MAIN and profile.tier == CharacterTier.SUPPORTING
    ):
        tier = profile.tier
    visual = VisualProfile(
        hair=profile.visual.hair or existing.visual.hair,
        outfit=profile.visual.outfit or existing.visual.outfit,
        build=profile.visual.build or existing.visual.build,
        accessories=list(dict.fromkeys([*existing.visual.accessories, *profile.visual.accessories])),
        age_range=profile.visual.age_range or existing.visual.age_range,
        notes=profile.visual.notes or existing.visual.notes,
    )
    bible.characters[profile.id] = CharacterProfile(
        id=profile.id,
        canonical_name=profile.canonical_name or existing.canonical_name,
        tier=tier,
        aliases=merged_aliases,
        descriptors=merged_descriptors,
        pronoun=profile.pronoun or existing.pronoun,
        role=profile.role or existing.role,
        first_seen_panel=existing.first_seen_panel or profile.first_seen_panel,
        appearances=merged_appearances,
        visual=visual,
        narration_labels=merged_labels,
        sufficiency=profile.sufficiency if profile.sufficiency != "pending" else existing.sufficiency,
        confidence=max(existing.confidence, profile.confidence),
        merged_into=profile.merged_into or existing.merged_into,
        source_chapters=merged_chapters,
    )


# Words that carry no story information on their own. A "role" that reduces to one of
# these after the tier word is stripped is not a role at all.
_EMPTY_ROLE_NOUNS = frozenset(
    """character person figure man woman guy girl one npc role someone somebody
    individual member""".split()
)


# Gendered nouns/titles in English. Language-level, not series vocabulary — a title's
# own words ("queen", "cowboy") never enter this list.
_FEMALE_WORDS = frozenset(
    """woman women girl girls lady ladies queen princess mother mom daughter sister
    wife widow nun priestess witch goddess maid waitress actress heroine she her hers""".split()
)
_MALE_WORDS = frozenset(
    """man men boy boys gentleman king prince father dad son brother husband widower
    monk priest wizard god butler waiter actor hero he him his""".split()
)


def effective_pronoun(profile: CharacterProfile) -> str:
    """The pronoun to actually use: the descriptors win when they clearly disagree.

    Applied on the READ path as well as the write path, because bibles persist at SERIES
    level across every chapter of a title and existing ones never rebuild themselves —
    the same reason sanitize_role is applied twice.
    """
    inferred = infer_pronoun_from_descriptors(profile)
    return inferred or (profile.pronoun or "they")


def infer_pronoun_from_descriptors(profile: CharacterProfile) -> str:
    """Read a character's gender off the descriptors the vision pass already wrote.

    The pronoun field is filled by the quest/search passes and is wrong often enough to
    corrupt narration: Frozen Player's bible records Skaya as "he" while three separate
    descriptors call her a "woman in white robes", and the Marksman as "they" while three
    call him a "man in a cowboy hat". That shipped "He nominates Jun-Ho" for a woman in
    one beat and "her staff" for the same character two beats later — the kind of
    contradiction a viewer notices immediately.

    Requires agreement: at least two descriptors pointing the same way and none pointing
    the other. A single mention decides nothing, and a genuinely mixed set is left alone
    rather than guessed at — "they" is a legitimate answer, just not one that should
    survive three descriptors saying "man".
    """
    female = male = 0
    for text in [*profile.descriptors, profile.role or ""]:
        words = {w.strip(".,'\u2019s").lower() for w in text.split()}
        if words & _FEMALE_WORDS:
            female += 1
        if words & _MALE_WORDS:
            male += 1
    if female >= 2 and male == 0:
        return "she"
    if male >= 2 and female == 0:
        return "he"
    return ""


def sanitize_role(role: str) -> str:
    """Strip internal TAXONOMY out of a character's story role.

    CharacterTier is bookkeeping — main/supporting/minor/extra rank how much page time
    someone gets. It is not something a narrator can say. But the tier word leaks into the
    role field (the quest/search passes see the tier in context and answer "supporting
    hunter"), the bible prints `role: supporting hunter`, and rule 4 tells the writer to
    introduce each person with their role — so Solo Leveling ch1 shipped "Kim Sangshik, a
    supporting hunter". Nothing in that clause tells a viewer anything.

    This is series-agnostic damage: any title gets "a supporting knight", "a supporting
    mage". Strip the tier word and keep the real noun ("supporting hunter" -> "hunter");
    if nothing informative survives ("main character"), return empty and let the writer
    introduce the person some other way rather than with a label about the pipeline.

    Applied on both paths deliberately. Sanitizing only at write time would leave every
    bible already on disk broken, and those persist at SERIES level across every chapter
    of a title — the state does not rebuild itself.
    """
    text = " ".join((role or "").split())
    if not text:
        return ""
    tier_words = {t.value.lower() for t in CharacterTier}
    kept = [w for w in text.split() if w.lower().strip(",") not in tier_words]
    # A role that ends mid-clause is a truncation artifact, not a role: the quest pass
    # once stored 'The final boss of the Antarctic dungeon whose' (its source sentence
    # continued "...whose blizzard froze the Pacific") and the introduction inserter
    # shipped that dangling "whose," verbatim. Trim trailing function words until the
    # role ends on a content word.
    _dangling = {
        "whose", "who", "which", "that", "and", "or", "but", "of", "with", "for",
        "from", "to", "in", "on", "at", "by", "the", "a", "an", "is", "was", "as",
    }
    while kept and kept[-1].lower().strip(",.") in _dangling:
        kept.pop()
    if not kept:
        return ""
    if kept == text.split():
        return text  # nothing removed; leave the role exactly as written
    if not kept or all(w.lower().strip(",") in _EMPTY_ROLE_NOUNS for w in kept):
        return ""
    return " ".join(kept)


def format_bible_for_prompt(bible: SeriesBible, *, active_ids: set[str] | None = None) -> str:
    if not bible.characters:
        return "(no characters in bible yet)"
    lines: list[str] = []
    ordered = sorted(
        bible.characters.values(),
        key=lambda p: (p.tier.value, -len(p.appearances), p.canonical_name),
    )
    for profile in ordered:
        if profile.merged_into:
            continue  # tombstone — kept only so id redirects survive consolidation
        if active_ids and profile.id not in active_ids and profile.tier not in (
            CharacterTier.MAIN,
            CharacterTier.SUPPORTING,
        ):
            continue
        alias_text = ", ".join(profile.aliases) if profile.aliases else ""
        desc_text = ", ".join(profile.descriptors) if profile.descriptors else ""
        visual_bits = [profile.visual.hair, profile.visual.outfit, profile.visual.build]
        visual_text = ", ".join(v for v in visual_bits if v)
        label_text = ", ".join(profile.narration_labels) if profile.narration_labels else ""
        mc_tag = " [MC]" if profile.id == bible.protagonist_id else ""
        parts = [
            f"- [{profile.tier.value}]{mc_tag} {profile.canonical_name} "
            f"(id={profile.id}, pronoun={effective_pronoun(profile)})"
        ]
        role_text = sanitize_role(profile.role)
        if role_text:
            parts.append(f"role: {role_text}")
        if alias_text:
            parts.append(f"aliases: {alias_text}")
        if desc_text:
            parts.append(f"looks: {desc_text}")
        if visual_text:
            parts.append(f"visual: {visual_text}")
        if label_text:
            parts.append(f"say_as: {label_text}")
        lines.append("; ".join(parts))
    return "\n".join(lines)


def naming_priority_rules(bible: SeriesBible | None = None, config: dict | None = None) -> str:
    """Anchor policy measured from the reference channel: the protagonist is anchored by
    NAME roughly every 80 words, with pronouns carrying everything in between (6+ pronoun
    references per anchor). Generic labels are what make a script feel like it lost its
    protagonist, so they are essentially banned."""
    mc_name = ""
    mc_pronoun = "he"
    if bible and bible.protagonist_id and bible.protagonist_id in bible.characters:
        mc = bible.characters[bible.protagonist_id]
        mc_name = mc.canonical_name.strip()
        mc_pronoun = mc.pronoun or "he"
    anchor = f"'{mc_name}'" if mc_name else "the protagonist's canonical name"
    return (
        "Naming rules (never use the word 'character' for a person on screen):\n"
        f"Protagonist{f' = {mc_name}' if mc_name else ''}:\n"
        f"  - Anchor with the NAME {anchor} roughly every 70-90 words, and at each scene change.\n"
        f"  - Between anchors use pronouns only ({mc_pronoun}/him/his) — several pronoun uses per name anchor.\n"
        "  - NEVER write 'MC'. Use the phrase 'the protagonist' at most ONCE in the whole chapter.\n"
        "  - Never describe the protagonist by clothing or gear as if a different person "
        "('the man with the backpack' is FORBIDDEN when it is him).\n"
        "Supporting cast:\n"
        "  - FIRST mention in the script: name + one short ROLE clause from the bible "
        "(what they do, never what they wear): '<name>, the party's field medic, ...'.\n"
        "  - Every later mention: name or pronoun. Never repeat the intro clause.\n"
        "Unnamed people: a short role phrase (the guild clerk, a veteran hunter) — "
        "NEVER 'character', 'someone', 'a man', 'two people'.\n"
        "Never attribute an action or line to anyone not on screen in that beat's panels.\n"
    )


def rebuild_bible_from_glossary(
    meta: Any,
    glossary: dict[str, Any],
    *,
    chapter_summaries: dict[str, str] | None = None,
) -> SeriesBible:
    """Reset polluted bible to glossary-backed cast hints."""
    from manhwa2vid.characters.seed import profiles_from_glossary

    bible = SeriesBible(series_slug=meta.series_slug, title=meta.title)
    if chapter_summaries:
        bible.chapter_summaries = chapter_summaries

    # Which character is the protagonist comes from the glossary, never from a name
    # hardcoded here. glossary.json may say so explicitly:
    #     {"protagonist": "Sung Jin-Woo", "characters": {...}}
    # and otherwise the first entry wins, since a reader writing a glossary by hand lists
    # the lead first. Their descriptors are simply their glossary aliases — the same place
    # the hardcoded list used to duplicate ("man with green backpack", "E-Rank hunter").
    declared = normalize_name(str(glossary.get("protagonist", "") or "")) if isinstance(glossary, dict) else ""
    profiles = list(profiles_from_glossary(glossary))
    for index, profile in enumerate(profiles):
        is_protagonist = (
            normalize_name(profile.canonical_name) == declared if declared else index == 0
        )
        if is_protagonist:
            profile.tier = CharacterTier.MAIN
            profile.role = profile.role or "protagonist"
            bible.protagonist_id = profile.id
        merge_profile(bible, profile)

    clean_bible_aliases(bible)
    return bible
