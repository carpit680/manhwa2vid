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

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_PRONOUN_START_RE = re.compile(r"^(?:He|She|They|His|Her|Their)\b")


def lint_captioning(beats: list[ScriptBeat]) -> dict[int, list[str]]:
    """Flag beats written as image descriptions instead of story."""
    report: dict[int, list[str]] = {}
    for beat in beats:
        hits = sorted({m.group(0).lower() for m in _CAPTION_RE.finditer(beat.narration)})
        if hits:
            report[beat.beat_id] = [f"caption:{h}" for h in hits[:3]]
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
) -> int:
    """The single source of truth for a beat's word budget.

    Three forces, minimum wins: the panel-driven budget (words the beat's screen time
    can pay for), the absolute per-beat ceiling, and — new — the share of the CHAPTER
    budget. Until now no total-length target existed anywhere: per-beat caps summed to
    1,680 words for a two-chapter project whose reference narration runs 979. Length was
    an emergent accident of beats x panel density. words_per_chapter (measured: the
    reference channel ~490/chapter, the two golds 525 and 677) makes runtime a chosen
    number, since narration is audio-locked and word count IS runtime.
    """
    per_panel = int(get_nested(config, "script", "words_per_panel_target", default=14))
    ceiling = int(get_nested(config, "script", "max_beat_words", default=60))
    cap = min(max(16, n_panels * per_panel), ceiling)
    if n_beats > 0:
        per_chapter = int(get_nested(config, "script", "words_per_chapter", default=550))
        share = round(per_chapter * max(1, n_chapters) / n_beats * 1.2)
        cap = min(cap, max(20, share))
    return cap


def trim_overlong_beats(
    beats: list[ScriptBeat],
    config: dict[str, Any],
) -> list[ScriptBeat]:
    """Enforce the per-beat word cap by dropping trailing sentences.

    Every word over budget stretches this beat's panels on screen, because audio locks
    the visuals. The cap has been in the prompt and the lint for days and the rewrite
    ignores it (4 flagged -> 3 still flagged). Trailing sentences are where the padding
    accumulates — the beat's own point is made first. Always keeps at least two
    sentences so a beat is never gutted.
    """
    out: list[ScriptBeat] = []
    n_chapters = int(config.get("_n_chapters", 1)) if isinstance(config, dict) else 1
    for beat in beats:
        limit = beat_word_cap(len(beat.panel_ids), config, n_beats=len(beats), n_chapters=n_chapters)
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
) -> dict[int, list[str]]:
    """A beat's words are paid for in screen time by its panels; over budget = long
    static dwells. Flag with the concrete ceiling so the rewrite knows the target."""
    # Allow some slack over the authoring target before forcing a rewrite.
    report: dict[int, list[str]] = {}
    n_chapters = int(config.get("_n_chapters", 1)) if isinstance(config, dict) else 1
    for beat in beats:
        limit = beat_word_cap(len(beat.panel_ids), config, n_beats=len(beats), n_chapters=n_chapters)
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
        if (profile.pronoun or "").lower() != mc_pron:
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
    for beat in beats:
        ambiguous = any(rx.search(beat.narration) for rx in rival_res)
        anchor_here = beat.beat_id <= 1 or beats_since_anchor >= cadence or ambiguous
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
_ECHOED_AGENT_RE = re.compile(r"\b(an?)\s+([a-z][\w'’-]*)\s+and\s+(an?)\s+\2\b", re.I)


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
        stranded = _ARTICLE_PRONOUN_RE.search(beat.narration)
        # A stranded determiner heads a SUBJECT, so a verb has to follow the pronoun.
        # Without that test the object pronoun in "The healer treats him after the raid"
        # matched — article, two words, pronoun — and flagged a correct sentence.
        if stranded:
            after = beat.narration[stranded.end():].split()
            if not after or not _looks_like_verb(after[0]):
                stranded = None
            # A conjunction or preposition between the determiner and the pronoun means a
            # new clause started and the pronoun heads THAT one: "he is used to the pain
            # because he is weak" matches article + two words + pronoun + verb and is
            # perfectly correct. Only an unbroken determiner-modifier-pronoun run is wrong.
            elif _CLAUSE_BREAKERS & {w.lower().strip(",") for w in stranded.group(0).split()}:
                stranded = None
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
    if beat.beat_id not in remaining:
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
            new_text = rewrite_beat(
                beat,
                bible,
                attribution,
                config,
                issues=report[beat.beat_id],
                scene_cards=scene_cards,
            )
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
    r"newcomer|leader|healer|veteran|fighter|mage|kid|youth|boy|girl|stranger"
)
_GARMENT = (
    r"collar|jacket|cap|hat|coat|shirt|hoodie|glasses|hair|beard|goatee|backpack|"
    r"uniform|vest|scarf|boots|gloves|mask"
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
    # ...plus any further descriptors chained onto it ("and a goatee", "and grey hair"),
    # or the strip leaves a dangling conjunction behind.
    rf"(?:\s*,?\s*and\s+(?:a|an|the)?\s*(?:[\w'’-]+\s+){{0,3}}(?:{_GARMENT})\b)*",
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

    Only indefinite noun phrases match, so a definite reference the story depends on
    ("the man in the blue cap" as a running identifier) is left alone, as is any phrase
    whose head noun is not a person.
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


def _is_trailing_closer_sentence(sentence: str) -> bool:
    return bool(_TRAILING_CLOSER_RE.search(sentence) or _QUESTION_OPENER_RE.match(sentence))


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
