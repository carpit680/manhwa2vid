"""Script linting and banned-word rewrite."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.characters.bible import format_bible_for_prompt, naming_priority_rules
from manhwa2vid.config import get_nested
from manhwa2vid.llm.provider import apply_stage_model, get_stage_llm
from manhwa2vid.models import PanelCast, SceneCard, ScriptBeat, SeriesBible
from manhwa2vid.script.grounding import (
    GROUNDING_KEYWORDS,
    evidence_for_panels,
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
_ASIDE_RE = re.compile(
    r"\b(ngl|no cap|lowkey|i mean|wait|bro|honestly)\b"
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
    r"now referred to|naming priority)\b",
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
- Write flowing sentences of roughly 9-16 words — cutting length must NOT mean chopping into staccato fragments
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
    max_after = int(get_nested(config, "script", "max_mc_full_name_after_hook", default=2))
    name_re = re.compile(re.escape(name), re.I)
    after_hook_hits = 0
    report: dict[int, list[str]] = {}
    for beat in beats:
        count = len(name_re.findall(beat.narration))
        if beat.beat_id <= 1:
            continue
        if count:
            after_hook_hits += count
            if after_hook_hits > max_after:
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


def lint_overlong_beats(
    beats: list[ScriptBeat],
    config: dict[str, Any],
) -> dict[int, list[str]]:
    """A beat's words are paid for in screen time by its panels; over budget = long
    static dwells. Flag with the concrete ceiling so the rewrite knows the target."""
    per_panel = int(get_nested(config, "script", "words_per_panel_target", default=14))
    # Allow some slack over the authoring target before forcing a rewrite.
    report: dict[int, list[str]] = {}
    for beat in beats:
        limit = max(16, len(beat.panel_ids) * per_panel)
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
            # "Kim Sangshik tells Jin-Woo to stay" must rotate to "tells HIM", not
            # "tells he" — narration is spoken aloud, so the case error is audible.
            last_word = re.search(r"([A-Za-z']+)\W*$", prior)
            replacement = (
                objective
                if last_word and last_word.group(1).lower() in _OBJECT_CUE_WORDS
                else pronoun
            )
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


def fix_pronoun_case(text: str, bible: SeriesBible) -> str:
    """Repair subject pronouns sitting in object position.

    Name rotation substitutes the subject form, so "Kim pats Jin-Woo on the shoulder"
    became "pats HE on the shoulder" — ungrammatical, and this text is SPOKEN, so the
    error is audible rather than cosmetic. A verb whitelist could not keep up (the miss
    was 'pats'); deciding on the word AFTER the pronoun does: a finite verb means the
    pronoun is a subject, anything else in mid-sentence means it is an object.
    """
    if not bible.protagonist_id or bible.protagonist_id not in bible.characters:
        return text
    pronoun = (bible.characters[bible.protagonist_id].pronoun or "he").lower()
    objective = {"he": "him", "she": "her", "they": "them"}.get(pronoun, "them")
    if objective == pronoun:
        return text

    # Word boundaries matter: without them "he" matches inside "the" and "shoulder".
    pattern = re.compile(
        r"(\S+\s+)\b" + re.escape(pronoun) + r"\b(?=(\s*)(\S*))",
        re.I,
    )

    def _sub(m: re.Match) -> str:
        before, after = m.group(1), m.group(3)
        # Clause-initial position stays nominative whatever preceded the break.
        if not before.strip() or before.strip().endswith((".", "!", "?", ",", ";", ":")):
            return m.group(0)
        # A finite verb after the pronoun means it is the subject of its own clause —
        # "says he is the weakest", "and he laughs".
        if _looks_like_verb(after):
            return m.group(0)
        return f"{before}{objective}"

    return pattern.sub(_sub, text)


def enforce_mc_name_budget(
    beats: list[ScriptBeat],
    bible: SeriesBible,
    config: dict[str, Any],
) -> list[ScriptBeat]:
    """Script-wide protagonist-name rotation — the deterministic twin of lint_mc_name_spam.

    Beat 1 (the hook) keeps one anchor; every later beat draws from a single shared
    budget, so the pass mirrors exactly what the lint rule measures. Per-beat rotation
    can never satisfy a script-wide rule, and asking the LLM to self-limit across beats
    it cannot see is hopeless.
    """
    max_after = int(get_nested(config, "script", "max_mc_full_name_after_hook", default=2))
    state = {"seen": 0}
    out: list[ScriptBeat] = []
    for beat in beats:
        if beat.beat_id <= 1:
            # The hook anchors the name; rotate only repeats within the beat itself.
            text = rotate_protagonist_name(beat.narration, bible, keep=1)
        else:
            text = rotate_protagonist_name(beat.narration, bible, keep=max_after, state=state)
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
        hits = [f"descriptor_for_named:{name}" for d, name in named_descriptors if d in low]
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
    for beat_id, issues in lint_overlong_beats(beats, config).items():
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
    if beat.beat_id not in remaining:
        return sanitized

    llm = llm or apply_stage_model(get_stage_llm("script", config), "script", config)

    ban = ", ".join(banned_words(config))
    cast = _cast_for_panels(attribution, beat.panel_ids)
    issue_text = ", ".join(issues or remaining.get(beat.beat_id, []))
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

    pre_sanitized = [
        ScriptBeat(
            beat_id=beat.beat_id,
            panel_ids=beat.panel_ids,
            narration=rotate_protagonist_name(local_sanitize_narration(beat.narration), bible),
            estimated_seconds=beat.estimated_seconds,
            character_ids=beat.character_ids,
        )
        for beat in beats
    ]

    # Script-wide name rotation must run BEFORE measuring: the per-beat rotation above
    # leaves one anchor per beat, which the script-wide spam rule then flags everywhere.
    pre_sanitized = enforce_mc_name_budget(pre_sanitized, bible, config)

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
            new_text = rewrite_beat(
                beat,
                bible,
                attribution,
                config,
                issues=report[beat.beat_id],
                scene_cards=scene_cards,
            )
            fixed.append(
                ScriptBeat(
                    beat_id=beat.beat_id,
                    panel_ids=beat.panel_ids,
                    narration=new_text,
                    estimated_seconds=beat.estimated_seconds,
                    character_ids=beat.character_ids,
                )
            )
        else:
            fixed.append(beat)
    # A rewrite re-introduces the full name freely (it sees only its own beat), so the
    # budget sweep runs again over the final text.
    fixed = enforce_mc_name_budget(fixed, bible, config)
    remaining = lint_beats(
        fixed, config, bible=bible, attribution=attribution, scene_cards=scene_cards
    )
    if remaining:
        console.print(f"[yellow]Script lint:[/] {len(remaining)} beat(s) still flagged after rewrite")
    return fixed