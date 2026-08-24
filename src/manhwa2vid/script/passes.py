"""Targeted few-shot rewrite passes for two defect classes generic rewrites keep failing.

Both classes showed up in EVERY sampled candidate across two separate Frozen Player runs
— the world-history beats read like a textbook and the 25-year jump felt abrupt in all
six candidates, whether or not the jump was marked. A defect present in 100% of samples
is not a selection problem, so raising K or rewriting against a generic issue list cannot
fix it; a targeted pass with a worked example is the one prompt device this project has
measured moving voice reliably (register exemplars did; four zero-shot rules about time
markers did not).

Each pass rewrites ONE beat against ONE worked BAD->GOOD example lifted from the
reference channel's own handling, with invented names so nothing here is series-specific.
Both go through the same well-formedness backstop (`accept_rewrite`) every other rewrite
in this pipeline uses, so a pass can never ship something worse-formed than what it
started from.
"""

from __future__ import annotations

import re
from typing import Any

from manhwa2vid.characters.bible import format_bible_for_prompt, naming_priority_rules
from manhwa2vid.models import PanelCast, SceneCard, ScriptBeat, SeriesBible
from manhwa2vid.script.grounding import evidence_for_panels, split_utterances
from manhwa2vid.script.lint import (
    _cast_for_panels,
    _clean_prose_reply,
    accept_rewrite,
    banned_words,
    local_sanitize_narration,
    rotate_protagonist_name,
)
from manhwa2vid.llm.provider import apply_stage_model, get_stage_llm
from manhwa2vid.script.scorecard import _TIME_MARK_RE

_PLACE_CUE_RE = re.compile(
    r"\b(?:earlier|later|meanwhile|back (?:at|in)|elsewhere|now|then|before (?:all )?this)\b",
    re.I,
)

# "REWRITE THIS TRANSITION BEAT" must not collide with any MockLLMProvider branch —
# "rewrite this recap beat" (generic rewrite) is the nearest neighbor.
_TRANSITION_PROMPT = """REWRITE THIS TRANSITION BEAT so a LISTENER hears the story move, not just the picture change.

The reference channel this pipeline imitates never marks a time or scene cut with a bare
description of the new setting — it moves in three parts: close the old scene with a
consequence, jump WITH orientation (when/where), and land an immediate stake. Marking the
jump alone still reads as abrupt without the other two parts.

BAD (marks the jump but reads as a caption):
"Twenty years ago in the northern wastes, a towering ice pillar stands amid a swirling blizzard."

GOOD (closes the old scene, jumps with orientation, lands a stake):
"That's the last thing Doran sees for twenty years. Now, three days before this fight,
five hunters are standing in front of that same gate, and there's a problem — only one
of them can go up those stairs."

Rules:
- Open by closing out the PREVIOUS beat (you are given its last sentence) in one clause
- Then mark the jump with a concrete time/place cue
- Then land a stake or consequence in the SAME beat — never end on the orientation alone
- Keep the same plot meaning as the original narration; invent nothing outside the panel evidence
- NEVER use these words/phrases: {ban_words}
- NEVER quote dialogue verbatim or use quotation marks — convert to reported speech
- PRESENT tense, confident story voice, 1-3 sentences
"""

# "REWRITE THIS EXPOSITION BEAT" must not collide with any MockLLMProvider branch.
_EXPOSITION_PROMPT = """REWRITE THIS EXPOSITION BEAT by telling it through a PERSON, not as a list of facts.

A stretch of world-lore or backstory read as events-that-happened is flat — it is the
narrator reciting a Wikipedia paragraph. The fix is never to add adjectives; it is to
put the information in someone's mouth and show how the LISTENER-STAND-IN reacts to
hearing it, the way the reference channel always does.

BAD (facts, no person, no reaction):
"In the twenty years since the siege ended, the order has only cleared one additional
floor of the tower."

GOOD (a person says it, another person reacts to it):
"Vesh can barely get the words out. In twenty years, the order has cleared exactly one
more floor. Doran almost falls over."

Rules:
- Identify who in this beat's evidence would plausibly SAY this information, and who
  would hear it — use the panel evidence and cast list, never invent a new person
- Show the listener's reaction in the same beat (a gesture, a reply, a feeling) — the
  reaction is what turns a fact into a moment
- Keep the same plot meaning as the original narration; invent nothing outside the panel evidence
- NEVER use these words/phrases: {ban_words}
- NEVER quote dialogue verbatim or use quotation marks — convert to reported speech
- PRESENT tense, confident story voice, 1-3 sentences
"""


def transition_needs_rework(beat: ScriptBeat) -> bool:
    """A boundary beat still reads as a continuation unless it opens with a cue AND has
    room after the cue for a consequence — a single-sentence beat cannot hold both."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", beat.narration.strip()) if s.strip()]
    if len(sentences) < 2:
        return True
    head = " ".join(sentences[:2])
    has_cue = bool(_TIME_MARK_RE.search(head)) or bool(_PLACE_CUE_RE.search(head))
    return not has_cue


def is_dialogue_heavy_exposition(beat: ScriptBeat, cards: list[SceneCard]) -> bool:
    """This beat's panels are mostly people TALKING about the world, not acting in it —
    the shape the reference tells through a person's reaction rather than as events."""
    by_panel = {pid: c for c in cards for pid in c.panel_ids}
    monologue_words = 0
    action_words = 0
    for pid in beat.panel_ids:
        card = by_panel.get(pid)
        if card is None:
            continue
        addressed, monologue, unattributed = split_utterances(card.source_text)
        monologue_words += sum(len(line.split()) for line in [*addressed, *monologue])
        action_words += len((card.action or "").split())
    total = monologue_words + action_words
    return total > 0 and monologue_words / total >= 0.6


def rewrite_transition(
    beat: ScriptBeat,
    prev_beat: ScriptBeat | None,
    bible: SeriesBible,
    attribution: list[PanelCast],
    config: dict[str, Any],
    *,
    scene_cards: list[SceneCard] | None = None,
    llm: Any | None = None,
) -> str:
    """Rewrite a beat that OPENS a scene/time boundary using the reference's 3-part move."""
    llm = llm or apply_stage_model(get_stage_llm("script", config), "script", config)
    ban = ", ".join(banned_words(config))
    cast = _cast_for_panels(attribution, beat.panel_ids)
    evid = evidence_for_panels(beat.panel_ids, scene_cards or [])
    prev_sentence = ""
    if prev_beat is not None:
        sentences = [s.strip() for s in prev_beat.narration.split(".") if s.strip()]
        prev_sentence = (sentences[-1] + ".") if sentences else ""
    user = (
        f"{naming_priority_rules(bible, config)}\n\n"
        f"Bible:\n{format_bible_for_prompt(bible)}\n\n"
        f"On-screen cast:\n{cast}\n\n"
        f"Panel EVIDENCE (narrate ONLY this):\n{evid}\n\n"
        f"Previous beat's last sentence (close it out before jumping):\n"
        f"{prev_sentence or '(this is the opening beat — nothing precedes it)'}\n\n"
        f"Beat id: {beat.beat_id}\n\n"
        f"Original narration:\n{beat.narration}"
    )
    try:
        raw = llm.complete(_TRANSITION_PROMPT.format(ban_words=ban), user, json_mode=False)
        result = _clean_prose_reply(raw)
    except Exception:
        return beat.narration
    if not result:
        return beat.narration
    return accept_rewrite(beat.narration, rotate_protagonist_name(local_sanitize_narration(result), bible))


def rewrite_exposition(
    beat: ScriptBeat,
    bible: SeriesBible,
    attribution: list[PanelCast],
    config: dict[str, Any],
    *,
    scene_cards: list[SceneCard] | None = None,
    llm: Any | None = None,
) -> str:
    """Rewrite a beat the viewer marked flat, telling its facts through a person's reaction."""
    llm = llm or apply_stage_model(get_stage_llm("script", config), "script", config)
    ban = ", ".join(banned_words(config))
    cast = _cast_for_panels(attribution, beat.panel_ids)
    evid = evidence_for_panels(beat.panel_ids, scene_cards or [])
    user = (
        f"{naming_priority_rules(bible, config)}\n\n"
        f"Bible:\n{format_bible_for_prompt(bible)}\n\n"
        f"On-screen cast:\n{cast}\n\n"
        f"Panel EVIDENCE (narrate ONLY this):\n{evid}\n\n"
        f"Beat id: {beat.beat_id}\n\n"
        f"Original narration:\n{beat.narration}"
    )
    try:
        raw = llm.complete(_EXPOSITION_PROMPT.format(ban_words=ban), user, json_mode=False)
        result = _clean_prose_reply(raw)
    except Exception:
        return beat.narration
    if not result:
        return beat.narration
    return accept_rewrite(beat.narration, rotate_protagonist_name(local_sanitize_narration(result), bible))
