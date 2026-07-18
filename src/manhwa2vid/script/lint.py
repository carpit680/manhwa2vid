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
from manhwa2vid.llm.provider import get_llm_provider
from manhwa2vid.models import PanelCast, ScriptBeat, SeriesBible

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

_REWRITE_PROMPT = """Rewrite this recap beat narration.

Rules:
- Keep the same plot meaning; confident Momoru-style story voice
- NEVER use these words/phrases: {ban_words}
- NEVER use hedging: possibly, likely, maybe, seems to, appears to, may be, highlighting, is seen, is shown
- Use names/pronouns/role descriptors from the cast list
- Prefer MC / the protagonist / he/him over repeating the full protagonist name after beat 1
- No narrator diary asides unless this is the single allowed aside
- Return JSON: {{"narration": "rewritten text"}}
"""


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


def lint_beats(
    beats: list[ScriptBeat],
    config: dict[str, Any],
    *,
    bible: SeriesBible | None = None,
    attribution: list[PanelCast] | None = None,
) -> dict[int, list[str]]:
    words = banned_words(config)
    report: dict[int, list[str]] = {}
    for beat in beats:
        hits = find_violations(beat.narration, words)
        if hits:
            report[beat.beat_id] = hits
    for beat_id, issues in lint_hedging(beats).items():
        report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    if bible:
        for beat_id, issues in lint_mc_name_spam(beats, bible, config).items():
            report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    for beat_id, issues in lint_aside_overuse(beats, config).items():
        report[beat_id] = list(dict.fromkeys([*report.get(beat_id, []), *issues]))
    if bible and attribution is not None:
        for beat_id, issues in lint_mc_attribution(beats, bible, attribution, config).items():
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
) -> str:
    sanitized = local_sanitize_narration(beat.narration)
    remaining = lint_beats(
        [ScriptBeat(beat_id=beat.beat_id, panel_ids=beat.panel_ids, narration=sanitized, character_ids=beat.character_ids)],
        config,
        bible=bible,
        attribution=attribution,
    )
    if beat.beat_id not in remaining:
        return sanitized

    llm = get_llm_provider(config=config)
    model_name = get_nested(config, "script", "model", default="gpt-4o-mini")
    if hasattr(llm, "model"):
        llm.model = model_name

    ban = ", ".join(banned_words(config))
    cast = _cast_for_panels(attribution, beat.panel_ids)
    issue_text = ", ".join(issues or remaining.get(beat.beat_id, []))
    user = (
        f"{naming_priority_rules(bible, config)}\n\n"
        f"Bible:\n{format_bible_for_prompt(bible)}\n\n"
        f"On-screen cast:\n{cast}\n\n"
        f"Issues to fix: {issue_text}\n"
        f"Beat id: {beat.beat_id}\n\n"
        f"Original narration:\n{beat.narration}"
    )
    for attempt in range(4):
        try:
            raw = llm.complete(_REWRITE_PROMPT.format(ban_words=ban), user, json_mode=True)
            data = json.loads(raw)
            result = str(data.get("narration", sanitized)).strip()
            return local_sanitize_narration(result)
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
) -> list[ScriptBeat]:
    attribution: list[PanelCast] = []
    if attribution_path.exists():
        attribution = [PanelCast.model_validate(a) for a in json.loads(attribution_path.read_text())]

    pre_sanitized = [
        ScriptBeat(
            beat_id=beat.beat_id,
            panel_ids=beat.panel_ids,
            narration=local_sanitize_narration(beat.narration),
            estimated_seconds=beat.estimated_seconds,
            character_ids=beat.character_ids,
        )
        for beat in beats
    ]

    report = lint_beats(pre_sanitized, config, bible=bible, attribution=attribution)
    if not report:
        return pre_sanitized

    hedge = sum(1 for issues in report.values() if any(i in ("possibly", "likely", "highlighting") or "hedge" in i for i in issues))
    name_spam = sum(1 for issues in report.values() if "mc_full_name_spam" in issues)
    asides = sum(1 for issues in report.values() if "aside_overuse" in issues)
    console.print(
        f"[yellow]Script lint:[/] {len(report)} beat(s) flagged "
        f"(hedges/name-spam/asides/banned/mc) — rewriting"
        + (f" [name-spam={name_spam}]" if name_spam else "")
        + (f" [asides={asides}]" if asides else "")
    )

    fixed: list[ScriptBeat] = []
    for beat in pre_sanitized:
        if beat.beat_id in report:
            new_text = rewrite_beat(beat, bible, attribution, config, issues=report[beat.beat_id])
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
    remaining = lint_beats(fixed, config, bible=bible, attribution=attribution)
    if remaining:
        console.print(f"[yellow]Script lint:[/] {len(remaining)} beat(s) still flagged after rewrite")
    return fixed
