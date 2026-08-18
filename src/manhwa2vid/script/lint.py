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
                rf"(\b{re.escape(name)}),\s+(?:a|an|the)\s+(?:[\w''-]+\s+){{0,16}}[\w''-]+,",
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
            kept.append(sentence)
            seen.append(tokens)
        if len(kept) < len(sentences):
            out.append(beat.model_copy(update={"narration": " ".join(kept).strip()}))
        else:
            out.append(beat)
    return out


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
    per_panel = int(get_nested(config, "script", "words_per_panel_target", default=14))
    out: list[ScriptBeat] = []
    for beat in beats:
        limit = max(16, len(beat.panel_ids) * per_panel)
        hard = int(limit * 1.35)
        sentences = [s for s in _SENTENCE_SPLIT_RE.split(beat.narration.strip()) if s.strip()]
        if len(beat.narration.split()) <= hard or len(sentences) <= 2:
            out.append(beat)
            continue
        kept = list(sentences)
        while len(kept) > 2 and len(" ".join(kept).split()) > limit:
            kept.pop()
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
            next_word = after.split(None, 1)[0].strip(".,!?;:'\"") if after else ""
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
        if m.group(1).lower() in _OBJECT_PREV_WORDS and not _looks_like_verb(next_word):
            return f"{m.group(1)}{m.group(2)}{objective}"
        return m.group(0)

    return pattern.sub(_sub, text)


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
