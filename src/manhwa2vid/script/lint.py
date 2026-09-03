"""Script linting and banned-word rewrite."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.characters.bible import (
    format_bible_for_prompt,
    is_descriptor_label,
    naming_priority_rules,
)
from manhwa2vid.config import get_nested
from manhwa2vid.llm.provider import apply_stage_model, get_stage_llm
from manhwa2vid.models import CharacterTier, PanelCast, SceneCard, ScriptBeat, SeriesBible
from manhwa2vid.script.grounding import (
    GROUNDING_KEYWORDS,
    evidence_for_panels,
    quoted_lines_for_panels,
    unsupported_grounding_keywords,
)

console = Console()

_HEDGE_PATTERNS = [
    r"\bpossibly\b",
    r"\blikely\b",
    r"\bmaybe\b",
    r"\bmight be\b",
    r"\bmay be\b",
    r"\bseems to\b",
    r"\bappears to\b",
    r"\bhighlighting\b",
    r"\bis seen\b",
    r"\bis shown\b",
    r"\bpossibly showing\b",
]
_HEDGE_RE = re.compile("|".join(_HEDGE_PATTERNS), re.I)

# Soft first-person narrator aside signals
# What this counts is FIRST-PERSON intrusion and verbal filler — a narrator stepping
# out of the story to address you as himself. It deliberately does NOT count "bro":
# config.yaml documents that the reference runs ~8 casual epithets per 1k ("bro", "the
# guy") and that reading those as slang was "the error that made our narration read like
# a report". Counting it here capped it at max_narrator_asides (4) and triggered a
# rewrite to remove the exact register we are trying to reproduce — while the scorecard
# simultaneously floors the evaluative asides it is named after. Three mechanisms, one
# word, opposite directions.
_ASIDE_RE = re.compile(
    r"\b(ngl|no cap|lowkey|i mean|wait|honestly)\b"
    r"|\band look\b"
    r"|\b(i'm|i am|i just)\b",
    re.I,
)

# Report-register verbs the reference channel never uses (it says/asks/tells instead).
_REGISTER_RE = re.compile(
    r"\b(express(?:es|ed|ing)?|convers(?:es|ed|ing)|interact(?:s|ed|ing)?|"
    r"discuss(?:es|ed|ing)?|mention(?:s|ed|ing)?|react(?:s|ed|ing)?|"
    r"respond(?:s|ed|ing)?|gestur(?:es|ed|ing))\b",
    re.I,
)

# Narrating the artwork instead of the story.
_ART_RE = re.compile(
    r"\b(speech bubbles?|the viewer|panels?|the scene|the image|is depicted|we see|"
    r"captions?|photo inset|inset|title text|sound effects?|onomatopoeia|"
    r"looking (?:at|away from) the (?:viewer|camera))\b",
    re.I,
)

# Internal pipeline vocabulary leaking into spoken narration.
_LEAK_RE = re.compile(
    r"\b(referred to as|beat_id|panel_ids?|character_ids?|char_[a-z_]+|"
    r"now referred to|naming priority|"
    # The writer describing the STORYTELLING MECHANISM instead of telling the story:
    # "while narration explains that..." appeared once the inner-monologue rule landed.
    r"narration (?:explains|says|states|tells|reveals)|a caption (?:explains|reads)|the (?:caption|text|narration) (?:explains|reads|says))\b",
    re.I,
)

# "MC" is an internal label, never spoken narration.
_MC_TOKEN_RE = re.compile(r"\bMC\b")

# Verbatim quoted dialogue (reported speech is required). Matches spans of 4+ words inside
# straight or curly double quotes, or curly single quotes — straight apostrophes are left
# alone so contractions don't false-positive.
_QUOTE_RE = re.compile(r"[\"“‘]((?:\S+\s+){3,}\S+?)[\"”’]")

_PROTAGONIST_PHRASE_RE = re.compile(r"\bthe protagonist\b", re.I)

# Words that put the NEXT noun in the object slot, so a rotated name becomes him/her/them
# rather than he/she/they. Narration is spoken aloud — "Sangshik tells he to stay" is an
# audible error, not a silent one. Prepositions plus the transitive verbs this register
# actually uses (see reference/style_profile.md: says/asks/tells dominate).
_OBJECT_CUE_WORDS = frozenset(
    """
    to with at for from on of about behind beside near toward towards into onto than
    over under around past against upon after before between among across
    tells told asks asked says said warns warned calls called sees saw watches watched
    follows followed joins joined greets greeted thanks thanked helps helped stops stopped
    leads led drags dragged pushes pushed shoves shoved hits hit gives gave hands handed
    shows showed offers offered passes passed reminds reminded orders ordered sends sent
    leaves left meets met knows knew likes liked wants wanted needs needed lets let
    scolds scolded mocks mocked teases teased praises praised blames blamed
    engulfs engulfed swallows swallowed surrounds surrounded carries carried
    """.split()
)

_REWRITE_PROMPT = """Rewrite this recap beat narration.

Rules:
- Keep the same plot meaning; confident Mamoru-style story voice, PRESENT tense
- NEVER use these words/phrases: {ban_words}
- NEVER use hedging: possibly, likely, maybe, seems to, appears to, may be, highlighting, is seen, is shown
- NEVER use report-register verbs (expresses, converses, interacts, discusses, mentions, reacts, responds) — use says, asks, tells, replies, snaps
- NEVER quote dialogue verbatim or use quotation marks — convert to reported speech
- NEVER narrate the artwork: no "speech bubble", "panel", "the viewer", "the scene"
- NEVER write "MC"; the phrase "the protagonist" is allowed at most once per chapter — prefer the character's name or pronouns
- Anchor people by NAME (from the cast list) or pronoun; never by clothing descriptor if they have a name
- If an issue below says named_offscreen, remove or re-attribute that person's action — they are not in these panels
- If an issue below says overlong, cut to UNDER the stated word count — keep only the strongest plot facts
- If an issue says caption:..., the beat reads like an image description. Delete visual
  inventory (objects, clothing, expressions-as-phrases) and retell the beat as EVENTS with
  consequence — what happens, who says what, why it matters.
- If an issue says malformed_opening, the beat starts mid-sentence — rewrite it as a
  complete sentence with its subject restored.
- If an issue says repeats_beat_N, this beat re-tells what beat N already said —
  keep only what is NEW here and carry the moment forward.
- If an issue says reintro:Name, that person was already introduced — remove the
  appearance appositive and use the bare name or a pronoun.
- If an issue says pronoun_monotony, vary the sentence openings: start from the action,
  the other character, or a connective (But / So / Still / Then) — never three
  "He ..." sentences in a row.
- Write flowing sentences of roughly 9-18 words, linked by stance or consequence —
  cutting length must NOT mean chopping into staccato fragments
- Narrate ONLY what the panel EVIDENCE supports

Return ONLY the rewritten narration as plain prose. No JSON, no quotes around it, no
preamble, no explanation — the entire reply becomes the narration verbatim.
"""


def _clean_prose_reply(raw: str) -> str:
    """Normalize a plain-prose model reply into narration text.

    Models still occasionally wrap the answer in a fence or a JSON envelope despite being
    asked for prose, so unwrap those rather than shipping braces into the narration.
    """
    text = (raw or "").strip()
    text = re.sub(r"^```(?:\w+)?\s*|\s*```$", "", text).strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            match = re.search(r'"narration"\s*:\s*"(.+)"\s*}\s*$', text, flags=re.S)
            if match:
                return match.group(1).replace('\\"', '"').replace("\\n", " ").strip()
        else:
            if isinstance(data, dict) and data.get("narration"):
                return str(data["narration"]).strip()
    # A leading label ("Narration:") or wrapping quotes are the other two stock shapes.
    text = re.sub(r"^(?:rewritten\s+)?narration\s*:\s*", "", text, flags=re.I).strip()
    if len(text) > 1 and text[0] == text[-1] == '"':
        text = text[1:-1].strip()
    return text


def banned_words(config: dict[str, Any]) -> list[str]:
    words = get_nested(config, "characters", "ban_words", default=[])
    if isinstance(words, list) and words:
        return [str(w) for w in words]
    return ["character", "unnamed character", "a person"]


def find_violations(text: str, words: list[str]) -> list[str]:
    hits: list[str] = []
    lower = text.lower()
    for word in words:
        if word.lower() in lower:
            hits.append(word)
    return hits


def find_hedge_violations(text: str) -> list[str]:
    return sorted({m.group(0).lower() for m in _HEDGE_RE.finditer(text)})


PLACEHOLDER_PREFIXES = ("unnamed", "unidentified")

# One pattern, so the article is only ever touched at a strip site. A standalone
# `\ba(n)?\b` fixup pass would re-agree EVERY article in the narration and silently
# rewrite "an hour" to "a hour".
#
# No re.IGNORECASE: the flag applies to the whole pattern, so a case-insensitive
# `[a-z]` lookahead would match capitals too.
_PLACEHOLDER_ADJ_RE = re.compile(
    r"\b(?:(?P<art>[Aa]n?)\s+)?"
    + r"(?:" + "|".join(f"[{w[0]}{w[0].upper()}]{w[1:]}" for w in PLACEHOLDER_PREFIXES) + r")"
    + r"\s+(?=(?P<next>\w))"
)


def strip_placeholder_descriptors(text: str) -> str:
    """Remove cast-labelling placeholders that leaked into narration as adjectives.

    The read pass is told not to invent names for unnamed characters, and complies by
    putting the DESCRIPTOR in the name field: `"Unnamed Man in Cowboy Hat"`. That key
    becomes part of the canonical-name set handed to the writer and scored by
    `name-integrity`, so the narration says "the unnamed man in a cowboy hat" — a data
    label read aloud to the viewer. `merge_cast_into_glossary` now normalises the key,
    but narration is also written from panel text and from cached drafts, so the
    invariant is enforced on the finished prose too.

    Only the ATTRIBUTIVE use is stripped (placeholder directly modifying a following
    word), leaving "the man in a cowboy hat" — the descriptor the label carried
    survives. Predicative use ("the swordsman stayed unnamed") is ordinary English and
    is left alone. Any indefinite article in front re-agrees with the new head word.

    Sentence terminators are untouched, so `split_sentences` yields the same count
    before and after: `plan_shots` returns None when the sidecar's sentence count
    diverges from the narration's, which would silently drop the entire shot plan back
    to airtime weighting.
    """

    def _sub(m: re.Match[str]) -> str:
        art = m.group("art")
        if not art:
            return ""
        return f"{art[0]}{'n' if m.group('next').lower() in 'aeiou' else ''} "

    return re.sub(r"[ \t]{2,}", " ", _PLACEHOLDER_ADJ_RE.sub(_sub, text))


def local_sanitize_narration(text: str) -> str:
    """Fast regex cleanup before optional LLM rewrite."""
    cleaned = text
    cleaned = re.sub(r"\bunnamed characters?\b", "someone", cleaned, flags=re.I)
    cleaned = re.sub(r"\bunnamed\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\btwo characters\b", "two people", cleaned, flags=re.I)
    cleaned = re.sub(r"\ba character\b", "someone", cleaned, flags=re.I)
    cleaned = re.sub(r"\bthe character\b", "they", cleaned, flags=re.I)
    cleaned = re.sub(r"\bcharacters\b", "people", cleaned, flags=re.I)
    cleaned = re.sub(r"\ba person\b", "someone", cleaned, flags=re.I)
    # Soft local hedge strip for common patterns
    cleaned = re.sub(r",?\s*possibly\s+", " ", cleaned, flags=re.I)
    cleaned = re.sub(r",?\s*likely\s+", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\bhighlighting\b[^.]*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\bis seen\b", "is", cleaned, flags=re.I)
    cleaned = re.sub(r"\bis shown\b", "is", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _mc_terms(config: dict[str, Any]) -> list[str]:
    labels = get_nested(config, "characters", "mc_labels", default=["MC", "the protagonist", "our guy"])
    return [str(label).lower() for label in labels] if isinstance(labels, list) else ["mc", "the protagonist"]


def _panels_include_protagonist(
    panel_ids: list[str],
    protagonist_id: str,
    attribution: list[PanelCast],
) -> bool:
    if not protagonist_id:
        return False
    panel_set = set(panel_ids)
    for row in attribution:
        if row.panel_id not in panel_set:
            continue
        for person in row.people:
            if person.ref == protagonist_id:
                return True
    return False


def lint_mc_attribution(
    beats: list[ScriptBeat],
    bible: SeriesBible,
    attribution: list[PanelCast],
    config: dict[str, Any],
) -> dict[int, list[str]]:
    """Flag beats that use MC terms when protagonist is not on screen."""
    if not bible.protagonist_id:
        return {}
    mc_terms = _mc_terms(config)
    report: dict[int, list[str]] = {}
    for beat in beats:
        lower = beat.narration.lower()
        uses_mc = any(term in lower for term in mc_terms)
        on_screen = _panels_include_protagonist(beat.panel_ids, bible.protagonist_id, attribution)
        if uses_mc and not on_screen:
            report[beat.beat_id] = ["mc_attribution_off_screen"]
        if bible.protagonist_id not in beat.character_ids and on_screen and beat.beat_id > 1:
            if uses_mc and beat.character_ids:
                others = [cid for cid in beat.character_ids if cid != bible.protagonist_id]
                if others and bible.protagonist_id not in beat.character_ids:
                    report[beat.beat_id] = report.get(beat.beat_id, []) + ["wrong_character_ids"]
    return report


def lint_hedging(beats: list[ScriptBeat]) -> dict[int, list[str]]:
    report: dict[int, list[str]] = {}
    for beat in beats:
        hits = find_hedge_violations(beat.narration)
        if hits:
            report[beat.beat_id] = hits
    return report


def lint_mc_name_spam(
    beats: list[ScriptBeat],
    bible: SeriesBible,
    config: dict[str, Any],
) -> dict[int, list[str]]:
    """After beat 1, flag excess full canonical-name uses for the protagonist."""
    if not bible.protagonist_id or bible.protagonist_id not in bible.characters:
        return {}
    mc = bible.characters[bible.protagonist_id]
    name = mc.canonical_name.strip()
    if not name:
        return {}
    # Spam is DENSITY, not existence. The old cumulative cap (hook + 2 names for the
    # whole script) shipped a video where the MC was 'he' for fifteen straight beats —
    # 21:1 pronouns-to-names against the reference channel's ~6:1, and ambiguous out
    # loud wherever another man was named. One anchor per beat is the register the
    # reference actually speaks; two-plus in a single beat is the spam worth flagging.
    short = _short_name_form(name)
    name_re = re.compile(
        rf"\b(?:{re.escape(name)}|{re.escape(short)})(?:'s|’s)?\b", re.I
    )
    report: dict[int, list[str]] = {}
    for beat in beats:
        count = len(name_re.findall(beat.narration))
        allowed = 2 if beat.beat_id <= 1 else 1
        if count > allowed:
            report[beat.beat_id] = ["mc_full_name_spam"]
    return report


def lint_aside_overuse(
    beats: list[ScriptBeat],
    config: dict[str, Any],
) -> dict[int, list[str]]:
    max_asides = int(get_nested(config, "script", "max_narrator_asides", default=1))
    aside_beats: list[int] = []
    for beat in beats:
        if _ASIDE_RE.search(beat.narration):
            aside_beats.append(beat.beat_id)
    if len(aside_beats) <= max_asides:
        return {}
    # Flag extras beyond the first allowed aside
    report: dict[int, list[str]] = {}
    for beat_id in aside_beats[max_asides:]:
        report[beat_id] = ["aside_overuse"]
    return report


def lint_register(beats: list[ScriptBeat]) -> dict[int, list[str]]:
    """Report-register verbs, art-description phrasing, leaked internal vocabulary,
    the spoken 'MC' token, and verbatim quoted dialogue."""
    report: dict[int, list[str]] = {}
    for beat in beats:
        issues: list[str] = []
        for m in _REGISTER_RE.finditer(beat.narration):
            issues.append(f"register:{m.group(0).lower()}")
        if _ART_RE.search(beat.narration):
            issues.append("art_description")
        if _LEAK_RE.search(beat.narration):
            issues.append("instruction_leak")
        if _MC_TOKEN_RE.search(beat.narration):
            issues.append("mc_token_spoken")
        if _QUOTE_RE.search(beat.narration):
            issues.append("verbatim_quote")
        if issues:
            report[beat.beat_id] = sorted(set(issues))
    return report


# Caption constructions: each of these describes an IMAGE rather than advancing a story.
# Straight from the user's review of the shipped video ("a plate of food sits on the
# counter", "with a startled expression") — the failure they summarized as "a stringed
# narration of image descriptions".
_CAPTION_RE = re.compile(
    r"\bis visible\b|\bare visible\b|\bcan be seen\b"
    r"|\bin the (?:foreground|background)\b"
    r"|\bwith an? \w+ expression\b"
    r"|\bsits? on the\b|\brests? on the\b"   # "an empty plate ... rests on the counter"
    r"|\bpasses by\b"                          # narrated scenery extras
    r"|\bthe (?:image|view|shot|close-up)\b"
    r"|\b(?:left|right) side of\b",
    re.I,
)

# Body-language inventory: a named character performing a gesture or wearing a mood that
# changes nothing. Measured against the reference over the same two chapters: it runs
# ZERO of these, we shipped 15, at near-identical total word counts — so this is purely
# where the words went. Every one of these is a word not spent on the line the panel
# prints, which is how the chapter's own reveal ("[YOU HAVE COMPLETELY ABSORBED THE
# FROST QUEEN'S NUCLEUS.]") lost its beat to a boy pointing at a statue.
#
# FLAGGED, not stripped. The appearance appositives above are removable by construction
# — "Kim, a veteran in a blue jacket, waves" -> "Kim waves" is grammatically safe. These
# are whole predicates: deleting "tilts his head slightly upward" leaves no verb, and
# deciding what should have been there instead needs the panel. So this reports and the
# rewrite fixes it, which is the same division of labour lint_captioning already uses.
_BODY_PART = r"head|forehead|jaw|chin|temple|temples|chest|shoulders?|brow|eyes?|hands?|fists?"
_GESTURE_VERB = r"tilts?|clutches?|presses?|rubs?|scratches?|clenches?|cradles?|massages?"
_MOOD_ADVERB = (
    r"solemnly|somberly|sombrely|awkwardly|nervously|sheepishly|wearily|grimly|"
    r"excitedly|intently|slightly|deeply|profoundly"
)
_BODY_INVENTORY_RE = re.compile(
    # "tilts his head slightly upward", "clutches his forehead in deep frustration"
    rf"\b(?:{_GESTURE_VERB})\s+(?:his|her|their|its)\s+(?:{_BODY_PART})\b"
    # "looks down solemnly", "smiles awkwardly", "nods excitedly"
    rf"|\b(?:looks?|stares?|glances?|smiles?|nods?|shrugs?|frowns?|sighs?|blinks?)\s+"
    rf"(?:\w+\s+){{0,2}}(?:{_MOOD_ADVERB})\b"
    # "stares in shock", "gasps in disbelief", "recoils in horror"
    rf"|\b(?:stares?|gasps?|recoils?|flinches?|freezes?)\s+in\s+"
    rf"(?:\w+\s+){{0,2}}(?:shock|disbelief|horror|confusion|surprise|awe|amazement)\b"
    # "sweats", "a bead of sweat"
    rf"|\bbead of sweat\b|\bsweats?\s+(?:and|,|nervously|profusely)",
    re.I,
)

# An honorific's period is not a sentence end. "Mr. Kim tells Sung Jin-Woo." split into
# "Mr." + "Kim tells Sung Jin-Woo.", which is wrong everywhere this is used — it inflates
# short_sentence_fraction with one-token "sentences", misleads trim_overlong_beats and the
# dedupe passes about where a sentence begins, and made repair_broken_sentences delete the
# wrong half and emit "Mr. Jin-Woo laughs nervously". Each lookbehind is fixed-width,
# which is what Python's re requires.
# The shared splitter adopted lint's honorific handling on 2026-08-28, so the private
# copy that used to live here is now an alias — the two can never drift again.
from manhwa2vid.script.sentences import SENTENCE_SPLIT_RE as _SENTENCE_SPLIT_RE  # noqa: E402
_PRONOUN_START_RE = re.compile(r"^(?:He|She|They|His|Her|Their)\b")


def lint_captioning(beats: list[ScriptBeat]) -> dict[int, list[str]]:
    """Flag beats written as image descriptions instead of story.

    Two shapes: narrated ARTWORK ("in the foreground", "the close-up") and narrated BODY
    LANGUAGE ("tilts his head slightly upward", "gasps in disbelief"). The second was
    invisible here until measured — the reference runs zero body-inventory phrases over
    the same two chapters and the shipped script ran 15, at the same word count.
    """
    report: dict[int, list[str]] = {}
    for beat in beats:
        hits = sorted({m.group(0).lower() for m in _CAPTION_RE.finditer(beat.narration)})
        body = sorted({m.group(0).lower() for m in _BODY_INVENTORY_RE.finditer(beat.narration)})
        issues = [f"caption:{h}" for h in hits[:3]]
        issues += [f"body_inventory:{h}" for h in body[:3]]
        if issues:
            report[beat.beat_id] = issues
    return report


def strip_repeated_appositives(
    beats: list[ScriptBeat],
    bible: SeriesBible | None,
) -> list[ScriptBeat]:
    """Deterministically remove appearance appositives after each character's first.

    Two iterations asked the LLM rewrite to do this and it complied ZERO times (11
    flagged, 11 still flagged) — so it stops being a request. Removing an appositive is
    grammatically safe: "Kim Sangshik, a veteran with short grey hair, waves" -> "Kim
    Sangshik waves". The first occurrence per character keeps its intro clause.
    """
    if bible is None:
        return beats
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for profile in bible.characters.values():
        if profile.merged_into:
            continue
        name = profile.canonical_name.strip()
        if not name or is_descriptor_label(name):
            continue
        patterns.append(
            (name, re.compile(
                rf"(\b{re.escape(name)}),\s+(?:a|an|the|another|one)\s+(?:[\w''-]+\s+){{0,16}}[\w''-]+(,|(?=[.!?]))",
                re.I,
            ))
        )
    seen: set[str] = set()
    out: list[ScriptBeat] = []
    for beat in beats:
        text = beat.narration
        for name, rx in patterns:
            def _sub(m: re.Match, _name: str = name) -> str:
                if _name in seen:
                    return m.group(1)  # bare name, appositive dropped
                seen.add(_name)
                return m.group(0)      # first one keeps the intro clause
            text = rx.sub(_sub, text)
            # A bare mention (no appositive) also counts as introduced.
            if re.search(rf"\b{re.escape(name)}\b", text, re.I):
                seen.add(name)
        out.append(beat.model_copy(update={"narration": text}) if text != beat.narration else beat)
    return out


# Temporal-transition markers. A chapter rewinds from its flashforward exactly ONCE; the
# prompt rule fires per beat, so beats 1, 2 AND 3 each announced "but it starts hours
# earlier". Whole-beat repetition linting cannot see this — those beats differ everywhere
# except the one repeated clause.
_TRANSITION_RE = re.compile(
    r"\b(?:hours?|days?|weeks?|months?|years?|moments?) earlier\b"
    r"|\bwhere this day is headed\b"
    r"|\bback in the present\b"
    r"|\bin the present day\b"
    r"|\bthis nightmare (?:starts|begins)\b",
    re.I,
)


# Verbs that make the CLAUSE itself about time — the signature of a rewind restatement
# rather than a scene that happens to be set earlier.
_REWIND_CLAUSE_RE = re.compile(
    r"\b(?:starts?|started|begins?|began|is headed|was headed|heads?|goes? back|"
    r"takes? us back|rewinds?|picks? up)\b",
    re.I,
)


def strip_duplicate_transitions(
    beats: list[ScriptBeat],
    transition_panel: str = "",
) -> list[ScriptBeat]:
    """Keep the rewind on the beat whose PANELS show the time shift; delete the rest.

    "Keep the first mention" was wrong and shipped the defect it was meant to fix: the
    rewind landed in beat 1, spoken over dungeon art before anything changed, while the
    beat actually containing the present-day establishing shot narrated the killing blow
    and let the transition panel pass in silence. The gold script gives that panel its
    own beat ("Then the sky clears, over present-day Seoul"). `transition_panel` comes
    from the chapter read; without it we fall back to first-wins.

    A sentence is removed only if it is transition-only — it carries a marker and no
    other event. A sentence that both transitions AND advances the story is kept, and a
    beat is never emptied.
    """
    # The beat that OWNS the rewind: the one whose panels include the transition panel.
    owner_id: int | None = None
    if transition_panel:
        for beat in beats:
            if transition_panel in beat.panel_ids:
                owner_id = beat.beat_id
                break

    seen_transition = False
    out: list[ScriptBeat] = []
    for beat in beats:
        # With a known owner, every other beat loses its transition outright.
        if owner_id is not None and beat.beat_id != owner_id:
            sentences = [x for x in _SENTENCE_SPLIT_RE.split(beat.narration.strip()) if x.strip()]
            kept_here = [
                x for x in sentences
                if not (_TRANSITION_RE.search(x) and _REWIND_CLAUSE_RE.search(x))
            ]
            if kept_here and len(kept_here) < len(sentences):
                out.append(beat.model_copy(update={"narration": " ".join(kept_here).strip()}))
            else:
                out.append(beat)
            continue
        sentences = _SENTENCE_SPLIT_RE.split(beat.narration)
        kept: list[str] = []
        for sentence in sentences:
            if not _TRANSITION_RE.search(sentence):
                kept.append(sentence)
                continue
            if not seen_transition:
                seen_transition = True
                kept.append(sentence)
                continue
            # Distinguish a RESTATEMENT from a scene that merely happens earlier. If the
            # sentence's main clause is about time itself ("the path BEGINS hours
            # earlier", "that is where this day IS HEADED"), it re-announces the rewind
            # and goes. If the time phrase only frames a real event ("Hours earlier,
            # Joo-hee had begged him to stay home"), the event is new and stays.
            # A word-count threshold cannot tell these apart — the restatements were the
            # wordier ones.
            if not _REWIND_CLAUSE_RE.search(sentence):
                kept.append(sentence)
        if kept and len(kept) < len(sentences):
            out.append(beat.model_copy(update={"narration": " ".join(kept).strip()}))
        else:
            out.append(beat)
    return out


def strip_caption_sentences(
    beats: list[ScriptBeat],
    bible: SeriesBible | None,
) -> list[ScriptBeat]:
    """Delete sentences that are pure scenery captions.

    "An empty plate and chopsticks rest on the counter of the food stand." survived two
    LLM rewrite requests. A sentence is deletable only when it BOTH matches a caption
    pattern AND contains no person — no cast name, no personal pronoun. Sentences about
    people are never touched, and a beat is never emptied.
    """
    names: list[str] = []
    if bible is not None:
        for profile in bible.characters.values():
            if not profile.merged_into and profile.canonical_name.strip():
                names.extend(t for t in re.split(r"[\s\-‑]+", profile.canonical_name) if len(t) > 2)
    person_re = re.compile(
        r"\b(?:he|she|they|him|her|them|his|their"
        + ("|" + "|".join(re.escape(n) for n in set(names)) if names else "")
        + r")\b",
        re.I,
    )
    out: list[ScriptBeat] = []
    for beat in beats:
        sentences = _SENTENCE_SPLIT_RE.split(beat.narration)
        kept = [
            s for s in sentences
            if not (_CAPTION_RE.search(s) and not person_re.search(s))
        ]
        if kept and len(kept) < len(sentences):
            out.append(beat.model_copy(update={"narration": " ".join(kept).strip()}))
        else:
            out.append(beat)
    return out


def lint_reintroduction(
    beats: list[ScriptBeat],
    bible: SeriesBible | None,
) -> dict[int, list[str]]:
    """Flag appearance appositives after a character's first introduction.

    One iteration attached "with short grey hair" to Kim Sangshik SEVEN times, then
    introduced Song Chi-yul with the same phrase — three men sharing one description,
    indistinguishable to a listener. An intro clause exists exactly once per character;
    afterwards the name stands alone.
    """
    if bible is None:
        return {}
    report: dict[int, list[str]] = {}
    seen_intro: set[str] = set()
    patterns = []
    for profile in bible.characters.values():
        if profile.merged_into:
            continue
        name = profile.canonical_name.strip()
        if not name or is_descriptor_label(name):
            continue
        # "Name, a/an/the <up to 8 words>," — the appositive shape.
        patterns.append(
            (name, re.compile(
                rf"\b{re.escape(name)},\s+(?:a|an|the)\s+(?:[\w''-]+\s+){{0,8}}[\w''-]+,",
                re.I,
            ))
        )
    for beat in beats:
        issues: list[str] = []
        for name, rx in patterns:
            hits = len(rx.findall(beat.narration))
            if not hits:
                continue
            allowed = 0 if name in seen_intro else 1
            if hits > allowed:
                issues.append(f"reintro:{name}")
            seen_intro.add(name)
        if issues:
            report[beat.beat_id] = issues
    return report


def _stemmed_words(text: str) -> set[str]:
    """Content words with light suffix stripping.

    Restatements vary morphology: "he spots Kim WAVING" vs "Kim WAVES and asks". Exact
    tokens score those as different (0.4 overlap) and the echo survives; stemmed they
    match, which is what a listener hears.
    """
    out: set[str] = set()
    for word in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if len(word) <= 3:
            continue
        for suffix in ("ingly", "edly", "ing", "ies", "ied", "es", "ed", "ly", "s"):
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                word = word[: -len(suffix)]
                break
        out.add(word)
    return out


def dedupe_intra_beat_sentences(beats: list[ScriptBeat]) -> list[ScriptBeat]:
    """Remove a sentence that restates an earlier sentence of the SAME beat.

    Beat 8 had Kim waving in two consecutive sentences ("he spots Kim Sangshik waving
    enthusiastically" / "Kim waves warmly and asks if he has eaten"); beat 10 stated the
    weakest-hunter gossip three ways. Cross-beat repetition linting only compares whole
    beats, so within-beat echoes were invisible. Never drops the first sentence, never
    empties a beat.
    """
    out: list[ScriptBeat] = []
    for beat in beats:
        sentences = [s for s in _SENTENCE_SPLIT_RE.split(beat.narration.strip()) if s.strip()]
        if len(sentences) < 2:
            out.append(beat)
            continue
        kept: list[str] = []
        seen: list[set[str]] = []
        for sentence in sentences:
            tokens = _stemmed_words(sentence)
            if kept and tokens and any(
                len(tokens & prev) / len(tokens) >= 0.6 for prev in seen
            ):
                continue
            # The reverse duplication: a short sentence followed by its richer version
            # ("He points and laughs." then "He points and laughs at X for Y."). The
            # earlier one is a strict token-subset of the new one — keep the richer.
            drop = [i for i, prev in enumerate(seen) if prev and prev <= tokens]
            for i in reversed(drop):
                kept.pop(i)
                seen.pop(i)
            kept.append(sentence)
            seen.append(tokens)
        if len(kept) < len(sentences):
            out.append(beat.model_copy(update={"narration": " ".join(kept).strip()}))
        else:
            out.append(beat)
    return out


def beat_word_cap(
    n_panels: int,
    config: dict[str, Any],
    *,
    n_beats: int = 0,
    n_chapters: int = 1,
    payload_lines: int = 0,
) -> int:
    """The single source of truth for a beat's word budget.

    Three forces, minimum wins: the panel-driven budget (words the beat's screen time
    can pay for), the absolute per-beat ceiling, and — new — the share of the CHAPTER
    budget. Until now no total-length target existed anywhere: per-beat caps summed to
    1,680 words for a two-chapter project whose reference narration runs 979. Length was
    an emergent accident of beats x panel density. words_per_chapter (measured: the
    reference channel ~490/chapter, the two golds 525 and 677) makes runtime a chosen
    number, since narration is audio-locked and word count IS runtime.

    `payload_lines` then raises a FLOOR under all three, because every force above
    measures a beat's screen time and none of them measures what the beat has to SAY. A
    panel showing empty scenery and a panel printing three plot-critical system messages
    cost the same dwell and got the same budget. Frozen Player shipped exactly that
    contradiction: `split_dense_beats` isolated the panel carrying "an altar in the sea
    of lava" and "that altar requires the Frost Queen's nucleus" into its own beat, whose
    1-panel budget is 16 words — so `trim_overlong_beats` popped both payoff sentences
    off the tail, and `lint_dropped_dialogue` re-flagged the beat it had just fixed,
    every round, forever. The cap was not merely tight, it was UNSATISFIABLE: below even
    the two-sentence floor trim refuses to cut past, so the cap decided nothing and the
    truncation point was arbitrary.

    10 words per required line is not a new tunable: `words_per_beat` (40, measured from
    both golds and the reference channel) over the measured median of 4 distinct quoted
    lines per beat on both test titles. It lands within 1% of `words_per_shown_panel`
    (~9.9, derived independently from target_wpm x target_panel_seconds), which is the
    cross-check that it describes the same underlying speech rate. Still bounded by
    `max_beat_words`, so a pathologically chatty beat cannot mint runtime.
    """
    per_panel = int(get_nested(config, "script", "words_per_panel_target", default=14))
    ceiling = int(get_nested(config, "script", "max_beat_words", default=60))
    cap = min(max(16, n_panels * per_panel), ceiling)
    if n_beats > 0:
        per_chapter = int(get_nested(config, "script", "words_per_chapter", default=550))
        share = round(per_chapter * max(1, n_chapters) / n_beats * 1.2)
        cap = min(cap, max(20, share))
    if payload_lines > 0:
        per_line = int(get_nested(config, "script", "words_per_required_line", default=10))
        cap = max(cap, min(ceiling, payload_lines * per_line))
    return cap


def trim_overlong_beats(
    beats: list[ScriptBeat],
    config: dict[str, Any],
    scene_cards: list[SceneCard] | None = None,
) -> list[ScriptBeat]:
    """Enforce the per-beat word cap by dropping trailing sentences.

    Every word over budget stretches this beat's panels on screen, because audio locks
    the visuals. The cap has been in the prompt and the lint for days and the rewrite
    ignores it (4 flagged -> 3 still flagged). Trailing sentences are where the padding
    accumulates — the beat's own point is made first. Always keeps at least two
    sentences so a beat is never gutted.

    `scene_cards` is what stops this from deleting the very lines another gate demands:
    without them a beat's budget is blind to its dialogue load, and the tail this cuts
    from is exactly where a rewrite appends a newly-landed payoff (see `beat_word_cap`).
    """
    out: list[ScriptBeat] = []
    n_chapters = int(config.get("_n_chapters", 1)) if isinstance(config, dict) else 1
    for beat in beats:
        payload = (
            len(quoted_lines_for_panels(beat.panel_ids, scene_cards)) if scene_cards else 0
        )
        limit = beat_word_cap(
            len(beat.panel_ids), config, n_beats=len(beats), n_chapters=n_chapters,
            payload_lines=payload,
        )
        hard = int(limit * 1.35)
        sentences = [s for s in _SENTENCE_SPLIT_RE.split(beat.narration.strip()) if s.strip()]
        if len(beat.narration.split()) <= hard or len(sentences) <= 2:
            out.append(beat)
            continue
        kept = list(sentences)
        is_last = beat.beat_id == beats[-1].beat_id
        while len(kept) > 2 and len(" ".join(kept).split()) > limit:
            # The closer's FINAL sentences are the chapter's ending — the reveal the
            # whole chapter builds to sits there by construction. Trimming the closer
            # from the tail once deleted a seal-reveal the writer had correctly landed;
            # for the last beat the padding is the lead-in, so cut from the front.
            kept.pop(0) if is_last else kept.pop()
        out.append(beat.model_copy(update={"narration": " ".join(kept).strip()}))
    return out


def repair_malformed_openings(beats: list[ScriptBeat]) -> list[ScriptBeat]:
    """Drop a leading broken fragment when the rest of the beat is sound.

    Chunked generation can emit a dangling clause as a beat's first sentence ("is headed,
    but it starts hours earlier."). The missing subject cannot be invented, but the
    fragment itself is disposable — every following sentence is complete prose, so
    deleting it yields a clean beat. Only ever removes the FIRST sentence, never empties
    a beat, and leaves well-formed beats untouched.
    """
    out: list[ScriptBeat] = []
    for beat in beats:
        text = beat.narration.strip()
        sentences = _SENTENCE_SPLIT_RE.split(text) if text else []
        if len(sentences) >= 2 and sentences[0][:1].islower():
            rest = " ".join(sentences[1:]).strip()
            if rest and rest[:1].isupper():
                out.append(beat.model_copy(update={"narration": rest}))
                continue
        out.append(beat)
    return out


def lint_malformed_opening(beats: list[ScriptBeat]) -> dict[int, list[str]]:
    """Flag a beat that begins mid-sentence.

    Chunked generation occasionally emits a dangling clause as a beat's first words —
    one run opened beat 2 with "is headed, but it starts hours earlier." Spoken aloud
    that is simply broken, and no existing gate looked at how a beat STARTS.
    """
    report: dict[int, list[str]] = {}
    for beat in beats:
        text = beat.narration.strip()
        if not text:
            continue
        first = text.split()[0]
        # A real sentence opens with a capital (or a number/quote); a lowercase verb or
        # conjunction means the subject was lost upstream.
        if first[0].islower():
            report[beat.beat_id] = [f"malformed_opening:{' '.join(text.split()[:4])}"]
    return report


def lint_cross_beat_repetition(beats: list[ScriptBeat]) -> dict[int, list[str]]:
    """Flag a beat that re-tells content its predecessor already delivered.

    Each beat is written from only its own panels plus a short running summary, so two
    consecutive cards of one conversation produce two narrations of the same exchange —
    the hospital/healer content landed three times across beats 12-14. Nothing in the
    pipeline said a fact may be narrated once, and no gate measured it.
    """
    report: dict[int, list[str]] = {}
    prev: set[str] | None = None
    prev_id: int | None = None
    for beat in beats:
        tokens = _content_words(beat.narration)
        if prev and tokens:
            overlap = len(prev & tokens) / len(prev | tokens)
            if overlap >= 0.5:
                report[beat.beat_id] = [f"repeats_beat_{prev_id}:{overlap:.0%}"]
        prev, prev_id = tokens, beat.beat_id
    return report


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 3}


def lint_pronoun_monotony(beats: list[ScriptBeat]) -> dict[int, list[str]]:
    """Flag >=3 consecutive sentences opening with a subject pronoun.

    The aggregate pronoun:name ratio can be on target while one beat still reads
    "He walks... He blends... He thinks... He heads..." — the monotony is local, so the
    check must be local too. The gold script's worst run is 2.
    """
    report: dict[int, list[str]] = {}
    for beat in beats:
        run = longest = 0
        for sentence in _SENTENCE_SPLIT_RE.split(beat.narration):
            if _PRONOUN_START_RE.match(sentence.strip()):
                run += 1
                longest = max(longest, run)
            else:
                run = 0
        if longest >= 3:
            report[beat.beat_id] = [f"pronoun_monotony:{longest}_consecutive"]
    return report


def lint_overlong_beats(
    beats: list[ScriptBeat],
    config: dict[str, Any],
    scene_cards: list[SceneCard] | None = None,
) -> dict[int, list[str]]:
    """A beat's words are paid for in screen time by its panels; over budget = long
    static dwells. Flag with the concrete ceiling so the rewrite knows the target.

    Shares `trim_overlong_beats`' payload-aware budget so the two never disagree: a beat
    told to land three system messages must not also be told it is overlong for doing so.
    """
    # Allow some slack over the authoring target before forcing a rewrite.
    report: dict[int, list[str]] = {}
    n_chapters = int(config.get("_n_chapters", 1)) if isinstance(config, dict) else 1
    for beat in beats:
        payload = (
            len(quoted_lines_for_panels(beat.panel_ids, scene_cards)) if scene_cards else 0
        )
        limit = beat_word_cap(
            len(beat.panel_ids), config, n_beats=len(beats), n_chapters=n_chapters,
            payload_lines=payload,
        )
        words = len(beat.narration.split())
        if words > int(limit * 1.35):
            report[beat.beat_id] = [f"overlong:cut_to_{limit}_words"]
    return report


def rotate_protagonist_name(
    text: str,
    bible: SeriesBible,
    *,
    keep: int = 1,
    state: dict[str, int] | None = None,
    keep_form: str | None = None,
) -> str:
    """Deterministically replace 2nd+ uses of ANY protagonist name form in a beat with
    their pronoun. Models chronically ignore rotation instructions; the reference channel
    averages ~6 pronoun uses per name anchor, and name-spam every ~12 words (full name
    AND short aliases like 'Jin-Woo') was a top complaint about generated narration."""
    if not bible.protagonist_id or bible.protagonist_id not in bible.characters:
        return text
    mc = bible.characters[bible.protagonist_id]
    name = mc.canonical_name.strip()
    if not name:
        return text
    pronoun = (mc.pronoun or "he").lower()
    possessive = {"he": "his", "she": "her", "they": "their"}.get(pronoun, "their")
    objective = {"he": "him", "she": "her", "they": "them"}.get(pronoun, "them")

    # Only true NAME forms rotate: aliases whose every token comes from the canonical
    # name itself ('Sung', 'Jin-Woo'). Quest/consolidation also stores descriptor-ish
    # aliases ('weakest hunter', 'E-Rank hunter') — rotating those once produced spoken
    # garbage like "the world's he is still the strongest".
    name_tokens = {t.lower() for t in re.split(r"[\s\-‑]+", name) if t}

    def _is_name_form(alias: str) -> bool:
        tokens = {t.lower() for t in re.split(r"[\s\-‑]+", alias) if t}
        return bool(tokens) and tokens <= name_tokens

    forms = sorted(
        {name, *[a.strip() for a in mc.aliases if a.strip() and len(a.strip()) > 2 and _is_name_form(a.strip())]},
        key=len,
        reverse=True,
    )
    alternation = "|".join(re.escape(f).replace(r"\-", r"[-‑]") for f in forms)
    # The trailing lookaheads stop a short form matching INSIDE a longer name: the alias
    # 'Sung' once matched within the honorific 'Hunter Sung Woo-Jin' and shipped the
    # spoken garbage 'Hunter he Woo-Jin'.
    # (?-i: ...) scopes the lookahead case-SENSITIVELY — under the pattern-wide re.I,
    # [A-Z][a-z] would otherwise match any two letters and block every mid-sentence use.
    pattern = re.compile(rf"\b(?:{alternation})(’s|'s)?(?!(?-i:\s+[A-Z][a-z]))(?![-‑][A-Za-z])", re.I)
    # `state` carries the count ACROSS beats. Rotating each beat independently let every
    # beat keep its own first name use — 18 beats, 18 name uses, against a script-wide
    # budget of 2 (script.max_mc_full_name_after_hook). That mismatch was 11 of the 13
    # surviving lint flags on ch1.
    seen = state.get("seen", 0) if state is not None else 0

    def _sub(m: re.Match) -> str:
        nonlocal seen
        seen += 1
        if seen <= keep:
            # `keep_form` lets a kept anchor use the natural short form ("Jin-Woo")
            # instead of echoing the full canonical name at every anchor.
            if keep_form and not m.group(1):
                return keep_form
            if keep_form and m.group(1):
                return f"{keep_form}{m.group(1)}"
            return m.group(0)
        start = m.start()
        prior = text[:start].rstrip()
        sentence_initial = not prior or prior.endswith((".", "!", "?"))
        if m.group(1):
            replacement = possessive
        elif sentence_initial:
            # Always the subject at the start of a sentence, whatever preceded the period
            # ("runs over. Joo-hee asks" — 'over' is a cue word but belongs to the last
            # sentence, so reading it as an object slot yields "Her asks").
            replacement = pronoun
        else:
            # Mid-sentence: only rotate when the slot's case is CERTAIN. Prior word in
            # the object-cue list -> objective ("tells him"). Next word verb-ish ->
            # subject ("and Jin-Woo laughs" -> "and he laughs"). Anything else keeps the
            # NAME: "the gate engulfs Jin-Woo" once became "engulfs he" because 'engulfs'
            # was not on the cue list — an extra name mention costs style points; a wrong
            # pronoun case is gibberish out loud.
            last_word = re.search(r"([A-Za-z']+)\W*$", prior)
            after = text[m.end():].lstrip()
            words_after = [w.strip(".,!?;:'\"") for w in after.split()[:2]]
            next_word = words_after[0] if words_after else ""
            # "before Jun-Ho violently shatters": an adverb between the slot and its verb
            # hid the verb from the next-word test, so the objective branch won and
            # shipped "before him violently shatters". Look past a single -ly adverb.
            if next_word.lower().endswith("ly") and len(words_after) > 1:
                next_word = words_after[1]
            # Words that are BOTH prepositions and subordinating conjunctions. "before
            # him" is correct; "before him violently shatters" is not — the same word
            # opens a clause whose pronoun is a SUBJECT. Whenever a finite verb follows,
            # the slot is ambiguous by construction, so the name stays (the module's
            # precision-first policy: a spare mention beats spoken garbage).
            _DUAL_ROLE = {"before", "after", "until", "since", "while", "as", "than", "once"}
            if (
                last_word
                and last_word.group(1).lower() in _DUAL_ROLE
                and _looks_like_verb(next_word)
            ):
                return m.group(0)
            if last_word and last_word.group(1).lower() == "of":
                # "the hand of Jun-Ho" -> "the hand of him" is broken English; genitive
                # constructions keep the name (a spare mention beats spoken garbage).
                return m.group(0)
            if last_word and last_word.group(1).islower() and last_word.group(1).endswith("ing"):
                # "the monument containing Jun-Ho is beginning to crack": the name is the
                # OBJECT of a reduced relative clause, but the next word ("is") belongs to
                # the outer subject and passes the verb test — the subjective branch then
                # ships "containing he". A prior participle makes the slot uncertain by
                # construction, so the name stays (the documented safe policy).
                return m.group(0)
            if last_word and last_word.group(1).lower() in _OBJECT_CUE_WORDS:
                replacement = objective
            elif _looks_like_verb(next_word):
                replacement = pronoun
            else:
                return m.group(0)  # uncertain slot: the name stays, grammar guaranteed
        return replacement.capitalize() if sentence_initial else replacement

    out = pattern.sub(_sub, text)
    if state is not None:
        state["seen"] = seen
    return out


# Words that mark a following pronoun as the SUBJECT of its own clause. Reported speech is
# the dominant construction in this register ("says he is the weakest"), so the decisive
# signal is what comes AFTER the pronoun, not before: a finite verb means subject.
_FINITE_AUX = frozenset(
    """is was are were has have had will would can could should does did do
    might must may isn't wasn't hasn't won't can't didn't doesn't""".split()
)


def _looks_like_verb(word: str) -> bool:
    w = word.strip(".,!?;:'\"").lower()
    if not w:
        return False
    if w in _FINITE_AUX:
        return True
    # Present-tense third person and participles carry the clause in this style.
    return len(w) > 3 and (w.endswith("s") or w.endswith("ed") or w.endswith("ing"))


# Words after which a personal pronoun is reliably an OBJECT. Prepositions plus verbs
# that take a direct person object. Deliberately EXCLUDES clause-taking report verbs
# (says/admits/explains/wonders/realizes): "admits he returned" keeps a subject clause.
# History, because both directions of this bug have now shipped: a next-word-is-a-verb
# default converted "admits he only returned" -> "admits him" (adverbs) and "asks if he
# went" -> "if him went" (irregular pasts defeat suffix checks). Precision beats recall
# here — a missed conversion reads slightly off; a wrong one is gibberish out loud.
_OBJECT_PREV_WORDS = frozenset(
    """
    to with at for from on of about behind beside near toward towards into onto than
    over under around past against upon after before between among across without
    tells told asks asked warns warned calls called greets greeted thanks thanked
    helps helped stops stopped leads led drags dragged pushes pushed shoves shoved
    hits hit gives gave hands handed shows showed offers offered passes passed
    reminds reminded orders ordered sends sent meets met joins joined follows followed
    pats patted nudges nudged elbows elbowed hugs hugged grabs grabbed pulls pulled
    catches caught watches watched sees saw beside besides
    """.split()
)


def fix_pronoun_case(text: str, bible: SeriesBible) -> str:
    """Repair subject pronouns sitting in object position ("pats he on the shoulder").

    Converts ONLY when the previous word is in a high-precision object-cue whitelist;
    everything else keeps the nominative the writer chose. Spoken narration punishes the
    two failure modes asymmetrically: a missed conversion sounds slightly stiff, a wrong
    conversion ("Will him manage to survive?") is gibberish.
    """
    if not bible.protagonist_id or bible.protagonist_id not in bible.characters:
        return text
    pronoun = (bible.characters[bible.protagonist_id].pronoun or "he").lower()
    objective = {"he": "him", "she": "her", "they": "them"}.get(pronoun, "them")
    if objective == pronoun:
        return text

    pattern = re.compile(
        r"([A-Za-z']+)(\s+)\b" + re.escape(pronoun) + r"\b(?![-'’])(?=(\s*)(\S*))", re.I
    )

    def _sub(m: re.Match) -> str:
        # Prior word must be an object cue AND the next word must not be a verb:
        # "after" is a preposition in "runs after him" but a conjunction in "After he
        # dismisses the concern" — the verb after the pronoun is what tells them apart
        # ("After him dismisses" shipped once).
        next_word = (m.group(4) or "").strip(".,!?;:'\"")
        prior = m.group(1).lower()
        if prior.endswith("ing") and prior.islower() and prior not in _OBJECT_PREV_WORDS:
            return m.group(0)
        if prior in _OBJECT_PREV_WORDS and not _looks_like_verb(next_word):
            return f"{m.group(1)}{m.group(2)}{objective}"
        return m.group(0)

    text = pattern.sub(_sub, text)
    return _fix_object_pronoun_subjects(text)


# The other direction, which nothing caught: an OBJECT pronoun sitting in SUBJECT
# position. Observed: "warns Bak to stop before him hears". A subordinating conjunction
# opens a clause, so the pronoun immediately after it is a subject; if a finite verb
# follows, the objective form is simply wrong. Restricted to that frame because the same
# words are prepositions elsewhere ("after him", "before her") where the object IS
# correct — hence the required following verb.
_SUBORDINATORS = r"before|after|while|when|until|since|because|if|though|although|unless|whether|as"
_OBJECT_AS_SUBJECT_RE = re.compile(
    rf"\b({_SUBORDINATORS})\s+(him|her|them)\s+([\w'’-]+)",
    re.I,
)
_SUBJECT_FORM = {"him": "he", "her": "she", "them": "they"}
# Base-form verbs carry no suffix, so _looks_like_verb cannot see them and
# "after him quit" survived into a shipped draft. Narration verbs only — kept short and
# explicit rather than reaching for a part-of-speech tagger.
_BASE_VERBS = frozenset(
    """
    quit leave enter arrive speak hear see go come run walk talk know say tell ask
    answer reply shout call wait stand sit fall die win lose fight join return begin
    """.split()
)


def _fix_object_pronoun_subjects(text: str) -> str:
    def _sub(m: re.Match) -> str:
        following = m.group(3)
        bare = following.strip(".,!?;:'\u2019\"").lower()
        if not _looks_like_verb(following) and bare not in _BASE_VERBS:
            return m.group(0)
        # "her" is also a possessive determiner ("before her hands shake"), where the
        # objective form is correct and the next word only looks like a verb.
        if m.group(2).lower() == "her":
            return m.group(0)
        return f"{m.group(1)} {_SUBJECT_FORM[m.group(2).lower()]} {following}"

    return _OBJECT_AS_SUBJECT_RE.sub(_sub, text)


def _short_name_form(name: str) -> str:
    """The natural short anchor: the last hyphenated token ('Sung Jin-Woo' -> 'Jin-Woo')."""
    parts = name.split()
    return parts[-1] if len(parts) > 1 else name


def _same_pronoun_rivals(bible: SeriesBible) -> list[str]:
    from manhwa2vid.characters.bible import effective_pronoun

    """Names of non-protagonist characters who share the protagonist's pronoun.

    When one of these is named in a beat, a bare 'he' is ambiguous out loud — the listener
    cannot tell which man just laughed.
    """
    if not bible.protagonist_id or bible.protagonist_id not in bible.characters:
        return []
    mc_pron = (bible.characters[bible.protagonist_id].pronoun or "he").lower()
    rivals: list[str] = []
    for profile in bible.characters.values():
        if profile.id == bible.protagonist_id or profile.merged_into:
            continue
        if (effective_pronoun(profile) or "").lower() != mc_pron:
            continue
        name = profile.canonical_name.strip()
        if name and not is_descriptor_label(name):
            rivals.append(name)
    return rivals


def enforce_mc_name_budget(
    beats: list[ScriptBeat],
    bible: SeriesBible,
    config: dict[str, Any],
) -> list[ScriptBeat]:
    """Cadence-based protagonist-name rotation.

    The first version enforced a hard script-wide cap (hook + 2 names for 18 beats),
    which shipped a video where the MC is 'he' for fifteen straight beats — 62 pronouns
    to 3 names, 21:1 against the reference channel's ~6:1 — and made every beat that
    names another man ambiguous out loud ('Kim sips coffee and shouts to him. He says…').

    Cadence semantics instead: a beat keeps ONE name anchor when
      - it is the hook beat, or
      - at least `mc_anchor_every_beats` beats have passed since the last anchor, or
      - the beat names another same-pronoun character (a bare pronoun would be ambiguous).
    Everything else rotates to pronouns. Anchors after the first use the natural short
    form ('Jin-Woo'), matching how the reference channel actually speaks.
    """
    cadence = int(get_nested(config, "script", "mc_anchor_every_beats", default=2))
    rivals = _same_pronoun_rivals(bible)
    mc = bible.characters.get(bible.protagonist_id)
    short = _short_name_form(mc.canonical_name) if mc else ""

    rival_res = [re.compile(rf"\b{re.escape(n)}\b", re.I) for n in rivals]
    beats_since_anchor = 999  # first eligible beat anchors
    anchors = 0
    out: list[ScriptBeat] = []
    for idx, beat in enumerate(beats):
        ambiguous = any(rx.search(beat.narration) for rx in rival_res)
        # A beat that would OPEN on a bare pronoun must keep its name, whatever the
        # cadence says. Without this clause the budget and lint_unanchored_opening
        # contradict each other: the lint demands the beat name someone, the rewrite adds
        # the name, and this function — seeing no same-pronoun rival NAMED in the beat —
        # rotates it straight back out. ch1 beat 14 survived two rewrite rounds unfixed
        # for exactly that reason. Cadence exists to stop name spam, not to strip the one
        # anchor a listener needs to know who is acting.
        # Test the ROTATED text, not the input: the rotation is what creates the bare
        # opening. "Jin-Woo takes a sharp breath" becomes "He takes a sharp breath" and
        # only then leaves the listener without a subject.
        stripped = rotate_protagonist_name(beat.narration, bible, keep=0)
        prev_rivals = (
            [r for r in rivals if re.search(rf"\b{re.escape(r)}\b", beats[idx - 1].narration, re.I)]
            if idx else []
        )
        opens_bare = (
            bool(_OPENING_PRONOUN_RE.match(stripped.strip()))
            and stripped != beat.narration
            and bool(prev_rivals)
        )
        anchor_here = (
            beat.beat_id <= 1 or beats_since_anchor >= cadence or ambiguous or opens_bare
        )
        if anchor_here:
            # Full name for the very first anchor (the hook introduction); the short,
            # spoken form after that.
            form = None if anchors == 0 else (short or None)
            text = rotate_protagonist_name(beat.narration, bible, keep=1, keep_form=form)
            # Only count it as an anchor if the beat actually contained a name to keep.
            if text != rotate_protagonist_name(beat.narration, bible, keep=0):
                anchors += 1
                beats_since_anchor = 0
            else:
                beats_since_anchor += 1
        else:
            text = rotate_protagonist_name(beat.narration, bible, keep=0)
            beats_since_anchor += 1

        # Restore an anchor the beat never had. Everything above can only ROTATE a name
        # already present, so a beat the writer produced with no proper noun at all stayed
        # unanchored through every rewrite round — ch1 beat 14, "He takes a sharp breath",
        # with three men named in the beat before it.
        #
        # Substituting the protagonist is the inverse of what this function does:
        # rotate_protagonist_name turns the MC's name INTO "he", so a bare "he" in this
        # pipeline's own output is the MC by construction. Guarded to where that reading is
        # safe — the beat names nobody at all, the protagonist is in its own cast list, and
        # a same-pronoun rival in the previous beat makes the pronoun genuinely ambiguous.
        if short and (
            # Opens on a bare pronoun with a same-pronoun rival live in the beat before.
            (
                prev_rivals
                and beat.character_ids
                and bible.protagonist_id in beat.character_ids
                and _OPENING_PRONOUN_RE.match(text.strip())
                and not any(
                    re.search(rf"\b{re.escape(n)}\b", text, re.I)
                    for n in [*rivals, mc.canonical_name if mc else "", short] if n
                )
            )
            # Or acts through a pronoun anywhere in the beat while never being named —
            # the ice-break shape, which does not open bare and so slipped the clause
            # above entirely.
            or mc_acts_unnamed(beat.model_copy(update={"narration": text}), bible)
        ):
            # Substitute the FIRST subject pronoun, wherever it sits. Restricting this to
            # the beat's opening missed the ice-break shape entirely, where the beat opens
            # on somebody else ("The presenter introduces...") and the protagonist's only
            # appearance is a mid-beat "he".
            # Only the MC's OWN pronoun may be replaced. Substituting any of he/she/they
            # turned "proves they all share the same opinion" into "proves Jun-Ho all
            # share the same opinion" — a plural "they" is not the protagonist, and the
            # result is ungrammatical as well as wrong.
            from manhwa2vid.characters.bible import effective_pronoun

            mc_pronoun = effective_pronoun(mc) if mc else "he"
            if mc_pronoun not in {"he", "she"}:
                pass  # a they/them protagonist is indistinguishable from a plural here
            elif _OPENING_PRONOUN_RE.match(text.strip()):
                text = _OPENING_PRONOUN_RE.sub(short, text, count=1)
            else:
                text = re.sub(rf"\b{mc_pronoun}\b", short, text, count=1, flags=re.I)
            anchors += 1
            beats_since_anchor = 0
        out.append(beat.model_copy(update={"narration": fix_pronoun_case(text, bible)}))
    return out


def lint_protagonist_phrase(beats: list[ScriptBeat]) -> dict[int, list[str]]:
    """'the protagonist' is allowed once per chapter; every later use is a violation."""
    seen = 0
    report: dict[int, list[str]] = {}
    for beat in beats:
        count = len(_PROTAGONIST_PHRASE_RE.findall(beat.narration))
        if not count:
            continue
        seen += count
        if seen > 1:
            report[beat.beat_id] = ["protagonist_phrase_overuse"]
    return report


def lint_descriptor_quarantine(
    beats: list[ScriptBeat],
    bible: SeriesBible,
) -> dict[int, list[str]]:
    """A character with a real name must never be narrated by descriptor
    ('the man with the green backpack' for the protagonist)."""
    named_descriptors: list[tuple[str, str]] = []  # (descriptor_lower, canonical_name)
    for profile in bible.characters.values():
        if profile.merged_into or not profile.canonical_name.strip():
            continue
        if profile.tier.value not in ("main", "supporting"):
            continue
        # Skip profiles whose "name" is itself a descriptor label.
        if profile.canonical_name.lower().startswith(("guy ", "man ", "woman ", "blonde ", "bald ")):
            continue
        for desc in profile.descriptors:
            d = desc.strip().lower()
            if len(d.split()) >= 2:
                named_descriptors.append((d, profile.canonical_name))
    report: dict[int, list[str]] = {}
    for beat in beats:
        low = beat.narration.lower()
        # Only a REFERRING noun phrase counts — "the man with the green backpack" uses
        # the descriptor AS the person's identity. A possessive or action mention ("he
        # carries his green backpack") is legitimate narration; bare substring matching
        # flooded the rewrite loop with unfixable flags on 10 of 13 beats.
        hits = [
            f"descriptor_for_named:{name}"
            for d, name in named_descriptors
            if re.search(rf"\b(?:a|an|the)\s+{re.escape(d)}", low)
        ]
        if hits:
            report[beat.beat_id] = sorted(set(hits))
    return report


def lint_named_presence(
    beats: list[ScriptBeat],
    bible: SeriesBible,
    attribution: list[PanelCast],
) -> dict[int, list[str]]:
    """Any bible name in a beat's narration must be on screen in that beat's panels.
    Generalizes the MC-only check to the whole named cast — this is the gate that catches
    'the weakest hunter boasts about being highest ranked' before it ships."""
    attr_map: dict[str, set[str]] = {}
    for row in attribution:
        attr_map.setdefault(row.panel_id, set()).update(
            p.ref for p in row.people if p.ref and p.ref != "new"
        )
    named = [
        (p.canonical_name.strip().lower(), p.id)
        for p in bible.characters.values()
        if p.canonical_name.strip() and not p.merged_into
        and p.tier.value in ("main", "supporting")
        and not p.canonical_name.lower().startswith(("guy ", "man ", "woman ", "blonde ", "bald "))
    ]
    report: dict[int, list[str]] = {}
    for beat in beats:
        low = beat.narration.lower().replace("‑", "-")
        on_screen: set[str] = set()
        for pid in beat.panel_ids:
            on_screen.update(attr_map.get(pid, set()))
        issues: list[str] = []
        for name, char_id in named:
            variants = {name, name.replace("-", " ")}
            if any(v in low for v in variants) and char_id not in on_screen:
                issues.append(f"named_offscreen:{char_id}")
        if issues:
            report[beat.beat_id] = sorted(set(issues))
    return report


def _role_grounded_keywords(
    beat: ScriptBeat,
    bible: SeriesBible | None,
    attribution: list[PanelCast] | None,
) -> set[str]:
    """Grounding keywords that a PRESENT character's bible role already licenses.

    The recap prompt requires an intro clause drawn from the cast list ("Lee Joo-hee, the
    party's healer"), and the bible records that role — but panel art never contains the
    word 'healer', so the raw grounding check flagged the very clause the prompt mandates.
    A role sourced from the bible is grounded; only an INVENTED healer should flag.
    """
    if bible is None or not attribution:
        return set()
    panel_set = set(beat.panel_ids)
    present: set[str] = set()
    for row in attribution:
        if row.panel_id in panel_set:
            present.update(p.ref for p in row.people if p.ref and p.ref != "new")
    if not present:
        return set()
    text_parts: list[str] = []
    for ref in present:
        profile = bible.characters.get(ref)
        if profile is None:
            continue
        text_parts.extend([profile.role, *profile.narration_labels, *profile.descriptors])
    blob = " ".join(t.lower() for t in text_parts if t)
    if not blob:
        return set()
    return {key for key, phrases in GROUNDING_KEYWORDS.items() if any(p in blob for p in phrases)}


def lint_panel_grounding(
    beats: list[ScriptBeat],
    cards: list[SceneCard],
    *,
    bible: SeriesBible | None = None,
    attribution: list[PanelCast] | None = None,
) -> dict[int, list[str]]:
    """Flag beats that mention locations/events not supported by their panels' evidence."""
    report: dict[int, list[str]] = {}
    for beat in beats:
        bad = set(unsupported_grounding_keywords(beat.panel_ids, cards, beat.narration))
        bad -= _role_grounded_keywords(beat, bible, attribution)
        if bad:
            report[beat.beat_id] = [f"ungrounded:{k}" for k in sorted(bad)]
    return report


def lint_plot_coverage(
    beats: list[ScriptBeat],
    plot_by_id: dict[int, str],
    *,
    min_ratio: float = 0.25,
) -> dict[int, list[str]]:
    """Flag beats whose narration abandoned the outline's plot_beat.

    Every gate in this pipeline audits the HALLUCINATION direction — claims the panels
    do not support. Nothing audited the mirror, and that is where the damage was: the
    outline for Solo Leveling ch1 beat 8 read "Jin-Woo overhears them calling him the
    world's weakest hunter, before he tries to order a coffee only to find the vendor has
    run out", and the shipped narration contained NEITHER event, describing two men
    chatting instead. It passed every gate, because everything it said was true.

    The outline is the only artefact built with whole-chapter context, so it is the
    reference: score each beat by how much of its plot_beat's content vocabulary survives
    into the narration.

    Deliberately a WARN-and-rewrite signal, not a hard gate. The score is a lexical proxy
    for a semantic property, and it moves for honest reasons — heavy paraphrase scores
    low, repeated character names score high for free. Measured on the ch1 draft the
    distribution ran 0.00-0.81 with a 0.30 median, and the three beats a human reader
    independently called broken sat at 0.00, 0.06 and 0.07; 0.25 separates those from the
    honest paraphrases without chasing the middle. Tune the threshold, never the metric.
    """
    out: dict[int, list[str]] = {}
    for beat in beats:
        plot = (plot_by_id.get(beat.beat_id) or "").split("/ CLOSER")[0].strip()
        plot_tokens = _stemmed_words(plot)
        if not plot_tokens:
            continue  # continuity beats legitimately carry no plot_beat
        ratio = len(plot_tokens & _stemmed_words(beat.narration)) / len(plot_tokens)
        if ratio < min_ratio:
            out[beat.beat_id] = [
                f"narration covers only {ratio:.0%} of the beat's required story; it MUST "
                f"tell: {plot}"
            ]
    return out


def _dropped_line_priority(line: str) -> tuple[int, int, int]:
    """Higher sorts first. A bracketed system message is always plot-critical in this
    genre; a line carrying a number is usually a concrete fact (a count, a floor, a
    year) rather than color. Longer lines break remaining ties toward substance."""
    is_system = 1 if "[" in line and "]" in line else 0
    has_digit = 1 if any(ch.isdigit() for ch in line) else 0
    return (is_system, has_digit, len(line))


def is_system_line(line: str) -> bool:
    """A bracketed system message — the genre's non-negotiable plot beats."""
    return _dropped_line_priority(line)[0] == 1


def required_lines_for_beat(
    panel_ids: list[str],
    cards: list[SceneCard],
    config: dict[str, Any],
    *,
    max_words: int,
) -> list[str]:
    """The printed lines this beat MUST land, chosen deterministically.

    The single source of truth for *which lines are mandatory*, the way
    `beat_word_cap` is for *how many words are allowed* — so the prompt that asks for
    them and the gate that checks them can never disagree about the set.

    This exists because the loss was never that the writer couldn't see these lines:
    they were already in the EVIDENCE block. It was RANK. The beat block calls evidence
    "your only source of detail" and rule 7 says evidence bounds the DETAIL — so the
    prompt itself classified a printed system message as optional, while only
    `plot_beat` was mandatory. Frozen Player beat 11 owned the panels where Jun-Ho
    bursts out of the ice with "[YOU HAVE COMPLETELY ABSORBED THE FROST QUEEN'S
    NUCLEUS.]" and "[YOU HAVE RECEIVED THE NEW SKILL FROST(EX).]" printed on them, and
    narrated the boy pointing at the statue instead. The writer obeyed the prompt.

    Selected by `_dropped_line_priority` (system > numeric > longer) but returned in
    PANEL ORDER: priority decides what makes the cut, reading order decides how it is
    presented, so this never fights the "narrate panels in the order listed" rule.

    Capped at `max_required_lines_per_beat` (4) AND at what the word budget can hold
    (`max_words // words_per_required_line`). Not "all lines": `split_dense_beats`
    bounds a beat at 6, and 6 x 10 words is the entire 60-word ceiling with nothing
    left for a spine or a stake — which is how you get four flat "he says X, it says Y"
    sentences. 4 x 10 leaves ~20 words free, matching the 40-45 words/beat measured on
    both golds and the reference. Lines beyond the cap stay in EVIDENCE and remain
    covered by the warn-level corrective rounds, so nothing is lost relative to before.
    """
    lines = quoted_lines_for_panels(panel_ids, cards)
    if not lines:
        return []
    per_line = int(get_nested(config, "script", "words_per_required_line", default=10))
    hard_cap = int(get_nested(config, "script", "max_required_lines_per_beat", default=4))
    # Reserve framing words before dividing. Without this the budget arithmetic hands a
    # beat exactly as many lines as its cap can hold with nothing left to connect them:
    # FP beat 21 is one panel, cap 30, and was asked for 3 lines at 10 words each — a
    # word budget with no room for a subject, a speaker or a consequence. It shipped 28
    # words and landed two of the three, which is the arithmetic working as specified and
    # the specification being wrong. Same failure the 4-line hard cap already guards at
    # the top end; this guards the bottom.
    reserve = int(get_nested(config, "script", "required_line_framing_reserve", default=10))
    # Floor of 1: the reserve exists to stop a beat being packed wall-to-wall with
    # quotes, not to excuse it from its most important one. A narrow beat carrying a
    # single system message must still land it — that is the whole point of the check.
    budget_cap = max(1, (max_words - reserve) // per_line) if per_line > 0 else hard_cap
    n_req = max(0, min(len(lines), hard_cap, budget_cap))
    if not n_req:
        return []
    chosen = set(sorted(lines, key=_dropped_line_priority, reverse=True)[:n_req])
    return [ln for ln in lines if ln in chosen]  # back into panel order


def dropped_system_lines(
    beats: list[ScriptBeat],
    cards: list[SceneCard],
    dropped: dict[int, list[str]],
    required_by_beat: dict[int, list[str]],
) -> dict[int, list[str]]:
    """Of the lines a beat dropped, which were REQUIRED bracketed system messages.

    The blocking tier of `dialogue-delivery`, kept separate from the warn tier because
    the two differ in kind. The general check is a 0.3 stemmed-overlap proxy over every
    quoted line and moves for honest reasons — a faithful paraphrase scores low — so
    failing on it would fail every run and amount to tuning the metric to the threshold.
    A bracketed system message is a plot beat by construction, there are a handful per
    chapter, and it is precisely what went missing.
    """
    out: dict[int, list[str]] = {}
    for beat in beats:
        msgs = dropped.get(beat.beat_id)
        if not msgs:
            continue
        missing = [
            line for line in required_by_beat.get(beat.beat_id, [])
            if is_system_line(line) and any(line in m for m in msgs)
        ]
        if missing:
            out[beat.beat_id] = missing
    return out


def dialogue_delivery_status(
    mode: str,
    dropped: dict[int, list[str]],
    dropped_system: dict[int, list[str]],
) -> bool | str:
    """Tier the gate: `warn` reports only, `system` fails on a dropped required system
    message, `strict` fails on any dropped printed line."""
    if mode == "strict":
        return True if not dropped else False
    if mode == "system":
        return False if dropped_system else (True if not dropped else "warn")
    return True if not dropped else "warn"


def lint_dropped_dialogue(
    beats: list[ScriptBeat],
    cards: list[SceneCard],
    *,
    min_words: int = 4,
    min_ratio: float = 0.3,
    max_lines_per_beat: int = 2,
) -> dict[int, list[str]]:
    """Flag a beat that skips a panel's own quoted line for the panel's picture.

    `lint_plot_coverage` only checks the synopsis's five `plot_facts` — too coarse to
    catch a beat that narrates a panel's imagery while ignoring the quoted line printed IN
    that panel. Frozen Player's central reveal sat verbatim in a beat's own evidence
    ('system: "[YOU HAVE COMPLETELY ABSORBED THE FROST QUEEN'S NUCLEUS.]"') and the
    shipped narration described the hero's expression instead — six of the reference's
    nine payoffs were lost exactly this way, every one of them narrated (not curated out)
    with the line sitting right there in the card. A bracketed system message is always
    plot-critical in this genre, but the check is not restricted to brackets: any
    substantive quoted line the artwork prints is a payoff candidate.

    Deterministic and cheap: every quoted span in the beat's panels is checked by stemmed
    word overlap against that beat's narration, same metric `lint_plot_coverage` uses.
    `min_words` excludes bare exclamations ("HELLO.", "WHAT?!") — they carry no payoff and
    would only add noise to the rewrite prompt.

    `max_lines_per_beat` caps how many "MUST land" demands one rewrite call is handed:
    a beat with four dropped lines given four co-equal instructions has no way to know
    which one actually matters, and measured logs show it then lands none of them.
    `split_dense_beats` is the structural fix for a beat that is carrying too much to
    tell at all; this cap is what keeps a beat that is merely a LITTLE over — or one that
    slipped through before that pass ran — from being handed an unworkable rewrite brief.
    """
    if not cards:
        return {}
    out: dict[int, list[str]] = {}
    for beat in beats:
        lines = quoted_lines_for_panels(beat.panel_ids, cards, min_words=min_words)
        if not lines:
            continue
        narration_tokens = _stemmed_words(beat.narration)
        missing: list[str] = []
        for line in lines:
            tokens = _stemmed_words(line)
            ratio = len(tokens & narration_tokens) / len(tokens) if tokens else 1.0
            if ratio < min_ratio:
                missing.append(line)
        if not missing:
            continue
        missing.sort(key=_dropped_line_priority, reverse=True)
        out[beat.beat_id] = [
            f'narration drops the panel\'s own line — it MUST land: "{m}"'
            for m in missing[:max_lines_per_beat]
        ]
    return out


_FUNCTION_WORDS = frozenset(
    """a an the of in on at to from with by for and or that this his her its their
    into onto near behind beside toward towards through across over under""".split()
)

_TIME_SHIFT_PLOT_RE = re.compile(
    r"\b(?:transitions?|shifts?|jumps?|cuts?|moves?|returns?)\s+(?:the scene\s+)?(?:back\s+)?to\b"
    r"|\bthe scene (?:shifts?|changes?|transitions?)\b"
    r"|\bflash(?:es|ing)?[- ]?(?:back|forward)\b|\bflash(?:back|forward)\b"
    r"|\b(?:back|earlier|later) that (?:morning|day|night|week|month|year)\b"
    r"|\bpresent[- ]day\b|\bto the present\b|\bmoments? before\b"
    r"|\b(?:hours?|days?|weeks?|months?|years?) (?:earlier|later|before|ago)\b",
    re.I,
)
# Explicit cues a LISTENER can hear. A visual dissolve is not one: on the page a white
# flash and a change of scenery reads as a time jump, but read aloud it is just the next
# sentence, so the narration has to say so in words.
_TIME_CUE_RE = re.compile(
    r"\b(earlier|later|before (?:all )?(?:this|that)|beforehand|until then|by then|"
    r"back (?:then|in|at)|that (?:morning|afternoon|evening|night|day)|"
    r"hours?|days?|weeks?|months?|years? (?:earlier|later|before|ago)|ago|"
    r"rewind|now|at the time|once|前)\b",
    re.I,
)


def lint_time_shift_marker(
    beats: list[ScriptBeat], plot_by_id: dict[int, str]
) -> dict[int, list[str]]:
    """A beat that crosses a time boundary must SAY SO in words.

    Solo Leveling ch1 opens on the protagonist bleeding out, then jumps back to an
    ordinary morning. The outline knew ("a blinding flash transitions the scene back to a
    normal day in Seoul") and the narration rendered the jump entirely visually — a flash,
    then a river in sunshine. On the page that reads as a flashback because the ART
    changes; spoken aloud over those same panels it is just the next sentence, and a
    listener has no idea the story moved backwards in time.

    Detection is on the OUTLINE, not the narration: the outline is written with
    whole-chapter context and names the transition, while the narration is exactly the
    artefact that failed to. Every manhwa opens in media res sooner or later, so this is
    a structural property of the genre rather than a Solo Leveling quirk.
    """
    out: dict[int, list[str]] = {}
    for beat in beats:
        plot = plot_by_id.get(beat.beat_id) or ""
        if not _TIME_SHIFT_PLOT_RE.search(plot):
            continue
        if _TIME_CUE_RE.search(beat.narration):
            continue
        out[beat.beat_id] = [
            "this beat crosses a time jump but never says so — a viewer HEARS narration "
            "and cannot see a scene dissolve. Open the shifted part with an explicit "
            "spoken cue (\"Hours earlier,\" / \"Back at the start of that morning,\")"
        ]
    return out


def lint_repeated_setting(
    beats: list[ScriptBeat], terms: list[str], *, min_modifiers: int = 1
) -> dict[int, list[str]]:
    """A place or prop is DESCRIBED once; later beats refer to it plainly.

    Rule 4 already does this for people — name plus role clause on first mention, bare
    name ever after — and nothing did it for the world. ch1 established "a construction
    site where a swirling blue dungeon Gate vibrates behind industrial scaffolding" in
    beat 3 and then re-established "a glowing blue magical Gate inside a construction
    site" in beat 13, which a viewer hears as arriving somewhere new.

    Flags for rewrite rather than editing the text: the repeated sentence usually also
    carries NEW story ("the raid party gathers at the entrance"), so deleting it loses a
    beat, and stripping modifiers by regex is the kind of surgery that has twice broken
    correct prose in this module. The rewriter is told which term is already established.
    """
    out: dict[int, list[str]] = {}
    established: dict[str, int] = {}
    for beat in beats:
        for term in terms:
            if not term:
                continue
            pattern = re.compile(
                r"\b(?:a|an|the)\s+((?:[a-z][\w'’-]*\s+){%d,4})%s\b" % (min_modifiers, re.escape(term)),
                re.I,
            )
            match = pattern.search(beat.narration)
            # The captured run must be a real premodifier chain. Without this the article
            # of a DIFFERENT noun anchors the match: "A shout from the Gate" captured
            # "shout from the" as modifiers of Gate and flagged a beat that describes
            # nothing. A function word in the run means the chain was never one.
            if match and _FUNCTION_WORDS & {w.lower() for w in match.group(1).split()}:
                match = None
            if not match:
                continue
            first = established.get(term.lower())
            if first is None:
                established[term.lower()] = beat.beat_id
            elif first != beat.beat_id:
                out.setdefault(beat.beat_id, []).append(
                    f"'{term}' was already described in beat {first}; name it plainly here "
                    f"(the/that {term}) and spend the words on what HAPPENS instead"
                )
    return out


def lint_hook_grounding(hook: str, evidence_text: str) -> list[str]:
    """Specific claims in the hook must exist in the panels.

    The ch1 hook promised "a D-rank gate in Seoul". D-rank appears in no panel of the
    chapter — it is an E-rank dungeon, and the hook is the first line a viewer hears.
    The hook is generated from the synopsis with no panel binding of its own, so nothing
    downstream ever checked it.

    Narrow by design: only tokens carrying a hyphen or a digit are treated as specific
    claims (ranks, tiers, levels, counts, dates — the litRPG idiom this genre runs on).
    Prose words are left alone, because a hook is allowed to characterise while a rank is
    a fact that is either on the page or invented.
    """
    haystack = evidence_text.lower()
    bad: list[str] = []
    for token in re.findall(r"\b[a-z]+-[a-z]+\b|\b[a-z]*\d[\w-]*\b", (hook or "").lower()):
        if len(token) < 3 or token in bad:
            continue
        if token not in haystack:
            bad.append(token)
    return bad


_REPORT_VERB_RE = re.compile(
    r"\b(tells?|told|asks?|says?|said|explains?|replies|replied|admits?|adds?|notes?|"
    r"warns?|reminds?|assures?|informs?)\b",
    re.I,
)
_REPORT_COMPLEMENT_RE = re.compile(
    r"\b(that|how|why|what|whether|if|about|to\s+\w+|not\s+to)\b|[,:]", re.I
)
# English drops "that" freely: "explains he needs the money" is "explains THAT he needs
# the money" and is perfectly good reported speech. Without this the check flagged a
# correct beat, and a false positive here is not free — it sends a good beat to an LLM
# rewrite, which is how one ch1 beat came back shortened to a single sentence.



def lint_contentless_report(beats: list[ScriptBeat]) -> dict[int, list[str]]:
    """A reporting verb that reports nothing: "Kim Sangshik tells Bak."

    Tells him WHAT. These are syntactically complete, so repair_truncated_sentences
    passes them and every grammar checker calls them clean, yet they carry no
    information at all — the whole point of the sentence went missing. Two shipped in one
    ch1 draft ("Kim Sangshik tells Bak.", "Jin-Woo smiles weakly and tells Lee Joo-hee."),
    both produced by rewrites squeezing a reported line into a tight word budget.

    Detection is a complement test on the clause FOLLOWING the verb: real reported speech
    continues into that/how/why/whether/about/to-infinitive or a comma. Deliberately
    narrow — it only fires when the sentence ENDS within a few words of the verb, so
    "she tells him the truth" (a direct object that is genuinely the content) survives.
    """
    out: dict[int, list[str]] = {}
    for beat in beats:
        for sentence in _SENTENCE_SPLIT_RE.split(beat.narration.strip()):
            m = _REPORT_VERB_RE.search(sentence)
            if not m:
                continue
            tail = sentence[m.end():].strip(" .!?")
            if len(tail.split()) > 4 or _REPORT_COMPLEMENT_RE.search(tail):
                continue
            tail_words = tail.split()
            # Only a tail short enough to be a bare LISTENER is contentless: "tells Bak",
            # "tells Lee Joo-hee". Anything longer is a clause with its "that" dropped
            # ("explains he needs the money", "explains Rell stole the ledger") and is
            # real reported speech. Testing for a verb instead was tried and fails on
            # irregular pasts, the same suffix-check limitation documented at
            # _OBJECT_PREV_WORDS — and a false positive here is not free: it sends a good
            # beat to an LLM rewrite, which is how one ch1 beat came back shortened to a
            # single sentence.
            if len(tail_words) > 2 or any(_looks_like_verb(w) for w in tail_words):
                continue
            out.setdefault(beat.beat_id, []).append(
                f'"{sentence.strip()}" reports nothing — say WHAT was said, or cut the '
                "sentence and spend the words on the next event"
            )
    return out


_CLAUSE_BREAKERS = frozenset(
    """because that when while if since as and or but so though although before after
    until unless whether where which who from of in on at to with by for""".split()
)


# "A dejected he walks away" — a determiner and modifiers stranded on a pronoun, left
# behind when a name is swapped out of a premodified noun phrase.
_ARTICLE_PRONOUN_RE = re.compile(
    r"\b(a|an|the)\s+(?:[a-z][\w'’-]*\s+){0,2}(he|she|they|him|her|them)\b", re.I
)
# "A hunter and a hunter both shout" — two anonymous agents collapsed onto one descriptor.
_ECHOED_AGENT_RE = re.compile(r"\b(an?)\s+([a-z][\w'’-]*)\s*(?:,|\s+and)\s*(an?)\s+\2\b", re.I)
# The unambiguous sub-case: an article sitting DIRECTLY on a pronoun. No English
# sentence wants "The they" or "a him", the repair is mechanical (drop the article),
# and there is no noun-vs-adjective judgement to get wrong.
_BARE_ARTICLE_PRONOUN_RE = re.compile(r"\b(a|an|the)\s+(he|she|they|him|her|them)\b", re.I)


def stranded_determiner(text: str, *, strict: bool = False) -> re.Match | None:
    """`_ARTICLE_PRONOUN_RE` plus the two guards that make it safe to act on.

    The bare regex matches "A worker tells him that the gate is closed" — article, two
    words, pronoun — which is ordinary English with the pronoun as the OBJECT. That was
    tolerable while the only caller compared a rewrite's count against the original's
    (a false positive on both sides cancels), and became a bug the moment
    `lint_broken_sentences` started reporting it absolutely: a 5-chapter SL run was
    blocked by a correct sentence.

    Both guards already existed inline in `lint_malformed_phrases`; the newer callers
    each re-derived the raw regex without them. One definition now, so a detector and
    the gate that blocks on it cannot disagree about what the defect IS.

    `strict` narrows to the sub-case that can be decided without a POS tagger. With one
    or two words between the article and the pronoun, "A dejected he walks away" (broken)
    and "the moment he arrives" / "in a way she never expected" (ordinary reduced relative
    clauses) are the SAME token shape, and the verb-follows guard passes both — "arrives"
    ends in -s. That ambiguity is survivable for `narration_defects`, which only compares
    a rewrite's count against the original's so a symmetric false positive cancels; it is
    not survivable for a gate that blocks a run. So the blocking caller passes strict=True
    and sees only the bare form, and the ambiguous form stays advisory — reported for
    rewrite, never fatal. Widening the strict form needs a real tagger, not a longer regex.
    """
    # The bare form is a defect under both tiers, and it must be tested BEFORE the
    # verb-follows guard: "The they explain that ..." — the shape this detector was
    # written for — has a bare plural verb, which `_looks_like_verb` (built for -s/-ed/
    # -ing) rejects, so the guard was throwing away the very case it was guarding.
    bare = _BARE_ARTICLE_PRONOUN_RE.search(text or "")
    if bare or strict:
        return bare
    match = _ARTICLE_PRONOUN_RE.search(text or "")
    if not match:
        return None
    # A stranded determiner heads a SUBJECT, so a verb has to follow the pronoun.
    # "The healer treats him after the raid" — object pronoun, no verb after: clean.
    after = (text or "")[match.end():].split()
    if not after or not _looks_like_verb(after[0]):
        return None
    # A conjunction or preposition between determiner and pronoun means a new clause
    # started and the pronoun heads THAT one: "he is used to the pain because he is
    # weak". Only an unbroken determiner-modifier-pronoun run is wrong.
    if _CLAUSE_BREAKERS & {w.lower().strip(",") for w in match.group(0).split()}:
        return None
    return match


def lint_malformed_phrases(beats: list[ScriptBeat]) -> dict[int, list[str]]:
    """Two shapes that are grammatical enough to survive every other net.

    Both shipped in one ch1 draft, both out of REWRITES rather than the first pass, and
    neither is reproducible by any single polish step — which is the point: LanguageTool
    calls them clean, the malformed-opening gate only inspects a beat's first words, and
    the deterministic repairs each look at one construction.

      "A dejected he walks away from the coffee stall"  — the determiner and its modifier
      outlived the name they belonged to;
      "A hunter and a hunter both shout their agreement" — two anonymous agents flattened
      onto the same descriptor, so the sentence says nothing.

    Reported for rewrite rather than repaired: recovering "A dejected Jin-Woo" needs to
    know WHICH person, and inventing one is how a misattribution ships.
    """
    out: dict[int, list[str]] = {}
    for beat in beats:
        stranded = stranded_determiner(beat.narration)
        for match, why in (
            (stranded,
             "an article and its modifiers are stranded on a pronoun; name the person or "
             "drop the determiner"),
            (_ECHOED_AGENT_RE.search(beat.narration),
             "the same descriptor is used for two different people, so the sentence "
             "identifies nobody; distinguish them or name one"),
        ):
            if match:
                out.setdefault(beat.beat_id, []).append(f'"{match.group(0)}" — {why}')
    return out


# Category nouns. Each names a CLASS of thing rather than a thing, which is exactly the
# move that turns a panel fact into vapor: "his financial situation" for "my wife is
# pregnant", "his career path" for a job that gets him killed. Rule 7 already forbids this
# ("Concrete events only") and the model declines it, so it belongs here — the same
# reasoning that moved every other twice-declined rule into the deterministic pass.
_ABSTRACTION_NOUNS = frozenset(
    """situation situations circumstance circumstances condition conditions status
    matter matters issue issues problem problems case cases aspect aspects factor
    factors element elements nature thing things stuff path
    level levels degree extent reality experience experiences activity process
    processes state career careers detail details topic subject""".split()
)

# Function words and transcription noise: never useful as "the detail you dropped".
_UNINFORMATIVE = frozenset(
    """after already because become been being didn dont doesn wasn couldn wouldn
    shouldn about above again against along among around before below beneath beside
    between beyond during except inside into onto over since through toward under
    until upon within without with from that this these those they them their there
    here what when where which while will would could should have has had was were
    are our your you him her his she who whom whose then than each every some any
    much many more most other another such only just even also very really quite
    haha hahaha yeah yep nope huh hmm ahh ugh oh ow eh well okay yes not
    com net org www""".split()
)


def lint_abstraction_drift(
    beats: list[ScriptBeat],
    scene_cards: list[SceneCard] | None,
    *,
    min_dropped: int = 2,
) -> dict[int, list[str]]:
    """Flag a beat that swapped a panel's concrete fact for a category word.

    This is the "lifeless description" failure. The panels of Solo Leveling ch1 have a man
    explaining he came back to hunting because his wife is pregnant with their second son;
    the narration said his "financial situation got worse during his break". Nothing there
    is false, no gate fired, and the one human detail in the scene was gone. Same instinct
    produced "his highly dangerous career path" for a job that nearly kills him.

    Detection is a CONJUNCTION, and both halves are load-bearing. Retention alone is not
    the signal: the beat where a spear comes down scores 0.00 because its dialogue is
    grunts, and it is correctly narrated. An abstraction noun alone is not the signal
    either — sometimes there is nothing more specific available. The defect is a category
    word standing in a beat whose own panels supplied specifics that never made it.

    Reports the dropped specifics rather than a score, because "too abstract" is not
    actionable and "the panels say wife, pregnant, son" is. Ranked by length as a rough
    proxy for informativeness — there is no POS tagger here, and a wrong ordering costs a
    less helpful hint, never a wrong edit.
    """
    if not scene_cards:
        return {}
    from manhwa2vid.script.grounding import split_utterances

    by_panel: dict[str, str] = {}
    for card in scene_cards:
        for pid in card.panel_ids:
            by_panel[pid] = card.source_text or ""

    out: dict[int, list[str]] = {}
    for beat in beats:
        narration_stems = _stemmed_words(beat.narration)
        # A gerund before the noun makes it a COMPOUND, not a category reference:
        # "the gate gathering point" is a place, "his financial situation" is a category
        # standing where a fact belongs. Without this the check flagged a correct beat.
        words = [w.lower().strip(".,!?;:'\"") for w in beat.narration.split()]
        abstractions = sorted(
            {
                w for i, w in enumerate(words)
                if w in _ABSTRACTION_NOUNS
                and not (i and words[i - 1].endswith("ing"))
            }
        )
        if not abstractions:
            continue
        spoken: list[str] = []
        for pid in beat.panel_ids:
            addressed, monologue, unowned = split_utterances(by_panel.get(pid, ""))
            spoken += [ln.split(":", 1)[-1] for ln in addressed + monologue + unowned]
        if not spoken:
            continue
        dropped = [
            w for w in (_stemmed_words(" ".join(spoken)) - narration_stems)
            if w not in _UNINFORMATIVE and len(w) > 3
        ]
        if len(dropped) < min_dropped:
            continue  # nothing specific was available to keep
        dropped.sort(key=lambda w: (-len(w), w))
        out[beat.beat_id] = [
            f"narration reaches for {abstractions} where this beat's own panels say "
            f"{dropped[:6]} — name the specific fact instead of its category"
        ]
    return out


def lint_missing_introduction(
    beats: list[ScriptBeat],
    bible: SeriesBible | None,
) -> dict[int, list[str]]:
    """The other half of rule 4: a named character must be introduced ONCE — at least.

    lint_reintroduction has always enforced the ceiling (no appositive after the first)
    and nothing enforced the floor, so characters kept walking into the script as bare
    names. ch1 has done it to a different person on three separate runs — Bak once, Song
    Chi-yul in the current draft, where a listener meets "He tells Song Chi-yul that there
    are no objections" having never been told who that is or why his opinion settles
    anything.

    Accepts either shape the style actually uses:
        "Song Chi-yul, the raid leader, steps forward"   (appositive)
        "the raid leader Song Chi-yul steps forward"     (premodifier)

    The protagonist is exempt — the hook and the anchor cadence establish them, and rule 4
    separately budgets how often their name recurs. Characters whose canonical_name is
    itself a descriptor ("the coffee vendor") are exempt too: they arrive self-describing,
    and demanding a role clause for them produces "the coffee vendor, a vendor".
    """
    if bible is None:
        return {}
    out: dict[int, list[str]] = {}
    from manhwa2vid.characters.bible import sanitize_role

    for profile in bible.characters.values():
        if profile.merged_into or profile.id == bible.protagonist_id:
            continue
        if profile.tier not in (CharacterTier.MAIN, CharacterTier.SUPPORTING):
            continue
        name = profile.canonical_name.strip()
        if not name or is_descriptor_label(name):
            continue
        appositive = re.compile(
            rf"\b{re.escape(name)},\s+(?:a|an|the|his|her|their)\s+[^,.;!?]+[,.]", re.I
        )
        premodifier = re.compile(
            rf"\b(?:a|an|the)\s+(?:[\w'’-]+\s+){{0,4}}{re.escape(name)}\b", re.I
        )
        first_beat = None
        for beat in beats:
            if not re.search(rf"\b{re.escape(name)}\b", beat.narration, re.I):
                continue
            if first_beat is None:
                first_beat = beat
            if appositive.search(beat.narration) or premodifier.search(beat.narration):
                first_beat = None  # introduced somewhere; the ceiling lint owns the rest
                break
        if first_beat is not None:
            role = sanitize_role(profile.role) or "their role in this scene"
            out.setdefault(first_beat.beat_id, []).append(
                f"{name} is named here for the first time with no introduction — a "
                f"listener has never met them. Give the first mention a short role clause "
                f"(\"{name}, {role},\") and leave later mentions bare"
            )
    return out


def lint_narration_order(
    beats: list[ScriptBeat],
    scene_cards: list[SceneCard] | None,
    *,
    min_match: float = 0.10,
    min_gap: int = 2,
) -> dict[int, list[str]]:
    """Flag a beat whose sentences do not run in its panels' reading order.

    `grounding.enforce_reading_order` guarantees the invariant at BEAT level and nothing
    checked it below that, so a beat could narrate its last panel first: ch1 beat 12
    opened on a leader addressing the party (its final panel) and only then gave the
    conversation from its first four. Read aloud over those panels the words describe one
    moment while the art shows another.

    `lock_transition_line` already ASSUMES this ordering — it converts a panel index into
    a sentence index to place the rewind cue — and asserted it in a comment without
    anything verifying it. This is that verification.

    Scored by argmax, deliberately, NOT by `derive_key_panels`' 0.18 threshold: that
    number is normalized by a panel's token count and calibrated for whole-beat
    narration, so a single sentence scored the same way sits far below it and every
    sentence would look unmatched. Sentences that match nothing (connective or scene-
    setting lines with no panel content of their own) are skipped rather than counted at
    index 0, where they would manufacture inversions out of correct prose.

    Reported for rewrite, never reordered in place. Sentences carry connective tissue
    ("Behind him,", "Suddenly,") that silently breaks when moved, and nothing in this
    module reorders prose today — every existing pass filters or substitutes and rejoins
    in the original order.
    """
    if not scene_cards:
        return {}
    by_panel: dict[str, str] = {}
    for card in scene_cards:
        for pid in card.panel_ids:
            by_panel[pid] = f"{card.source_text or ''} {card.action or ''}"

    out: dict[int, list[str]] = {}
    for beat in beats:
        if len(beat.panel_ids) < 2:
            continue
        sentences = [s for s in _SENTENCE_SPLIT_RE.split(beat.narration.strip()) if s.strip()]
        if len(sentences) < 2:
            continue
        seq: list[tuple[int, str]] = []
        for sentence in sentences:
            stems = _stemmed_words(sentence)
            best_i, best_score = None, 0.0
            for i, pid in enumerate(beat.panel_ids):
                panel_stems = _stemmed_words(by_panel.get(pid, ""))
                if not panel_stems:
                    continue
                score = len(stems & panel_stems) / len(panel_stems)
                if score > best_score:
                    best_i, best_score = i, score
            if best_i is not None and best_score >= min_match:
                seq.append((best_i, sentence))
        # An ADJACENT swap is not evidence of anything. Lexical matching cannot resolve
        # neighbouring panels — a scene-setting or monologue sentence routinely scores
        # higher against the next panel than its own — and two consecutive panels are
        # about 2.5s apart on screen, which no viewer perceives as out of order. The
        # observed real defect told a sentence from the END of a five-panel beat before
        # one from its start: a gap of 3. Requiring a gap removes three false positives
        # measured on a later ch1 draft while keeping that case.
        inversions = [
            (seq[a], seq[b])
            for a in range(len(seq))
            for b in range(a + 1, len(seq))
            if seq[a][0] - seq[b][0] >= min_gap
        ]
        if inversions:
            (early_i, early_s), (late_i, late_s) = inversions[0]
            out[beat.beat_id] = [
                f'narration runs out of panel order: "{early_s.strip()[:70]}" belongs to '
                f"panel {beat.panel_ids[early_i]} but is told before "
                f'"{late_s.strip()[:70]}", which belongs to the earlier panel '
                f"{beat.panel_ids[late_i]}. Narrate this beat's panels in reading order"
            ]
    return out


# Its own regex on purpose. _PRONOUN_START_RE exists TWICE with different semantics —
# lint.py's is case-sensitive and includes possessives, scorecard.py's is case-insensitive,
# includes "it" and excludes possessives — so importing either by name invites the wrong
# one. This needs exactly third-person personal SUBJECTS at a sentence start.
_OPENING_PRONOUN_RE = re.compile(r"^\s*(?:He|She|They)\b")


def lint_unanchored_opening(
    beats: list[ScriptBeat],
    bible: SeriesBible | None,
) -> dict[int, list[str]]:
    """Flag a beat that opens on a pronoun and never names who it means.

    ch1 beat 14 was "He replies quickly to reassure her, steeling his resolve..." — the
    beat contains no proper noun at all, `He` was last named two beats earlier among three
    men, and `her` two beats earlier. On the page a reader can glance back; a listener
    cannot, and the beat boundary is also a panel cut and often a pause.

    Nothing existing catches this. `enforce_mc_name_budget` forces an anchor only when a
    same-pronoun RIVAL is named in that beat (lint.py, `_same_pronoun_rivals`), so a beat
    naming nobody never trips it — and that function can only remove names, never add one.
    `scorecard._pronoun_start_fraction` averages every sentence script-wide and is
    warn-only. So this is a genuine gap, not a duplicate.

    Reported for rewrite rather than repaired: choosing the referent wrongly would ship a
    misattribution, the costliest error class in this pipeline. The message names the
    rivals that make the pronoun ambiguous so the rewriter has to resolve it explicitly.
    """
    out: dict[int, list[str]] = {}
    if bible is None:
        return {}
    known: list[str] = []
    for profile in bible.characters.values():
        if profile.merged_into:
            continue
        name = profile.canonical_name.strip()
        if name and not is_descriptor_label(name):
            known.append(name)
    if not known:
        return {}
    rivals = _same_pronoun_rivals(bible)

    def _names_in(text: str, pool: list[str]) -> list[str]:
        return [
            n for n in pool
            if re.search(rf"\b{re.escape(_short_name_form(n))}\b", text, re.I)
            or re.search(rf"\b{re.escape(n)}\b", text, re.I)
        ]

    for i, beat in enumerate(beats):
        text = beat.narration.strip()
        if not _OPENING_PRONOUN_RE.match(text):
            continue
        if _names_in(text, known):
            continue  # the beat names somebody; the anchor lints own the rest
        # A bare pronoun is only AMBIGUOUS when a same-pronoun rival is live. "He checks
        # his pack" after a beat that named only the protagonist is ordinary prose, and
        # flagging it fought `enforce_mc_name_budget`'s cadence — the lint demanded a
        # name, the budget rotated it out, and the beat could never satisfy both. The
        # observed defect always had rivals in play: "He replies quickly to reassure her"
        # followed a beat naming three other men.
        live = _names_in(beats[i - 1].narration, rivals) if i else []
        if not live:
            continue
        opening = text.split()[0]
        out[beat.beat_id] = [
            f'this beat opens on "{opening}" and never names anyone in it, but the beat '
            f"before it named {', '.join(live[:3])} — a listener cannot tell who is "
            f"acting. Name the person in the first sentence"
        ]
    return out


_NAME_TOKEN_RE = re.compile(r"^[A-Z][\w'’-]*[.!?]?$")


def _is_bare_name_sentence(sentence: str) -> bool:
    """A short sentence made only of capitalised name tokens, with no verb.

    Kept narrow on purpose: "Silence." and "Not this time." must survive, so a token has
    to be capitalised AND the sentence must carry nothing verb-shaped. "Sung Jin-Woo." is
    two tokens and qualifies; "Silence." is one token but is checked for verb-shape and,
    more importantly, is a common noun the writer chose — the cost of losing a rare
    intentional name-beat is one flat sentence, against shipping a dead stub as audio.
    """
    words = sentence.split()
    if not words or len(words) > 3:
        return False
    if any(_looks_like_verb(w) for w in words):
        return False
    if not all(_NAME_TOKEN_RE.match(w) for w in words):
        return False
    # A single common-noun beat ("Silence.", "Darkness.") is deliberate; require either a
    # multi-token name or an internal hyphen/apostrophe, which a one-word noun lacks.
    return len(words) > 1 or bool(re.search(r"[-’\']", words[0]))


def sentence_fragments(text: str, *, min_words: int = 3) -> list[str]:
    """Sentences carrying no verb at all — "Jin-Woo and Lee Joo-hee."

    Not reachable by lint_malformed_opening, which only asks whether the first character
    is lowercase, so a capitalised fragment passes every existing check and is then spoken
    aloud as a dead stub.

    `min_words` keeps one- and two-word sentences out of it: those are deliberate beats
    ("Silence." / "Not this time.") and the present-tense register means a real clause
    almost always carries an -s/-ed/-ing verb that _looks_like_verb catches.
    """
    out: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split((text or "").strip()):
        words = sentence.split()
        if len(words) < min_words:
            # ...with one exception. The min_words carve-out exists for a deliberate
            # one-word beat ("Silence."), and those are COMMON nouns. A sentence that is
            # nothing but a proper name — "Ju-Hee." / "Sung Jin-Woo." — is never a
            # stylistic choice in this register; it is a clause whose verb phrase was
            # deleted by a polish pass, and it gets SPOKEN as a dead stub. Two shipped in
            # one 5-chapter run, both invisible to every check because of this branch.
            if _is_bare_name_sentence(sentence):
                out.append(sentence.strip())
            continue
        if any(_looks_like_verb(w) for w in words):
            continue
        # _looks_like_verb is a suffix test, so it misses bare present-tense forms that a
        # plural or pronoun subject takes: "They trust Rell", "Hunters gather at the gate".
        # Treat any lowercase non-function word after the first token as a possible verb —
        # a real bare noun phrase ("Jin-Woo and Lee Joo-hee.") has none, because its only
        # lowercase words are conjunctions and determiners. Precision over recall: missing
        # a fragment reads slightly off, while a false one makes accept_rewrite discard a
        # good rewrite.
        if any(
            w[:1].islower() and w.strip(".,!?;:'\"").lower() not in _FUNCTION_WORDS
            for w in words[1:]
        ):
            continue
        out.append(sentence.strip())
    # The two detectors overlap on the plainest case ("Nearby, Kim Sangshik, Bak."),
    # and a defect counted twice would make accept_rewrite reject a rewrite that
    # merely left it alone.
    return list(dict.fromkeys([*out, *_trailing_name_list_fragments(text)]))


# "Near the entrance, Kim Sangshik, Bak." — the same dead stub as "Nearby, Kim Sangshik,
# Bak.", but one ordinary lowercase noun ("entrance") is enough to satisfy the
# possible-verb heuristic above and the whole sentence is waved through. That heuristic
# is deliberately precision-favouring and stays as it is; this catches the specific shape
# it cannot: a sentence ENDING in two or more comma-separated capitalised names, with no
# verb-looking word anywhere in it.
_TRAILING_NAMES_RE = re.compile(
    r"(?:^|,)\s*[A-Z][\w'’-]*(?:[- ][A-Z][\w'’-]*)*\s*,\s*"
    r"[A-Z][\w'’-]*(?:[- ][A-Z][\w'’-]*)*\s*[.!?]\s*$"
)


def _trailing_name_list_fragments(text: str) -> list[str]:
    out: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split((text or "").strip()):
        sent = sentence.strip()
        if not sent or not _TRAILING_NAMES_RE.search(sent):
            continue
        if any(_looks_like_verb(w) for w in sent.split()):
            continue
        out.append(sent)
    return out


# A speech verb that names its listener and then stops, never saying WHAT was said:
# "Jin-Woo offers a weak smile, telling Lee Joo-hee." The sentence has a main verb, so
# sentence_fragments correctly passes it — the hole is semantic, not syntactic. Requires
# a capitalised name (or pronoun) directly before the terminator, so ordinary intransitive
# uses survive: "Bak complains to Kim Sangshik." keeps its preposition, and "He explains."
# is a bare verb with no stranded listener.
_TRUNCATED_SPEECH_RE = re.compile(
    r"\b(?:telling|tells|told|asking|asks|saying|says|replying|replies|"
    r"answering|answers|admitting|admits|warning|warns|reminding|reminds)\s+"
    # An honorific is followed by a period that is NOT a sentence terminator, so
    # "Bak asks Mr. Kim if Jin-Woo is coming" matched on "asks Mr." and flagged a
    # complete sentence. Same class of bug as _SENTENCE_SPLIT_RE splitting on "Mr.".
    r"(?!(?:Mr|Mrs|Ms|Dr|St|Jr|Sr)\b)"
    r"(?:him|her|them|it|[A-Z][\w'’-]*(?:[- ][A-Z][\w'’-]*)*)\s*[.!?]",
)


#: The speech verb + content-clause shape that proves something WAS said: "explains that",
#: "asks whether", "tells him to", "warns her about". If one of these precedes a
#: trailing "telling him." in the same sentence, the trailing verb is a motive clause,
#: not a hole.
_SPEECH_WITH_CONTENT_RE = re.compile(
    r"\b(?:explain|say|tell|ask|admit|repl|answer|warn|remind|note|state|insist|"
    r"claim|add|mention|point|confirm|declare|report|argue|suggest|promise|complain)"
    r"\w*\s+(?:(?:him|her|them|it|[A-Z][\w'’-]*)\s+)?"
    r"(?:that|whether|if|to|about|how|why|what|where|when)\b",
)

#: Subordinators that turn a trailing speech verb into a reason, not a report:
#: "which is why she is telling him", "because he keeps asking her".
_MOTIVE_LEAD_RE = re.compile(
    r"\b(?:which is why|that is why|that's why|because|so that|before|after|while|"
    r"without|instead of|rather than|despite|keeps?|kept|stops?|stopped)\s+"
    r"(?:\w+\s+){0,4}$",
)


def is_truncated_speech(sentence: str) -> bool:
    """A speech verb naming its listener with nothing said — and NOTHING ELSE.

    The regex alone fired on the 20-chapter probe's beat 342, "Then she explains that
    the Association probably doesn't know yet, which is why she is telling him." —
    a complete sentence whose trailing "telling him" is the reason for the report, not
    a report with the content missing. At 1021 sentences a rare false positive in a
    BLOCKING gate is a near-certain block, so the two shapes that make a trailing
    speech verb legitimate are excluded: a content clause earlier in the sentence
    ("explains that…"), or a motive subordinator directly before the verb.
    """
    m = _TRUNCATED_SPEECH_RE.search(sentence)
    if not m:
        return False
    before = sentence[: m.start()]
    if _SPEECH_WITH_CONTENT_RE.search(before):
        return False
    if _MOTIVE_LEAD_RE.search(before + " "):
        return False
    return True

# "They grit his teeth." — a plural subject carrying a singular possessive for the same
# person. Narrow by construction: subject pronoun, then a short verb-and-modifier span
# with no second subject in it, then a gendered possessive.
#
# Prepositions are excluded along with the conjunctions: a possessive inside a
# prepositional phrase belongs to whoever the PP is about, not to the sentence's
# subject, so "Song admits there is nothing they can do for his missing arm" is
# correct English about two different people. That sentence blocked a whole Solo
# Leveling script stage. The direct-object construction this gate is actually for
# ("They grit his teeth") never crosses a preposition.
#
# The trade is deliberate: recall drops — "They look at his teeth" about one person is
# no longer caught — and precision matters more here because the gate BLOCKS, and
# because the plural reading of a PP is usually the correct one.
_MIXED_NUMBER_STOP = (
    "and", "or", "but", "while", "as",
    "for", "to", "with", "about", "from", "at", "on", "in", "of", "into",
    "against", "toward", "towards", "around", "over", "under", "near", "behind",
    "beside", "through", "across", "beyond", "onto", "upon",
)
#: What the possessive has to own for "They ... his" to be a NUMBER error rather than
#: two people in one sentence. The defect is one character called "they" and "his" in
#: the same breath, and the tell is that the thing possessed is inalienably their own —
#: "They grit his teeth", "They clench his fists". When the possessive owns something
#: separable ("They trust his skills", "They raise his banner") the plural reading is
#: not just possible, it is the ordinary one.
_SELF_POSSESSION = (
    "teeth|fists?|hands?|head|forehead|jaw|chin|temples?|chest|shoulders?|brow|eyes?|"
    "arms?|legs?|fingers?|knuckles?|throat|neck|face|breath|grip|stomach|gut|heart|"
    "lips|mouth|nose|ears?|hair|skin|spine|ribs?|wrists?|elbows?|knees?|feet|foot|"
    "palms?|thumbs?|tongue|body|blood|voice"
)
_MIXED_NUMBER_RE = re.compile(
    r"\bThey\b(?:\s+(?!" + "|".join(rf"{w}\b" for w in _MIXED_NUMBER_STOP)
    + r")[\w'’-]+){1,3}\s+(his|her)\s+(?:" + _SELF_POSSESSION + r")\b",
    re.I,
)


def mixed_number_pronouns(text: str) -> list[str]:
    """Sentences that call one person "they" and then "his"/"her" in the same breath.

    Not a style nit — it is the audible symptom of a character whose bible pronoun never
    resolved, and it reached a rendered 5-chapter script nine times ("They grit his
    teeth", "They look ... his"). Every existing check passed it: the sentence is
    grammatical in isolation, carries a verb, and neither the fragment nor the
    stranded-determiner detectors model agreement.

    Detection only. The repair is to fix the PRONOUN in the bible — rewriting the
    narration would paper over a wrong profile that the next chapter re-uses.

    NARROWED TWICE, both times because it blocked correct narration — this gate blocks,
    so a false positive stops a script stage dead:

      1. across a preposition: "Song admits there is nothing they can do for his missing
         arm" (they = the healers, his = Jin-Woo);
      2. on a separable possession: "The group readily agrees. They trust his skills."
         (they = the party, his = Mr. Song) — a direct object, so the first narrowing
         did not reach it.

    What survives is the shape the gate was built for and nothing wider: "they" and a
    possessive of something INALIENABLY that person's own (`_SELF_POSSESSION`). It
    cannot be made fully precise — "They raise his sword" is ambiguous to any regex and
    is deliberately not flagged, because the cost of a false positive here is a blocked
    pipeline and the cost of a miss is one audible sentence.
    """
    hits: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split((text or "").strip()):
        sent = sentence.strip()
        if sent and _MIXED_NUMBER_RE.search(sent):
            hits.append(sent[:80])
    return hits


def lint_broken_sentences(beats: list[ScriptBeat]) -> dict[int, list[str]]:
    """Every sentence in a beat, not just its first — the gap that shipped two dead
    stubs into a rendered video.

    `sentence_fragments` already detected "Nearby, Kim Sangshik, Bak." perfectly well.
    The problem was that nothing ever ASKED it about finished narration: it is reachable
    only through `narration_defects`, which is used in exactly one place —
    `accept_rewrite` — and there only as a RELATIVE count, rewrite versus original. A
    fragment the writer produced in a beat that no rewrite happened to touch was
    therefore never examined, and the one absolute gate on well-formedness,
    `lint_malformed_opening`, inspects a beat's FIRST sentence only.

    So this is not a new detector. It is the existing detector, finally applied to the
    whole beat, plus the one shape it structurally cannot see: a speech verb that names
    its listener and never says what was said.
    """
    report: dict[int, list[str]] = {}
    for beat in beats:
        issues = [f"fragment: {s[:60]}" for s in sentence_fragments(beat.narration)]
        for sent in _SENTENCE_SPLIT_RE.split(beat.narration.strip()):
            sent = sent.strip()
            if is_truncated_speech(sent):
                issues.append(f"truncated_speech: {sent[:60]}")
            # "The they explain that the other hunters held higher ranks" shipped in a
            # 5-chapter run. _ARTICLE_PRONOUN_RE has always detected this, but only
            # through narration_defects — i.e. only as a RELATIVE count inside
            # accept_rewrite — so a stranded determiner the writer produced in a beat no
            # rewrite touched was never examined. Same omission as the fragment case.
            if stranded_determiner(sent, strict=True):
                issues.append(f"stranded_determiner: {sent[:60]}")
        # Number disagreement on one person ("They grit his teeth"). Blocking, because
        # the cause is a bible pronoun that never resolved and the fix belongs THERE —
        # a run that ships this is narrating a character it cannot correctly refer to.
        issues += [f"mixed_number: {h}" for h in mixed_number_pronouns(beat.narration)]
        if issues:
            report[beat.beat_id] = issues
    return report


def narration_defects(text: str) -> list[str]:
    """Cheap deterministic defects in one narration string, for comparing two candidates.

    Used to guarantee a REWRITE does no harm. Every rewrite path here hands an LLM a
    defect to fix and accepts whatever comes back, and the damage that causes is now
    documented three times over: a beat came back shortened from three sentences to one,
    and beat 12 of ch1 came back as "Jin-Woo and Lee Joo-hee. He murmurs a quiet greeting,
    and he simply nods back" — a fragment, two unresolvable pronouns, and the raid leader
    the beat existed to introduce deleted outright. The model's ORIGINAL text for that
    beat was clean.

    The pairwise judge was supposed to be the backstop and returned "undecided", whose
    default is to keep the rewrite. That default is defensible for a coherent rewrite and
    indefensible for a malformed one, so well-formedness is settled here — deterministically
    and before the judge is ever consulted.
    """
    defects: list[str] = []
    defects += [f"fragment: {s[:60]}" for s in sentence_fragments(text)]
    # A speech verb that names its listener and never says what was said. Added after a
    # rewrite reintroduced "Jin-Woo smiles weakly and tells Lee Joo-hee." into a beat the
    # story-integrity round had already cleaned: the shape was checked by
    # lint_broken_sentences at the END of the run but was invisible HERE, so every
    # accept_rewrite in the pipeline let a rewrite add one for free.
    defects += [
        f"truncated_speech: {sent.strip()[:60]}"
        for sent in _SENTENCE_SPLIT_RE.split((text or "").strip())
        if is_truncated_speech(sent.strip())
    ]
    stripped = (text or "").strip()
    if stripped and stripped.split() and stripped.split()[0][:1].islower():
        defects.append("opens mid-sentence")
    if stranded_determiner(text or ""):
        defects.append("stranded determiner on a pronoun")
    if _ECHOED_AGENT_RE.search(text or ""):
        defects.append("same descriptor for two people")
    return defects


def accept_rewrite(original: str, rewritten: str) -> str:
    """Take a rewrite only when it introduces no NEW deterministic defect.

    A rewrite is aimed at a named defect, so it earns the benefit of the doubt on content
    — that judgement belongs to the pairwise judge, which can see the panels. It does not
    earn the benefit of the doubt on well-formedness, which is decidable here for free.
    Equal counts keep the rewrite; strictly worse keeps the original.
    """
    if not (rewritten or "").strip():
        return original
    if len(narration_defects(rewritten)) > len(narration_defects(original)):
        return original
    return rewritten


def restore_lost_required_lines(
    beats: list[ScriptBeat],
    verified: dict[int, str],
    required_by_beat: dict[int, list[str]],
    *,
    min_ratio: float = 0.3,
) -> tuple[list[ScriptBeat], dict[int, list[str]]]:
    """Put back any beat that LOST a required line somewhere downstream.

    The one choke point for a bug class that has now appeared five separate times in this
    pipeline, each time in a different pass, each time invisible because every individual
    step looked locally reasonable:

      1. `trim_overlong_beats` popping a just-landed payoff off the tail (panel-count cap)
      2. `rewrite_voice` stripping system messages in the name of rhythm
      3. the alignment audit rewriting a beat and dropping its system line
      4. `strip_trailing_closer_sentence` deleting a forward thesis
      5. the quote scanner losing lines before anything even asked for them

    Guarding each pass individually loses: three were fixed that way and a fourth
    appeared immediately. `accept_rewrite` cannot cover it either, because it only
    compares WELL-FORMEDNESS between two candidates and knows nothing about which lines
    the beat is obliged to carry.

    So this runs LAST, over the shipped text, against a snapshot taken at the point where
    required lines were last verified. Per beat: if the shipped version lands fewer
    required lines than the snapshot did, the snapshot wins. Any future pass is covered
    automatically, including ones not written yet.

    Returns the reconciled beats and a report of what was restored, so a silent revert is
    impossible — a beat needing this means some pass upstream is still lossy and should
    be fixed at its source.
    """
    def landed(text: str, lines: list[str]) -> set[str]:
        tokens = _stemmed_words(text)
        out: set[str] = set()
        for line in lines:
            lt = _stemmed_words(line)
            if lt and len(lt & tokens) / len(lt) >= min_ratio:
                out.add(line)
        return out

    restored: dict[int, list[str]] = {}
    out_beats: list[ScriptBeat] = []
    for beat in beats:
        prior = verified.get(beat.beat_id)
        req = required_by_beat.get(beat.beat_id) or []
        if not prior or not req:
            out_beats.append(beat)
            continue
        had, now = landed(prior, req), landed(beat.narration, req)
        lost = had - now
        if lost:
            restored[beat.beat_id] = sorted(lost)
            out_beats.append(beat.model_copy(update={"narration": prior}))
        else:
            out_beats.append(beat)
    return out_beats, restored


def keeps_landed_lines(
    original: str,
    rewritten: str,
    required: list[str],
    *,
    min_ratio: float = 0.3,
) -> bool:
    """Did the rewrite keep every required line the ORIGINAL had already landed?

    A rewrite aimed at DELIVERY must not cost CONTENT. The voice pass rewrote three
    Frozen Player beats that were carrying their system messages correctly and handed
    back versions without them — beats 16, 21 and 26 passed the dialogue-delivery retry
    and then failed the final gate, having been "re-delivered" in between. Same defect
    class as trim_overlong_beats deleting a landed payoff: a later pass undoing an
    earlier pass's work, invisible because each step looked locally reasonable.

    Only lines the original ACTUALLY landed are protected — this never demands that a
    rewrite fix something the original was already failing, which is the corrective
    loop's job, not this guard's. Uses the same stemmed-overlap test as
    `lint_dropped_dialogue`, so the guard and the gate agree by construction.
    """
    if not required:
        return True
    orig_tokens = _stemmed_words(original)
    new_tokens = _stemmed_words(rewritten)
    for line in required:
        tokens = _stemmed_words(line)
        if not tokens:
            continue
        had = len(tokens & orig_tokens) / len(tokens) >= min_ratio
        if had and len(tokens & new_tokens) / len(tokens) < min_ratio:
            return False
    return True


def ensure_first_mention_role(
    beats: list[ScriptBeat],
    bible: SeriesBible | None,
) -> list[ScriptBeat]:
    """Insert the role clause at a character's FIRST mention, deterministically.

    The exact inverse of `strip_repeated_appositives`, which already performs mechanical
    appositive REMOVAL — same machinery, same risk profile, opposite direction. Rule 4 has
    two halves and the ceiling was enforced in code while the floor was left to the prompt,
    which declined it across three separate runs: a named character kept walking into the
    script cold, and the last one had to be fixed by hand.

    The role comes from the bible through `sanitize_role`, so it can never be a tier word
    ("a supporting hunter"). Skipped whenever the surrounding text is not a plain first
    mention — a possessive ("Song Chi-yul's skills"), a name already followed by a comma
    (it may already carry its clause), or a name inside an existing appositive. Skipped
    entirely when no role is known, because inventing one is how a misattribution ships.

    Only ever inserts at the FIRST occurrence in the script; `lint_reintroduction` and
    `strip_repeated_appositives` continue to own every later mention, which is why this
    runs before them in the polish chain.
    """
    if bible is None:
        return beats
    from manhwa2vid.characters.bible import sanitize_role

    roles: dict[str, str] = {}
    for profile in bible.characters.values():
        if profile.merged_into or profile.id == bible.protagonist_id:
            continue
        if profile.tier not in (CharacterTier.MAIN, CharacterTier.SUPPORTING):
            continue
        name = profile.canonical_name.strip()
        role = sanitize_role(profile.role)
        if name and role and not is_descriptor_label(name):
            # Bible roles are stored bare ("raid leader"); narration needs the article,
            # and lint_missing_introduction's appositive pattern requires one too.
            # Roles are stored however the bible captured them — "The final boss of the
            # Antarctic dungeon" arrived title-cased and shipped as "the Frost Queen, The
            # final boss...". An inserted appositive always sits mid-sentence, so its
            # first letter is lowercase unless the role opens on a proper noun.
            if re.match(r"^(?:a|an|the|his|her|their)\s", role, re.I):
                head, rest = role.split(" ", 1)
                role = f"{head.lower()} {rest}"
            else:
                role = f"the {role[0].lower()}{role[1:]}" if role[:1].isupper() and not role.split()[0].isupper() else f"the {role}"
            roles[name] = role

    if not roles:
        return beats

    introduced: set[str] = set()
    used_roles: set[str] = set()
    # Pre-scan: a character already introduced ANYWHERE keeps that introduction and never
    # gets a second one inserted.
    #
    # Both shapes count, which lint_missing_introduction also accepts and an earlier
    # version of this function did not: the appositive "Kim Sangshik, a veteran hunter,"
    # and the premodifier "Veteran hunter Kim Sangshik". Missing the second shipped
    # "Veteran hunter Kim Sangshik, the hunter, grabs a warm drink" — introduced twice in
    # four words. The test is the role's own head noun appearing near the name, which
    # catches both without needing to parse either.
    role_heads = {name: role.split()[-1].lower() for name, role in roles.items() if role.split()}
    for beat in beats:
        for name in roles:
            head = role_heads.get(name, "")
            # The window must span a full appositive: "Skaya, a member of the original
            # five heroes" runs 32 characters between name and head noun, and a 20-char
            # window missed it — so Skaya was never marked introduced and her clause was
            # inserted AGAIN at her next bare mention. 48 covers every observed clause
            # while staying too short to bridge into a neighbouring sentence.
            if head and re.search(
                rf"(?:\b{re.escape(head)}\b[\w\s'’-]{{0,48}}?\b{re.escape(name)}\b"
                rf"|\b{re.escape(name)}\b[\w\s'’,-]{{0,48}}?\b{re.escape(head)}\b)",
                beat.narration, re.I,
            ):
                introduced.add(name)
                # And their role is now TAKEN. Without this, four teammates sharing the
                # bible role "member of the five heroes" got the clause stamped onto a
                # second character because the first carried it from the writer, not
                # from this function — used_roles only learned what IT inserted.
                used_roles.add(roles[name])

    out: list[ScriptBeat] = []
    for beat in beats:
        text = beat.narration
        for name in roles:
            if name in introduced:
                continue
            # Plain mention only. A following COMMA is skipped (the name may already
            # carry a clause) and so is a possessive, but a sentence-final mention is
            # fine: "They trust Song Chi-yul." -> "They trust Song Chi-yul, the raid
            # leader." is exactly the introduction rule 4 asks for.
            m = re.search(rf"\b{re.escape(name)}\b(?![\u2019']s\b)(?!\s*,)", text)
            if not m:
                continue
            # A clause closes with a comma mid-sentence and with nothing at a sentence
            # end, where the existing terminator does the job — otherwise ", the raid
            # leader,." ships.
            tail = text[m.end():]
            closer = "" if tail[:1] in {".", "!", "?", ";", ":"} or not tail.strip() else ","
            # A role that does not DISTINGUISH is not an introduction. Both supporting
            # hunters in Solo Leveling ch1 carry the bare role "hunter", and inserting it
            # for each produced "Kim Sangshik, a hunter, ... Bak, the hunter, calls out
            # his name" in one beat — repetitive and no more informative than the bare
            # names. The first character to claim a role keeps it; later ones are left
            # alone, and lint_missing_introduction still reports them so the gap stays
            # visible rather than being papered over with a duplicate.
            if roles[name] in used_roles:
                continue
            used_roles.add(roles[name])
            text = f"{text[:m.end()]}, {roles[name]}{closer}{tail}"
            introduced.add(name)
        out.append(beat.model_copy(update={"narration": text}) if text != beat.narration else beat)
    return out


_SUBJECT_PRONOUN_RE = re.compile(r"\b(he|she|they)\b", re.I)
def mc_acts_unnamed(beat: ScriptBeat, bible: SeriesBible | None) -> bool:
    """The protagonist acts in this beat through a pronoun and is never named in it.

    Shipped on Frozen Player: "The presenter introduces the frozen figures as the five
    heroes. When a schoolboy points out a moving statue, HE shatters his icy prison."
    The beat's cast contains the protagonist, the narration never names him, and the
    nearest antecedent a listener has is the schoolboy — so nobody watching could tell who
    broke out of the ice. Every lint was green on that beat.

    Cast membership is the signal, not pronoun agreement: bibles carry wrong pronouns
    often enough (this title records two women as "he") that a pronoun-matched rule fires
    on garbage. Nor can the OTHER people be identified from the prose — the presenter's
    canonical name in that bible is "man in a black suit with black hair", so neither a
    name match nor a "the <noun> <verb>" regex finds them; the regex version read "the
    frozen statues" as a person doing something.

    Shared by the repair (`enforce_mc_name_budget`) and the gate
    (`lint_ambiguous_pronoun`) so the two can never disagree — the loop where a lint
    demands a name and the name budget rotates it straight back out has already cost this
    project two rounds.
    """
    if bible is None or not beat.character_ids:
        return False
    mc = bible.characters.get(bible.protagonist_id or "")
    if mc is None or bible.protagonist_id not in beat.character_ids:
        return False
    name = mc.canonical_name.strip()
    if not name:
        return False
    if not _OPENING_PRONOUN_RE.search(beat.narration) and not re.search(
        r"\b(he|she|they)\b", beat.narration, re.I
    ):
        return False
    short = _short_name_form(name)
    return not re.search(rf"\b{re.escape(short)}\b", beat.narration, re.I) and not re.search(
        rf"\b{re.escape(name)}\b", beat.narration, re.I
    )


def lint_ambiguous_pronoun(
    beats: list[ScriptBeat],
    bible: SeriesBible | None,
) -> dict[int, list[str]]:
    """Gate for `mc_acts_unnamed` — see it for the failure this exists for.

    Normally silent: `enforce_mc_name_budget` repairs this deterministically in the polish
    chain. It fires only when the repair could not (no name form to restore), which is
    worth surfacing rather than shipping.
    """
    if bible is None:
        return {}
    mc = bible.characters.get(bible.protagonist_id or "")
    who = mc.canonical_name if mc else "the protagonist"
    return {
        beat.beat_id: [
            f"this beat acts through a pronoun and never names {who}, who its own cast "
            "says is present — a listener cannot tell who is doing it. Name them"
        ]
        for beat in beats
        if mc_acts_unnamed(beat, bible)
    }


def lint_beats(
    beats: list[ScriptBeat],
    config: dict[str, Any],
    *,
    bible: SeriesBible | None = None,
    attribution: list[PanelCast] | None = None,
    scene_cards: list[SceneCard] | None = None,
) -> dict[int, list[str]]:
    words = banned_words(config)
    report: dict[int, list[str]] = {}
    for beat in beats:
        hits = find_violations(beat.narration, words)
        if hits:
            report[beat.beat_id] = hits
    for beat_id, issues in lint_hedging(beats).items():
        report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    for beat_id, issues in lint_register(beats).items():
        report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    for beat_id, issues in lint_protagonist_phrase(beats).items():
        report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    if bible:
        for beat_id, issues in lint_mc_name_spam(beats, bible, config).items():
            report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
        for beat_id, issues in lint_descriptor_quarantine(beats, bible).items():
            report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    for beat_id, issues in lint_aside_overuse(beats, config).items():
        report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    if bible is not None:
        for beat_id, issues in lint_reintroduction(beats, bible).items():
            report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    for beat_id, issues in lint_malformed_opening(beats).items():
        report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    for beat_id, issues in lint_cross_beat_repetition(beats).items():
        report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    for beat_id, issues in lint_captioning(beats).items():
        report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    for beat_id, issues in lint_dropped_speakers(beats, scene_cards, bible).items():
        report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    for beat_id, issues in lint_closer_reveal(beats, scene_cards).items():
        report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    for beat_id, issues in lint_trailing_closer(beats).items():
        report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    for beat_id, issues in lint_dangling_reply(beats).items():
        report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    for beat_id, issues in lint_pronoun_monotony(beats).items():
        report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    for beat_id, issues in lint_overlong_beats(beats, config, scene_cards).items():
        report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    if bible and attribution is not None:
        for beat_id, issues in lint_mc_attribution(beats, bible, attribution, config).items():
            report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
        for beat_id, issues in lint_named_presence(beats, bible, attribution).items():
            report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    if scene_cards is not None:
        for beat_id, issues in lint_panel_grounding(
            beats, scene_cards, bible=bible, attribution=attribution
        ).items():
            report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    return report


def _cast_for_panels(attribution: list[PanelCast], panel_ids: list[str]) -> str:
    lines: list[str] = []
    panel_set = set(panel_ids)
    for row in attribution:
        if row.panel_id not in panel_set:
            continue
        people = ", ".join(
            p.name_used or p.descriptor or p.ref for p in row.people if p.ref != "new" or p.name_used
        )
        if people:
            lines.append(f"{row.panel_id}: {people}")
    return "\n".join(lines) or "(see bible)"




def _humanize_issues(issues: list[str]) -> str:
    """Turn lint codes into instructions. A rewrite prompt fed "dropped_speaker:Song
    Chi-yul" has to guess what is being asked of it."""
    out: list[str] = []
    for issue in issues:
        if issue == "dangling_reply":
            out.append(
                "an answer is narrated with no question before it — either narrate the "
                "question it answers (it is in this beat's SPOKEN evidence) or drop the "
                "reply framing and state the fact directly"
            )
            continue
        if issue == "closer_no_forward_hook":
            out.append(
                "this beat ENDS the chapter and gives a listener no reason to watch the "
                "next one — it recaps and stops. Land the last sentence on what the "
                "protagonist is now going to DO about it, drawn from this beat's own "
                "evidence (a plan, an intent, a next step), never a hedge or a question"
            )
            continue
        if issue == "trailing_closer":
            out.append(
                "this beat ENDS the script and currently trails off on a hedge — end on a "
                "concrete forward hook drawn from the beat's own evidence instead"
            )
            continue
        if issue.startswith("dropped_reveal:"):
            evidence = issue.split(":", 1)[1]
            out.append(
                "this beat is the chapter's ENDING and its final panels read: "
                f"\"{evidence}\" — the beat must END by landing that content in reported "
                "form (never verbatim); everything else in the beat is secondary"
            )
            continue
        if issue.startswith("fragment:"):
            frag = issue.split(":", 1)[1].strip()
            out.append(
                f'"{frag}" is not a sentence — it has no verb. Either give it one or fold '
                "it into the sentence beside it; a listener hears a dead stub"
            )
            continue
        if issue.startswith("truncated_speech:"):
            sent = issue.split(":", 1)[1].strip()
            out.append(
                f'"{sent}" names who was spoken to but never what was said. Say the '
                "CONTENT of the line, from this beat's own evidence, or drop the speech "
                "framing entirely"
            )
            continue
        if issue.startswith("body_inventory:"):
            phrase = issue.split(":", 1)[1]
            out.append(
                f'"{phrase}" is body-language inventory — a gesture or mood that changes '
                "nothing. Spend those words on what is SAID or what it costs instead; "
                "keep the gesture only if the story turns on it"
            )
            continue
        if issue.startswith("dropped_speaker:"):
            name = issue.split(":", 1)[1]
            out.append(
                f"{name} SPEAKS in this beat's evidence but never appears in the narration — "
                f"narrate what {name} says and to whom, and do not hand their line to anyone else"
            )
        else:
            out.append(issue)
    return ", ".join(out)

def rewrite_beat(
    beat: ScriptBeat,
    bible: SeriesBible,
    attribution: list[PanelCast],
    config: dict[str, Any],
    *,
    issues: list[str] | None = None,
    scene_cards: list[SceneCard] | None = None,
    llm: Any | None = None,
) -> str:
    sanitized = local_sanitize_narration(beat.narration)
    remaining = lint_beats(
        [ScriptBeat(beat_id=beat.beat_id, panel_ids=beat.panel_ids, narration=sanitized, character_ids=beat.character_ids)],
        config,
        bible=bible,
        attribution=attribution,
        scene_cards=scene_cards,
    )
    # A caller-supplied issue IS the contract. This used to return here whenever
    # lint_beats came up clean, silently discarding `issues` — and lint_beats covers only
    # the old suite (hedges, name-spam, asides, banned words, grounding, malformed
    # openings). Every story-integrity finding — plot coverage, time shift, repeated
    # setting, abstraction drift, missing introduction, narration order, unanchored
    # opening — is invisible to it, so those rewrites never reached the model unless the
    # beat happened to ALSO carry an old-style defect. "Song Chi-yul is named with no
    # introduction" survived two full rewrite rounds untouched for exactly this reason and
    # had to be fixed by hand. lint_beats is now an ADDITIONAL source of issues, not a gate.
    if not issues and beat.beat_id not in remaining:
        return sanitized

    llm = llm or apply_stage_model(get_stage_llm("script", config), "script", config)

    ban = ", ".join(banned_words(config))
    cast = _cast_for_panels(attribution, beat.panel_ids)
    issue_text = _humanize_issues(issues or remaining.get(beat.beat_id, []))
    evid = evidence_for_panels(beat.panel_ids, scene_cards or [])
    user = (
        f"{naming_priority_rules(bible, config)}\n\n"
        f"Bible:\n{format_bible_for_prompt(bible)}\n\n"
        f"On-screen cast:\n{cast}\n\n"
        f"Panel EVIDENCE (narrate ONLY this):\n{evid}\n\n"
        f"Issues to fix: {issue_text}\n"
        f"Beat id: {beat.beat_id}\n\n"
        f"Original narration:\n{beat.narration}"
    )
    for attempt in range(4):
        try:
            # Plain prose, NOT JSON. The payload is one string, so the JSON envelope added
            # only a failure mode: narration containing reported speech or an apostrophe
            # broke json.loads and the rewrite was silently discarded (2-3 beats/run),
            # shipping the flagged text the rewrite existed to fix.
            raw = llm.complete(_REWRITE_PROMPT.format(ban_words=ban), user, json_mode=False)
            result = _clean_prose_reply(raw) or sanitized
            return rotate_protagonist_name(local_sanitize_narration(result), bible)
        except Exception as exc:
            if "rate_limit" in str(exc).lower() or "429" in str(exc):
                time.sleep(2 ** attempt)
                continue
            console.print(f"[yellow]Rewrite failed for beat {beat.beat_id}:[/] {exc}")
            break
    return sanitized


def lint_and_rewrite_script(
    beats: list[ScriptBeat],
    bible: SeriesBible,
    attribution_path: Path,
    config: dict[str, Any],
    *,
    scene_cards: list[SceneCard] | None = None,
) -> list[ScriptBeat]:
    attribution: list[PanelCast] = []
    if attribution_path.exists():
        attribution = [PanelCast.model_validate(a) for a in json.loads(attribution_path.read_text())]

    # model_copy, never field-by-field reconstruction: every beat passes through here,
    # and a hand-built ScriptBeat silently drops any field this code predates
    # (key_panel_ids was wiped on all 28 beats exactly this way).
    pre_sanitized = [
        beat.model_copy(
            update={"narration": rotate_protagonist_name(local_sanitize_narration(beat.narration), bible)}
        )
        for beat in beats
    ]

    # Script-wide name rotation must run BEFORE measuring: the per-beat rotation above
    # leaves one anchor per beat, which the script-wide spam rule then flags everywhere.
    pre_sanitized = enforce_mc_name_budget(pre_sanitized, bible, config)
    pre_sanitized = strip_repeated_appositives(pre_sanitized, bible)

    report = lint_beats(
        pre_sanitized, config, bible=bible, attribution=attribution, scene_cards=scene_cards
    )
    if not report:
        return pre_sanitized

    name_spam = sum(1 for issues in report.values() if "mc_full_name_spam" in issues)
    asides = sum(1 for issues in report.values() if "aside_overuse" in issues)
    ungrounded = sum(1 for issues in report.values() if any(i.startswith("ungrounded:") for i in issues))
    console.print(
        f"[yellow]Script lint:[/] {len(report)} beat(s) flagged "
        f"(hedges/name-spam/asides/banned/mc/grounding) — rewriting"
        + (f" [name-spam={name_spam}]" if name_spam else "")
        + (f" [asides={asides}]" if asides else "")
        + (f" [ungrounded={ungrounded}]" if ungrounded else "")
    )

    fixed: list[ScriptBeat] = []
    for beat in pre_sanitized:
        if beat.beat_id in report:
            new_text = accept_rewrite(beat.narration, rewrite_beat(
                beat,
                bible,
                attribution,
                config,
                issues=report[beat.beat_id],
                scene_cards=scene_cards,
            ))
            fixed.append(beat.model_copy(update={"narration": new_text}))
        else:
            fixed.append(beat)
    # A rewrite re-introduces the full name freely (it sees only its own beat), so the
    # budget sweep runs again over the final text.
    fixed = enforce_mc_name_budget(fixed, bible, config)
    fixed = strip_repeated_appositives(fixed, bible)
    remaining = lint_beats(
        fixed, config, bible=bible, attribution=attribution, scene_cards=scene_cards
    )
    if remaining:
        console.print(f"[yellow]Script lint:[/] {len(remaining)} beat(s) still flagged after rewrite")
    return fixed


# Function words a sentence can never legitimately end on. Vision captures bubbles that
# run across panel borders as fragments ("THE JOB WHERE YOUR LIFE'S ON THE"), and the
# writer reproduces the cut faithfully — "hunting is a job that puts his life on the...".
# A genuine cliffhanger ends on a COPULA ("his nickname is..."), which the manhwa itself
# punctuates with an ellipsis; that form is deliberate and stays.
_DANGLING_TAIL = {
    "the", "a", "an", "and", "or", "but", "of", "on", "in", "at", "to", "for", "with",
    "from", "into", "onto", "about", "as", "by", "that", "his", "her", "their", "its",
    "my", "your", "our", "this", "these", "those", "than", "then", "so", "because",
}


#: A speech verb followed by a bare echoed fragment and a question mark:
#: "He asks D-rank?". The words exist, so this is not truncation — it is a quotation
#: with the quotes missing, and TTS reads it exactly as written.
_ECHOED_QUESTION_RE = re.compile(
    r"\b(asks|repeats|echoes|repeated|asked|echoed)\s+"
    r"(?![Ii]f\b|whether\b|that\b|why\b|how\b|what\b|where\b|when\b|who\b|"
    r"about\b|for\b|him\b|her\b|them\b|it\b)"
    r"([^,.\"?!]{1,24}?)\s*\?\s*$"
)


def repair_echoed_question(text: str, names: set[str] | None = None) -> str:
    """Put the quotes back around an echoed line: He asks D-rank? -> He asks, "D-rank?"

    Found by the beats-wellformed gate on the first full-density 20-chapter script, at
    beat 70: the scouts read Jun-Ho's profile, one repeats the rank back in disbelief,
    and the writer rendered it without quotation marks. The gate was right — read aloud
    it is broken English, and the narrator would speak it as written.

    It is NOT the defect the truncated-speech detector describes (a speech verb naming a
    listener with nothing said), which is why the repair has to tell them apart. A known
    character name after the verb IS a listener, and quoting it would invent a line
    nobody spoke; anything else is the thing being echoed. Subordinators are excluded
    because "asks if his skill is D-rank" is already a complete report.
    """
    names = {n.lower() for n in (names or set())}

    def fix(sent: str) -> str:
        m = _ECHOED_QUESTION_RE.search(sent.strip())
        if not m:
            return sent
        echoed = m.group(2).strip()
        if not echoed or echoed.lower() in names:
            return sent          # a listener, not a quotation — a different defect
        head = sent.strip()[: m.start(2)].rstrip()
        head = head.rstrip(",")
        return f'{head}, "{echoed}?"'

    parts = [x for x in _SENTENCE_SPLIT_RE.split((text or "").strip()) if x.strip()]
    if not parts:
        return text
    return " ".join(fix(p) for p in parts)


def repair_truncated_sentences(beats: list[ScriptBeat]) -> list[ScriptBeat]:
    """Drop narration sentences that end mid-clause on a dangling function word.

    These are not style problems — they are unspeakable. The line goes to TTS and the
    narrator reads "puts his life on the" into silence. Dropping the sentence is always
    safe: every other sentence in the beat is independently grounded.
    """
    out: list[ScriptBeat] = []
    for beat in beats:
        sentences = [x for x in _SENTENCE_SPLIT_RE.split(beat.narration.strip()) if x.strip()]
        kept = []
        for sent in sentences:
            words = re.findall(r"[\w'’-]+", sent.lower())
            if words and words[-1] in _DANGLING_TAIL:
                continue
            kept.append(sent)
        text = " ".join(kept).strip()
        # Never empty a beat: a beat with no narration fails beat conservation.
        out.append(beat.model_copy(update={"narration": text}) if kept and text != beat.narration else beat)
    return out


# Script-writing vocabulary that must never reach the narrator's mouth. The prompt allows
# "the protagonist" once as a pressure valve; it spent that budget on the opening line
# ("Sung Jin-Woo, the protagonist and E-rank hunter, gasps..."), which is the worst
# possible place for it. Deterministic removal costs nothing and the prompt rule stays as
# guidance.
_LABEL = r"the (?:protagonist|main character|MC)"
# As an appositive the label is pure noise and comes out cleanly.
_LABEL_APPOSITIVE_RE = re.compile(rf",\s*{_LABEL}\b(\s+and\b)?", re.I)
# As a subject it is load-bearing: deleting it leaves a headless "walks away."
_LABEL_SUBJECT_RE = re.compile(rf"\b{_LABEL}\b", re.I)


def strip_internal_labels(beats: list[ScriptBeat], bible: SeriesBible | None = None) -> list[ScriptBeat]:
    """Remove narration references to the story's own machinery."""
    name = ""
    if bible is not None:
        profile = bible.characters.get(bible.protagonist_id or "")
        if profile is not None and not is_descriptor_label(profile.canonical_name):
            name = _short_name_form(profile.canonical_name)
    out: list[ScriptBeat] = []
    for beat in beats:
        def _label_sub(m: re.Match) -> str:
            # A PRECEDING comma does not make this an appositive. "Now, the protagonist
            # walks safely through the crosswalk" opens with a sentence adverbial, and
            # deleting the label there left "Now, walks safely" — which repair_subject_comma
            # then tidied into the headless "Now walks safely". Two correct steps, one
            # destroyed sentence. If a verb follows, the label is the SUBJECT: leave it for
            # the name swap below, which is what the comment on _LABEL_SUBJECT_RE has
            # always promised.
            after = beat.narration[m.end():].lstrip()
            first = after.split()[0] if after.split() else ""
            if _looks_like_verb(first):
                return m.group(0)
            return "," if m.group(1) else ""

        text = _LABEL_APPOSITIVE_RE.sub(_label_sub, beat.narration)
        # Whatever survived is a subject; swap in the name, or leave it rather than
        # producing a sentence with no subject at all.
        if name:
            text = _LABEL_SUBJECT_RE.sub(name, text)
        text = re.sub(r"\s*,\s*,", ",", text)
        text = re.sub(r"\s+([,.])", r"\1", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
        out.append(beat.model_copy(update={"narration": text}) if text and text != beat.narration else beat)
    return out


_SPEAKER_LINE_RE = re.compile(r"^\s*([^:>]+?)\s*(?:->[^:]*)?:", re.M)


def lint_dropped_speakers(
    beats: list[ScriptBeat],
    scene_cards: list[SceneCard] | None,
    bible: SeriesBible | None,
) -> dict[int, list[str]]:
    """Flag a beat whose evidence has a NAMED speaker the narration never mentions.

    Observed on ch1 beat 16: the evidence held Song Chi-yul asking the party to accept
    him as leader, plus an unowned "EVERY-ONE!" shout. The writer gave the unowned line
    to Kim Sangshik — a named character it already knew — and dropped Song Chi-yul
    entirely, so the next beat opened on "he happily accepts the choice" with no
    antecedent anywhere in the script. The election simply never happened.

    A named character with a line in the panel is always narratable, which makes this a
    high-signal check: if they are missing from the narration, the beat is telling the
    wrong story rather than compressing it.
    """
    if not scene_cards or bible is None:
        return {}
    # The protagonist is exempt: they are referred to by pronoun for stretches BY DESIGN,
    # and their anchoring cadence is enforce_mc_name_budget's job. Including them here
    # flags every well-formed beat that opens on "He".
    named = {
        p.canonical_name
        for pid, p in bible.characters.items()
        if not p.merged_into
        and p.canonical_name
        and not is_descriptor_label(p.canonical_name)
        and pid != bible.protagonist_id
    }
    if not named:
        return {}
    by_panel = {pid: c for c in scene_cards for pid in c.panel_ids}
    report: dict[int, list[str]] = {}
    for beat in beats:
        speakers: set[str] = set()
        for pid in beat.panel_ids:
            card = by_panel.get(pid)
            if card is None:
                continue
            for raw in _SPEAKER_LINE_RE.findall(card.source_text or ""):
                candidate = raw.strip().strip('"').strip()
                for name in named:
                    if candidate.lower() == name.lower():
                        speakers.add(name)
        low = beat.narration.lower()
        missing = [
            n for n in sorted(speakers)
            if n.lower() not in low and _short_name_form(n).lower() not in low
        ]
        if missing:
            report[beat.beat_id] = [f"dropped_speaker:{n}" for n in missing]
    return report


def lock_transition_line(
    beats: list[ScriptBeat],
    transition_panel: str,
    config: dict[str, Any],
    chapter_line: str = "",
) -> list[ScriptBeat]:
    """Replace the flashforward's closing sentence with the approved wording.

    The return to the present is the script's single most conspicuous line, and the model
    keeps embellishing it into something worse than the exemplar it was given:

        gold      Then the sky clears, over present-day Seoul.
        produced  Away from the trials of him, the sky clears over the peaceful bridges
                  of present-day Seoul.

    That second version is not a style disagreement, it is broken English shipped in the
    most audible position in the recap. Placement is already deterministic
    (strip_duplicate_transitions picks the beat whose panels show the shift); this locks
    the wording too, so the line stops being re-rolled every run.

    The wording comes from the chapter itself: the whole-chapter read writes
    `return_to_present_line` once, with the entire chapter in view, and this locks that
    sentence in place. Nothing here is series-specific — an earlier version hardcoded one
    title's line in config.yaml, which would have injected that city's name into every
    other series. `script.transition_line` survives only as a manual override.
    """
    line = str(get_nested(config, "script", "transition_line", default="") or "").strip()
    if not line:
        line = " ".join(str(chapter_line or "").split())
    if not line or not transition_panel:
        return beats
    out: list[ScriptBeat] = []
    for beat in beats:
        if transition_panel not in beat.panel_ids:
            out.append(beat)
            continue
        sentences = [s for s in _SENTENCE_SPLIT_RE.split(beat.narration.strip()) if s.strip()]
        if not sentences:
            out.append(beat)
            continue
        # The rewind closes the beat, so the final sentence is the one to replace — but
        # only if it is actually about the shift, never a story sentence.
        marker = re.compile(r"\bpresent[- ]day\b|\bthe sky clears\b|\bback in the present\b", re.I)
        if marker.search(sentences[-1]):
            sentences[-1] = line
            locked_at = len(sentences) - 1
        else:
            # Place it where the shift actually happens. Appending unconditionally put the
            # cue at the END of a beat whose FIRST panel was the last flashforward frame,
            # so three panels of present-day narration played before the line announcing
            # the return — the marker arrived after the thing it marks. Sentences track
            # panels in order, so the panel's position in the beat gives the position in
            # the prose: first panel -> the line opens the beat, last panel -> it closes.
            idx = beat.panel_ids.index(transition_panel)
            span = max(1, len(beat.panel_ids) - 1)
            pos = max(0, min(len(sentences), round(idx / span * len(sentences))))
            sentences.insert(pos, line)
            locked_at = pos
        # The model often writes the shift twice, e.g. "Quiet bridges now span the wide
        # river under the distant skyline of Seoul." right before the locked line. Any
        # EARLIER sentence naming the destination is that same restatement.
        # The place named at the end of the locked line ("...over present-day Seoul.") is
        # what an earlier restatement would also name.
        destination = line.rsplit(" ", 1)[-1].strip(".,").lower()
        if destination and len(destination) > 3:
            # Protect the locked line BY INDEX. This used to keep "the last sentence",
            # which was the same thing only while the line was always appended; once
            # placement follows the panel, an early-placed line names the destination and
            # the filter deleted the very sentence it was meant to preserve.
            sentences = [
                s for i, s in enumerate(sentences)
                if i == locked_at or destination not in s.lower()
            ]
        text = " ".join(sentences)
        out.append(beat.model_copy(update={"narration": text}) if text != beat.narration else beat)
    return out


# "a hunter with a fur collar", "another in a green jacket", "a man in a blue cap" — an
# anonymous person identified by clothing. recap.txt rule 3 bans appearance captioning and
# rule 5 bans scenery people; both keep being violated for extras specifically, because
# the evidence names them that way ("woman with fur collar -> Song Chi-yul: ...") and the
# writer passes the label straight through.
_ANON_NOUN = (
    r"hunter|man|woman|guy|person|figure|worker|vendor|bystander|onlooker|passerby|"
    r"newcomer|leader|healer|veteran|fighter|mage|kid|youth|boy|girl|stranger|"
    # Added 2026-09-01 from a real script: three unnamed examiners were each
    # identified by clothing ("a younger recruiter in a leather jacket"), which the
    # list could not reach. Generic occupation words only — no series vocabulary.
    r"recruiter|examiner|applicant|official|clerk|guard|soldier|nurse|doctor|"
    r"receptionist|attendant|reporter|student|customer|passenger"
)
_GARMENT = (
    r"collar|jacket|cap|hat|coat|shirt|hoodie|glasses|hair|beard|goatee|backpack|"
    r"uniform|vest|scarf|boots|gloves|mask|"
    # Added after the shipped script proved the list was the binding constraint, not the
    # pattern: "A young boy in a beige sweater" and "a man in a black suit with black
    # hair" both matched every part of _ANON_APPEARANCE_RE except the garment word.
    r"sweater|suit|tie|robe|robes|armor|armour|dress|skirt|apron|helmet|goggles|"
    r"eyepatch|earrings|necklace|gown|cloak|coveralls|slacks|trousers|jeans|"
    # Hairstyles are appearance exactly as hats are; "a man with dreadlocks" was the
    # case that showed the list stopped at garments.
    r"dreadlocks|ponytail|braid|braids|moustache|mustache|sideburns|bun"
)
_ANON_APPEARANCE_RE = re.compile(
    # "a/an/another/one" + optional adjectives + optional noun, then a garment phrase.
    # The noun is optional so "another in a green jacket" collapses too.
    rf"\b(a|an|the|another|one)\s+"
    rf"((?:[\w'’-]+\s+){{0,2}}(?:{_ANON_NOUN})\s+|)"
    rf"(?:with|in|wearing)\s+"
    rf"(?:a|an|the)?\s*"
    rf"(?:[\w'’-]+\s+){{0,3}}"
    rf"(?:{_GARMENT})\b"
    # ...plus any further descriptors chained onto it ("and a goatee", "with black
    # hair"), or the strip leaves half the inventory behind: "a man in a black suit with
    # black hair" collapsed only to "a man with black hair" while "and" was the sole
    # accepted connector.
    rf"(?:\s*,?\s*(?:and|with)\s+(?:a|an|the)?\s*(?:[\w'’-]+\s+){{0,3}}(?:{_GARMENT})\b)*",
    re.I,
)


def strip_appearance_descriptors(beats: list[ScriptBeat], bible: SeriesBible | None = None) -> list[ScriptBeat]:
    """Strip clothing and hair out of the noun phrases that identify people.

    "A hunter with a fur collar and another in a green jacket chime in" becomes "A hunter
    and another chime in" — the extras still act on the story, they just stop being
    described by their outfits.

    This also trims a NAMED character's intro clause down to its role, which is what rule
    4 asks for anyway: "Kim Sangshik, a veteran hunter in a blue jacket" -> "Kim Sangshik,
    a veteran hunter", matching the gold's "Lee Joo-hee, the party's rookie healer". Rule
    3 bans appearance captioning outright, so the garment adds nothing in either position.

    Definite phrases match too ("Song Chi-yul, the veteran party leader with short gray
    hair" -> "..., the veteran party leader"); an earlier version restricted this to
    indefinite phrases and those kept their hair. Any phrase whose head noun is not a
    person is left alone, which is what keeps places and objects out of it.
    """
    out: list[ScriptBeat] = []
    for beat in beats:
        text = _ANON_APPEARANCE_RE.sub(lambda m: f"{m.group(1)} {m.group(2)}".strip(), beat.narration)
        text = re.sub(r"\s{2,}", " ", text).strip()
        out.append(beat.model_copy(update={"narration": text}) if text and text != beat.narration else beat)
    return out


def dedupe_cross_beat_sentences(beats: list[ScriptBeat], lookback: int = 2) -> list[ScriptBeat]:
    """Remove a sentence that restates something an earlier beat already told.

    The once-only rule is the one that keeps failing, in every architecture tried. The
    latest run:

        beat 10  He sighs at the old men and asks for coffee. The vendor apologetically
                 admits they just ran out.
        beat 11  He sighs in disappointment when he learns there is no coffee left for
                 him. The coffee vendor tries to explain, but he politely says it is fine.

    The style gate caught it ("beat 11: 'coffee' both asserted and negated") but only as a
    warning. lint_cross_beat_repetition compares whole beats, so two beats that repeat one
    exchange while differing elsewhere score below its threshold and pass.

    Working at sentence level catches the real unit of repetition. Comparison is against
    the previous `lookback` beats only — a motif legitimately recurring across the whole
    chapter (the protagonist being called weak) is not the target; consecutive retellings
    of one moment are. Never empties a beat: the first sentence always survives, so beat
    conservation holds.

    SCOPE, measured rather than assumed: at 0.6 this catches near-verbatim restatement.
    The coffee pair above scores only 0.29 ("coffee", "sighs" are the entire overlap), so
    a threshold low enough to catch PARAPHRASED repetition would start deleting correct
    sentences. Paraphrase-level repetition is not reliably detectable by string matching;
    it stays a warn-only style-gate finding and a human edit, and this function
    deliberately does not chase it.
    """
    out: list[ScriptBeat] = []
    history: list[list[set[str]]] = []
    for beat in beats:
        sentences = [s for s in _SENTENCE_SPLIT_RE.split(beat.narration.strip()) if s.strip()]
        recent = [tokens for prev in history[-lookback:] for tokens in prev]
        kept: list[str] = []
        kept_tokens: list[set[str]] = []
        for sentence in sentences:
            tokens = _stemmed_words(sentence)
            # Unlike the intra-beat pass, the FIRST sentence is checked too — restating
            # the previous beat is precisely what a beat's opening sentence tends to do.
            if tokens and any(len(tokens & prev) / len(tokens) >= 0.6 for prev in recent):
                continue
            kept.append(sentence)
            kept_tokens.append(tokens)
        if not kept:
            kept, kept_tokens = sentences[:1], [_stemmed_words(sentences[0])] if sentences else ([], [])
        history.append(kept_tokens)
        text = " ".join(kept).strip()
        out.append(beat.model_copy(update={"narration": text}) if text and text != beat.narration else beat)
    return out


def lint_closer_reveal(
    beats: list[ScriptBeat],
    scene_cards: list[SceneCard] | None,
) -> dict[int, list[str]]:
    """The final story panels are the chapter's chosen ending; the closer must say it.

    Positional and series-agnostic: whatever the last panels' on-panel text contains is
    what the chapter ends on. Flagged as `dropped_reveal:<evidence>` so the rewrite is
    handed the exact content to land rather than a code to guess at.
    """
    if not beats or not scene_cards:
        return {}
    by_panel: dict[str, str] = {}
    for card in scene_cards:
        for pid in card.panel_ids:
            by_panel[pid] = card.source_text or ""
    ordered = sorted(by_panel, key=lambda p: p)
    tail_text = " ".join(by_panel[p] for p in ordered[-3:]).strip()
    if not tail_text:
        return {}
    terms = {
        w for w in re.findall(r"[a-z][a-z'-]{3,}", tail_text.lower())
        if w not in _STOPWORDS_SMALL
    }
    if not terms:
        return {}
    closer = beats[-1]
    low = closer.narration.lower()
    hits = sum(1 for t in terms if t in low)
    # A bracketed system message in the final panels is the genre's reveal device; a
    # closer that "lands" it must carry its content, not one stray noun. The lenient
    # single-term check let a closer narrating only the FAILURE half ("...stats fail
    # to melt her seal") pass on the word "seal" while the reveal (the seal CAN be
    # removed) was gone. Chapters ending on plain dialogue keep the lenient check —
    # their endings have no payload sentence to demand.
    strict = "[" in tail_text and "]" in tail_text
    required = 2 if strict else 1
    if hits >= min(required, len(terms)):
        return {}
    return {closer.beat_id: [f"dropped_reveal:{' '.join(tail_text.split())[:220]}"]}


_STOPWORDS_SMALL = frozenset(
    """
    the a an and or but so of to in on at for with from by as is are was were be have
    has had this that it its his her their you your they them he she we not no what
    when where who how why there here then than now all any some very
    """.split()
)


# Constructions that END a script on a shrug. The closer is the one beat a viewer is
# guaranteed to hear to the end, and the prompt's "no trailing off" instruction has been
# declined repeatedly ("...remains to be seen", "...only time will tell"). Generic
# English hedging shapes, not a per-series list.
_TRAILING_CLOSER_RE = re.compile(
    r"\b(?:remains? to be seen|only time will tell|time will tell|"
    r"what (?:happens|comes) next|remains? (?:unclear|uncertain|unknown)|"
    r"(?:he|she|they) (?:can )?only hopes?|the future (?:is|remains)|"
    r"whether .{0,60} remains?)\b",
    re.I,
)


# A final sentence that OPENS on "Whether ..." poses a question instead of landing an
# event, whatever it goes on to say. Shape, not vocabulary: rewording the hedge
# ("...remains to be seen" -> "...is the only question worth asking") keeps the defect,
# so the opener is what gets checked.
_QUESTION_OPENER_RE = re.compile(r"^\s*(?:whether|will\s+\w+\s+ever|can\s+\w+\s+really)\b", re.I)


# A concrete forward commitment: a plan, an intent, a next step. This is what the
# reference's closer lands and ours does not — Mamoru ends on "the plan writes itself.
# Climb the tower, get the magic, melt the ice, bring them home. He tells Shim he's
# becoming a player again", ours ended on "He gasps in disbelief."
#
# Deliberately about INTENT, not tense: the narration is present-tense throughout, so
# "will" is rare and cannot be the signal.
_FORWARD_HOOK_RE = re.compile(
    r"\b(?:the plan|plans? to|intends? to|sets? out|sets? his sights|plans on|"
    r"about to|going to|plans|plotting|decides? to|swears? to|vows? to|promises? to|"
    r"plans for|from here|next time|next stop|first step|starts? hunting|"
    r"begins? the climb|becom(?:e|es|ing)\s+\w+\s+again|has a plan|knows what to do|"
    r"now he|so he|that is when he|is coming for|comes for)\b",
    re.I,
)


def has_forward_hook(text: str) -> bool:
    """Does this text point at what happens NEXT, rather than only recapping?"""
    return bool(_FORWARD_HOOK_RE.search(text or ""))


def _is_trailing_closer_sentence(sentence: str) -> bool:
    """A hedge that ends the chapter on nothing.

    A sentence carrying a concrete forward commitment is exempt even when it is
    question-shaped: "Whether he can climb ten floors is beside the point — he already
    has a plan" states an intent, and deleting it would trade a hedge for no ending at
    all, which is strictly worse. The hedge test is about the ABSENCE of a next step,
    so a sentence that supplies one cannot be the thing this removes.
    """
    if has_forward_hook(sentence):
        return False
    return bool(_TRAILING_CLOSER_RE.search(sentence) or _QUESTION_OPENER_RE.match(sentence))


def lint_closer_forward_hook(beats: list[ScriptBeat]) -> dict[int, list[str]]:
    """Flag a closer that recaps without pointing forward.

    The gap this fills: every OTHER closer constraint in this pipeline is
    backward-looking — `lint_closer_reveal` and the `reveal-coverage` gate both demand
    the final panels' content, and `inject_closer_evidence` pins that content into the
    closer's plot_beat. Nothing ever asked whether the ending gives a listener a reason
    to watch the next one, so a closer could satisfy every gate while ending on "He
    gasps in disbelief." The forward hook existed only as prompt text and as an untested
    `open_threads` string.

    Warn-and-rewrite, not blocking: "points forward" is a judgement a regex approximates,
    and a chapter genuinely ending on a closed note is a legitimate shape.
    """
    if not beats:
        return {}
    closer = beats[-1]
    if has_forward_hook(closer.narration):
        return {}
    return {closer.beat_id: ["closer_no_forward_hook"]}


def lint_trailing_closer(beats: list[ScriptBeat]) -> dict[int, list[str]]:
    """Flag a closer that ends on a hedge instead of a concrete forward hook."""
    if not beats:
        return {}
    closer = beats[-1]
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(closer.narration.strip()) if s.strip()]
    if not sentences:
        return {}
    if _is_trailing_closer_sentence(sentences[-1]):
        return {closer.beat_id: ["trailing_closer"]}
    return {}


def strip_trailing_closer_sentence(beats: list[ScriptBeat]) -> list[ScriptBeat]:
    """Deterministic backstop: drop a closing hedge sentence outright.

    A hedge adds no information — the beat's remaining sentences already carry the
    chapter's last events — so removing it strictly improves the ending. Never empties a
    beat: a one-sentence closer is left alone for the rewrite to handle.
    """
    if not beats:
        return beats
    closer = beats[-1]
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(closer.narration.strip()) if s.strip()]
    if len(sentences) < 2 or not _is_trailing_closer_sentence(sentences[-1]):
        return beats
    text = " ".join(sentences[:-1]).strip()
    if not text:
        return beats
    return [*beats[:-1], closer.model_copy(update={"narration": text})]


_SUBJECT_COMMA_VERB_RE = re.compile(
    r"([A-Za-z][\w'’-]*),\s+"
    r"(stands|sits|walks|runs|steps|turns|leaps|lands|rises|falls|smiles|laughs|gasps|"
    r"stares|looks|draws|raises|enters|faces|charges|kneels|collapses|waits|watches|"
    r"crosses|arrives|pauses|freezes|shivers|nods|bows|climbs)\b"
)


# "Nearby, Kim Sangshik, Bak." followed by "They look toward the Gate." — the names are a
# stranded appositive whose verb ended up in the NEXT sentence. Joining them restores both
# without inventing anything.
_STRANDED_NAMES_JOIN_RE = re.compile(
    r"(?P<lead>[^.!?]*?)(?P<n1>[A-Z][\w'’-]*(?:[- ][A-Z][\w'’-]*)*)\s*,\s*"
    r"(?P<n2>[A-Z][\w'’-]*(?:[- ][A-Z][\w'’-]*)*)\s*\.\s+They\s+(?P<rest>[^.!?]*[.!?])"
)

# A speech verb naming its listener with nothing said. The clause carries no information
# as written, so removing it is lossless — unlike inventing what was said, which is not
# ours to do. Handles both the coordinated ("and tells X.") and participial (", telling
# X.") shapes.
_DANGLING_SPEECH_TAIL_RE = re.compile(
    r"(?:\s*,\s*(?:telling|asking|saying|replying|answering|admitting|warning|reminding)"
    r"|\s+and\s+(?:tells|asks|says|replies|answers|admits|warns|reminds|told))\s+"
    r"(?:him|her|them|it|[A-Z][\w'’-]*(?:[- ][A-Z][\w'’-]*)*)\s*(?=[.!?])"
)


def _drop_empty_speech_sentence(text: str) -> str:
    """Remove a whole sentence that is nothing but "X tells Y." — no content.

    The tail form (", telling Y." / "and tells Y.") is strippable back to the clause it
    hangs off. A STANDALONE one has nothing to fall back to: cutting the verb from
    "Mr. Kim tells Sung Jin-Woo." leaves "Mr. Kim." So the sentence goes entirely.

    Two guards, both about not trading one defect for a worse one: at least two sentences
    must survive, and the following sentence must not open on a bare pronoun — deleting
    "The demon tells Ju-Hee." before "She asks how that is possible." would strand
    "She" with no antecedent anywhere in the beat.
    """
    sentences = [s for s in _SENTENCE_SPLIT_RE.split((text or "").strip()) if s.strip()]
    if len(sentences) < 3:
        return text
    keep: list[str] = []
    for i, sent in enumerate(sentences):
        bare = sent.strip()
        is_empty_speech = bool(_TRUNCATED_SPEECH_RE.search(bare)) and len(bare.split()) <= 6
        nxt = sentences[i + 1].strip() if i + 1 < len(sentences) else ""
        strands_pronoun = bool(_PRONOUN_START_RE.match(nxt))
        if is_empty_speech and not strands_pronoun and len(sentences) - 1 >= 2:
            continue
        keep.append(sent)
    return " ".join(keep).strip() if len(keep) >= 2 else text


# "Ju-Hee. She looks down." — a bare name, then a sentence whose subject is the pronoun
# that name should have been. The verb already exists; only the subject was severed.
_PRONOUN_SUBJECT_RE = re.compile(r"^(He|She|They)\s+(?P<rest>[a-z].*)$", re.S)


def _rejoin_bare_name_sentence(text: str) -> str:
    """Splice a stranded name back onto the clause it was severed from.

    Invents nothing — the verb phrase is already sitting in the next sentence, and the
    pronoun it currently uses is precisely the one the name would have supplied.

    Works on whole SENTENCES rather than a regex over the running text. The first attempt
    matched any name-then-period-then-pronoun span and mangled five correct beats in the
    same run it was meant to fix: "Ju-Hee channels her magic into Sung Jin-Woo. She asks
    him why..." became "...into Sung Jin-Woo asks him why...", because "Sung Jin-Woo." is
    a bare name in isolation but was the TAIL of a complete sentence, not the whole of one.
    The condition was never "is this a name" — it is "is this sentence nothing but a name",
    and only a sentence-level view can tell those apart.
    """
    sentences = [x.strip() for x in _SENTENCE_SPLIT_RE.split((text or "").strip()) if x.strip()]
    out: list[str] = []
    i = 0
    while i < len(sentences):
        sent = sentences[i]
        follower = sentences[i + 1] if i + 1 < len(sentences) else ""
        match = _PRONOUN_SUBJECT_RE.match(follower) if follower else None
        if match and _is_bare_name_sentence(sent):
            out.append(f"{sent.rstrip('.!?')} {match.group('rest')}")
            i += 2
            continue
        out.append(sent)
        i += 1
    return " ".join(out)


def repair_broken_sentences(beats: list[ScriptBeat]) -> list[ScriptBeat]:
    """Mechanically fix the two dead-stub shapes the rewrite keeps declining.

    Both shipped into a rendered video, and both survived a story-integrity rewrite AND
    the dedicated dialogue retry with the offending sentence quoted back at the model.
    The evidence for beat 11 even CONTAINED what Jin-Woo says ("IT'S OKAY. IT'S ONLY
    BECAUSE I'M WEAK... I'M USED TO IT.") and the rewrite still returned "tells Lee
    Joo-hee." three runs running. That is this codebase's stated threshold: a rule the
    model declines twice stops being a request.

    Neither repair invents content. The stranded-name join moves a verb that is already
    in the next sentence; the dangling-speech strip removes a clause that says nothing —
    "Jin-Woo smiles weakly and tells Lee Joo-hee." carries exactly as much information as
    "Jin-Woo smiles weakly.", minus the broken grammar. Supplying what was actually said
    would be authoring narration, which belongs to the writer, not the polish.
    """
    out: list[ScriptBeat] = []
    for beat in beats:
        text = beat.narration
        # "The they explain..." -> "They explain...". Only when the article sits DIRECTLY
        # on the pronoun: _ARTICLE_PRONOUN_RE's docstring is right that "A dejected he
        # walks away" cannot be repaired without knowing which person, but a bare article
        # on a bare pronoun carries no such ambiguity.
        text = re.sub(
            r"\b(The|A|An|the|a|an)\s+(they|he|she|him|her|them|They|He|She|Him|Her|Them)\b",
            lambda m: m.group(2).capitalize() if m.group(1)[0].isupper() else m.group(2).lower(),
            text,
        )
        text = _drop_empty_speech_sentence(text)
        text = _rejoin_bare_name_sentence(text)
        text = _STRANDED_NAMES_JOIN_RE.sub(
            lambda m: f"{m.group('lead')}{m.group('n1')} and {m.group('n2')} {m.group('rest')}",
            text,
        )
        text = _DANGLING_SPEECH_TAIL_RE.sub("", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
        out.append(beat.model_copy(update={"narration": text}) if text and text != beat.narration else beat)
    return out


def repair_subject_comma(beats: list[ScriptBeat]) -> list[ScriptBeat]:
    """"Seo Jun-Ho, stands in the throne room" — a comma splice between subject and
    verb, unspeakable aloud.

    The verb match alone does NOT identify a splice, and the claim that it left genuine
    appositives untouched was simply wrong: the word before the comma is the last word of
    the appositive, not the subject, so "Lee Joo-hee, the party's healer, arrives" matched
    on "healer, arrives" and shipped as "the party's healer arrives" — the model had
    punctuated it correctly and the polish pass broke it, on every run.

    An earlier comma in the same sentence is the discriminator: it means this comma CLOSES
    a clause rather than separating a subject from its verb. Precision over recall, as
    everywhere in this module — a missed splice reads slightly off, a wrongly deleted
    comma changes what the sentence means.
    """
    out: list[ScriptBeat] = []
    for beat in beats:
        text = beat.narration

        def _sub(m: re.Match) -> str:
            head = text[: m.start(1)]
            sentence_so_far = re.split(r"[.!?]\s+", head)[-1]
            if "," in sentence_so_far:
                return m.group(0)  # closing an appositive, not splicing a subject
            return f"{m.group(1)} {m.group(2)}"

        fixed = _SUBJECT_COMMA_VERB_RE.sub(_sub, text)
        out.append(beat.model_copy(update={"narration": fixed}) if fixed != text else beat)
    return out


def derive_key_panels(
    beats: list[ScriptBeat],
    scene_cards: list[SceneCard] | None,
    *,
    max_keys: int = 5,
    min_overlap: float = 0.18,
) -> list[ScriptBeat]:
    """Mark the panels each beat's narration actually used — deterministically.

    The narration schema asked the writer to self-report key_panels; on whole-script
    calls (28 beats in one response) the model omitted the field every time while the
    small retry calls included it — compliance falls exactly when output pressure
    rises. But self-report was never necessary: the narration itself shows which panels
    it drew on. A panel whose dialogue/action content overlaps the beat's narration IS
    a panel the narration depends on. Writer-provided keys are kept when present;
    derivation fills the gaps.
    """
    if not scene_cards:
        return beats
    by_panel: dict[str, str] = {}
    for card in scene_cards:
        text = f"{card.source_text or ''} {card.action or ''}"
        for pid in card.panel_ids:
            by_panel[pid] = text
    out: list[ScriptBeat] = []
    for beat in beats:
        if beat.key_panel_ids:
            out.append(beat)
            continue
        narration_stems = _stemmed_words(beat.narration)
        if not narration_stems:
            out.append(beat)
            continue
        scored: list[tuple[float, str]] = []
        for pid in beat.panel_ids:
            panel_stems = _stemmed_words(by_panel.get(pid, ""))
            if not panel_stems:
                continue
            overlap = len(narration_stems & panel_stems) / len(panel_stems)
            if overlap >= min_overlap:
                scored.append((overlap, pid))
        scored.sort(reverse=True)
        keys = [pid for _s, pid in scored[:max_keys]]
        keys = [pid for pid in beat.panel_ids if pid in keys]  # reading order
        out.append(beat.model_copy(update={"key_panel_ids": keys}) if keys else beat)
    return out


_APPOSITIVE_LEAD_RE = re.compile(
    # The FIRST comma-segment of an appositive: ", a member of the five heroes",
    # ", Jun-Ho's old friend and the current president", ", her older brother".
    r",\s+((?:(?:a|an|the|another|one)\b|[A-Z][\w'’-]*['’]s\b|his\b|her\b|their\b)[^,.;!?]*)",
    re.I,
)
# A SECOND segment continuing the same appositive: ", currently frozen in ice".
_APPOSITIVE_TAIL_RE = re.compile(r",\s+([a-z][^,.;!?]*)")

# Bare weld: "<Name> currently frozen in ice, admits ..." — an appositive that lost its
# opening comma. Only ever removed when it is a variant of a clause already kept.
_APPOSITIVE_WELD_RE = re.compile(
    r"\b([A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+)*)\s+((?:[a-z][\w'’-]*\s+){2,7}[a-z][\w'’-]*),\s+([a-z][\w'’-]*)"
)

# How many comma-separated segments one appositive may span. Two, because that is the
# longest form observed ("<role>, <state>") and because the third segment is where the
# main sentence usually resumes with an irregular past ("..., spoke, Khali nodded") that
# no suffix test recognises as a verb. A greedy scan swallowed exactly that verb clause
# and poisoned the variant detector's token sets. The bound is the check: it is not
# precise, it is safe, and test_dedupe_appositive_clauses_all_observed_forms pins it.
_MAX_APPOSITIVE_SEGMENTS = 2


def _iter_appositive_spans(text: str):
    """Yield (start, end, clause) for each appositive, inner commas included.

    Non-overlapping and left-to-right; `end` includes the closing comma when there is
    one, so the caller can drop the slice outright.
    """
    cursor = 0
    for m in _APPOSITIVE_LEAD_RE.finditer(text):
        if m.start() < cursor:
            continue
        end = m.end(1)
        for _ in range(_MAX_APPOSITIVE_SEGMENTS - 1):
            tail = _APPOSITIVE_TAIL_RE.match(text, end)
            if not tail:
                break
            first = tail.group(1).split()[0] if tail.group(1).split() else ""
            if _looks_like_verb(first):
                break  # the main sentence resumes here
            end = tail.end(1)
        clause = text[m.start(1):end]
        if text[end:end + 1] == ",":
            end += 1
        cursor = end
        yield m.start(), end, clause

def dedupe_appositive_clauses(beats: list[ScriptBeat]) -> list[ScriptBeat]:
    """One appositive CLAUSE per script, whoever it is attached to.

    strip_repeated_appositives keys its ledger on the character NAME, which is correct
    for "introduce each character once" and useless when the SAME clause is stamped on
    several characters: a synopsis once gave four teammates the identical role sentence,
    and the first beat naming three of them shipped it three times in one sentence —
    every name legitimately at its own first occurrence. The unit of repetition is the
    clause, so that is the ledger key here.

    Two passes, both REMOVAL-ONLY:
      - article/possessive-led spans (", a member of the five heroes,", ", Jun-Ho's old
        friend and the current president,") — the first is kept, later ones dropped;
      - bare spans (", members of the five heroes,") which cannot be matched by the
        anchored pattern without matching every parenthetical, so they are removed only
        when they are a >=0.8 content-word variant of a clause already kept. Synopses
        vary their template per character ("a heavily tattooed member...", "a deadly
        member..."), and exact-text matching misses all of it.

    Scope, learned the hard way: this function once also carried "weld repair" and
    multi-round residue passes to clean text mangled by an earlier version of
    strip_repeated_appositives. One of their heuristics — treat a segment as descriptive
    if its first word ends in -en — deleted "queen dissipates into light," from "The
    queen dissipates into light, admitting she enjoyed their final struggle", because
    QUEEN ends in -en. That shipped. The mangling those passes cleaned up is now
    prevented at its two sources (the per-name regex no longer spans inner commas;
    synopsis roles are truncated to one clause), so the cleanup machinery is gone rather
    than made cleverer. A remover that can delete correct prose is worse than the
    duplication it removes.
    """
    seen: set[str] = set()
    seen_sets: list[frozenset[str]] = []
    out: list[ScriptBeat] = []

    def _content_set(clause: str) -> frozenset[str]:
        return frozenset(_stemmed_words(clause))

    def _is_variant(tokens: frozenset[str]) -> bool:
        if not tokens:
            return False
        return any(
            prev and len(tokens & prev) / min(len(tokens), len(prev)) >= 0.8
            for prev in seen_sets
        )

    for beat in beats:
        text = beat.narration

        # Pass 1 — article/possessive-led spans, scanned so a "<role>, <state>" clause
        # is one span. Keep the first of each clause, drop every later variant.
        pieces: list[str] = []
        protected: list[str] = []
        cursor = 0
        for a, b, clause in _iter_appositive_spans(text):
            norm = re.sub(r"^(?:a|an|the|another|one)\s+", "", " ".join(clause.split()).lower())
            tokens = _content_set(norm.replace(",", ""))
            pieces.append(text[cursor:a])
            if norm in seen or _is_variant(tokens):
                # Keep the comma only when a name-list continues ("Skaya, Khali, and X");
                # before a lowercase verb it must go too ("The Swordswoman agrees").
                pieces.append("," if text[b:].lstrip()[:1].isupper() else "")
            else:
                seen.add(norm)
                seen_sets.append(tokens)
                # Masked, not appended: passes 2 and 3 would otherwise re-match the
                # second segment of the clause just KEPT ("..., currently frozen in
                # ice,") as a variant of the whole, deleting it AND its closing comma
                # and leaving "Skaya, a member of the five heroes speaks first."
                pieces.append(f"\x00{len(protected)}\x00")
                protected.append(text[a:b])
            cursor = b
        pieces.append(text[cursor:])
        text = "".join(pieces)

        # Pass 2 — bare spans (", members of the five heroes,"). Not anchorable without
        # matching every parenthetical, so variant-similarity is the only admission test.
        def _bare_sub(m: re.Match) -> str:
            if _is_variant(_content_set(m.group(1).lower())):
                return "," if text[m.end():].lstrip()[:1].isupper() else ""
            return m.group(0)

        # The lookahead is load-bearing: without it this pass re-matches the very span
        # pass 1 just decided to KEEP (an article-led clause also starts lowercase), and
        # every first occurrence is deleted as a variant of itself.
        text = re.sub(
            r",\s+((?!(?:a|an|the|another|one|his|her|their)\b)[a-z][^,.;!?]+?)(?:,|(?=[.!?]))",
            _bare_sub,
            text,
        )

        # Pass 3 — welds: the same clause with its opening comma already gone.
        # ONLY variant membership may trigger this. Two looser triggers lived here and
        # both destroyed correct prose: an "ends in -en means participle" shape test
        # deleted "queen dissipates into light," from "The queen dissipates into light,
        # admitting she enjoyed their final struggle" (QUEEN ends in -en), and "the next
        # word looks like a verb" fires on any participial clause. A weld only ever
        # arises for a clause already seen, so the ledger is the correct trigger.
        def _weld_sub(m: re.Match) -> str:
            if _is_variant(_content_set(m.group(2).lower())):
                return f"{m.group(1)} {m.group(3)}"
            return m.group(0)

        text = _APPOSITIVE_WELD_RE.sub(_weld_sub, text)

        text = re.sub(r"\x00(\d+)\x00", lambda m: protected[int(m.group(1))], text)

        text = re.sub(r"\s*,\s*,", ",", text)
        text = re.sub(r"\s+([,.!?])", r"\1", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
        out.append(beat.model_copy(update={"narration": text}) if text and text != beat.narration else beat)
    return out

_ANSWER_VERB_RE = re.compile(
    r"\b(replies|responds|answers|confirms)\b(?:\s+[\w'’-]+){0,2}\s+that\b", re.I
)
_QUESTION_CUE_RE = re.compile(r"\?|\b(asks?|asked|wonders?|demands?|questions?)\b", re.I)


def lint_dangling_reply(beats: list[ScriptBeat]) -> dict[int, list[str]]:
    """An answer with no question: "The presenter replies that they did." shipped with
    nothing asked anywhere before it in the beat. Deterministic detection; the repair
    goes through the rewrite loop, which holds the beat's SPOKEN evidence and can
    narrate the actual question."""
    report: dict[int, list[str]] = {}
    for beat in beats:
        sentences = [x for x in _SENTENCE_SPLIT_RE.split(beat.narration.strip()) if x.strip()]
        prior = ""
        for sent in sentences:
            if _ANSWER_VERB_RE.search(sent) and not _QUESTION_CUE_RE.search(prior):
                report[beat.beat_id] = ["dangling_reply"]
                break
            prior += " " + sent
    return report


def near_homophone_names(text: str, names: set[str]) -> list[str]:
    """Glossary name TOKENS that collide on audio, both present in the narration.

    "Mr. Song" (Song Chi-Yul) and "Mr. Sung" (Sung Jin-Woo) are one edit apart and
    near-identical from the TTS; the user's own dictation of the vote scene transcribed
    BOTH as "Mr. Sung". A viewer cannot tell who counts the hands from who is being
    asked. Warn-only: the fix is a wording choice (use the given name for one of them),
    not a glossary repair, and the writer cannot be blocked for the source material
    naming two characters a vowel apart.
    """
    tokens: set[str] = set()
    for name in names:
        for tok in re.findall(r"[A-Za-z][a-z]+", name):
            if len(tok) >= 3:
                tokens.add(tok)

    def _close(a: str, b: str) -> bool:
        if a == b or abs(len(a) - len(b)) > 1:
            return False
        # A plural is not a different NAME. "Player / players" fired on Frozen Player
        # ch3-4 because the glossary holds the term "Player" and the narration also says
        # "players" — one edit apart, and completely unambiguous to a listener.
        lo_a, lo_b = sorted((a.lower(), b.lower()), key=len)
        if lo_b in (lo_a + "s", lo_a + "'s") or lo_b == lo_a:
            return False
        # edit distance 1 on lowercase, cheap two-pointer
        a, b = a.lower(), b.lower()
        if len(a) == len(b):
            return sum(x != y for x, y in zip(a, b)) == 1
        if len(a) > len(b):
            a, b = b, a
        i = j = diff = 0
        while i < len(a) and j < len(b):
            if a[i] == b[j]:
                i += 1
            else:
                diff += 1
                if diff > 1:
                    return False
            j += 1
        return True

    present = {t for t in tokens if re.search(rf"\b{re.escape(t)}\b", text)}
    hits = []
    for a in sorted(present):
        for b in sorted(present):
            if a < b and _close(a, b):
                hits.append(f"{a} / {b}")
    return hits
