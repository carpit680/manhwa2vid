"""The storyboard reviewer: checks a narration against the story it was written from.

Replaces the pairwise script judge, which compared two narrations to EACH OTHER with no
knowledge of the chapter — and duly split nearly every comparison it was given
("0v1: split; 0v2: split" in this project's own logs). You cannot rank "tells the story
right" without knowing the story.

So this agent gets the source the judge never had: the chapter's time map
(`synopsis.narrative_structure`), its act arc, the ordered plot_beats, and the
deterministically computed scene boundaries — including the transition captions the
artwork itself prints. Its job is the half the viewer cannot do: the viewer can say "I got
lost here" but has no idea what SHOULD have been said. This one does, so it returns a
`fix_hint` that is a usable sentence rather than a complaint.

Few-shot on purpose. The one prompt device that measurably moved this pipeline's output
was the register block's worked exemplars — the first simile appeared immediately after
that rewrite — while four separate zero-shot RULES about marking time jumps all failed.
Rules get satisfied; examples get imitated. Hence the BAD -> GOOD pair below, and hence
every fix_hint being written as a model sentence the rewriter can imitate rather than an
instruction it can decline.

Bounded by design: hints route through the same `rewrite_beat` -> `accept_rewrite` ->
polish -> gates path as every other rewrite. This agent proposes; nothing here ships text.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.llm.provider import apply_stage_model, get_stage_llm
from manhwa2vid.models import ChapterSynopsis, ScriptBeat

console = Console()


class StoryProblem(BaseModel):
    beat_id: int = 0
    problem: str = ""
    fix_hint: str = ""


class StoryReview(BaseModel):
    transitions: list[StoryProblem] = Field(default_factory=list)
    order_problems: list[StoryProblem] = Field(default_factory=list)
    misportrayals: list[StoryProblem] = Field(default_factory=list)
    sequence_ok: bool = True
    score: int = 0

    @property
    def problems(self) -> list[StoryProblem]:
        return [*self.transitions, *self.order_problems, *self.misportrayals]


# "checking a narration against the storyboard" must not collide with any other mock
# branch ("You are watching a recap video", "Pick the one a viewer would rather listen
# to", "beat-by-beat", "rewrite this recap beat", "Choose the better narration", ...).
_REVIEW_PROMPT = """You are checking a narration against the storyboard it was written
from. You can see the chapter's real structure; the narrator's audience cannot. Your job
is to catch places where the telling does not match the story.

Report three kinds of problem, and nothing else:

TRANSITIONS — the storyboard marks a scene or time boundary at a beat, and the narration
crosses it without telling the listener. This is the most damaging error there is: a
listener who does not know the story has moved thinks the new scene is a continuation of
the last one.

  BAD:  "...the blade comes down and everything goes white. A crowd gathers around the
         glass case, and a boy points at one of the statues."
  GOOD: "...the blade comes down and everything goes white. Twenty years later, that war
         is something children look at behind glass. A boy points at one of the statues
         and swears it moved."

  The GOOD version says the interval out loud, in the first sentence of the new beat, and
  makes the new scene's relationship to the old one obvious. When the storyboard tells you
  the ART prints an interval, use those words.

ORDER — the narration tells something before or after where the storyboard puts it.

MISPORTRAYAL — a beat's point is wrong: the wrong person acts, a scene's meaning is
inverted, an outcome is reversed.

For every problem give the beat_id, one plain sentence saying what is wrong, and a
fix_hint that is A SENTENCE THE NARRATOR COULD SAY, written for THIS story using the
names and intervals in the storyboard below. Not advice — the actual words. "Open with:
'Twenty-five years later, ...'" is useful; "mark the transition" is not.

Report only real problems. A narration that handles its boundaries gets empty lists and
sequence_ok true.

Return ONE JSON object:
{"transitions": [{"beat_id": 9, "problem": "...", "fix_hint": "..."}],
 "order_problems": [], "misportrayals": [],
 "sequence_ok": false, "score": 6}"""


def _storyboard(
    beats: list[ScriptBeat],
    synopsis: ChapterSynopsis | None,
    boundaries: dict[int, str],
    lessons: list[str],
) -> str:
    parts: list[str] = []
    if synopsis is not None:
        if synopsis.logline:
            parts.append(f"What the chapter is about: {synopsis.logline}")
        if getattr(synopsis, "narrative_structure", ""):
            parts.append(f"How time moves in it: {synopsis.narrative_structure}")
        if synopsis.arc:
            parts.append("Acts:\n" + "\n".join(f"  {i}. {a}" for i, a in enumerate(synopsis.arc, 1)))
    if boundaries:
        parts.append(
            "SCENE / TIME BOUNDARIES the storyboard marks — each of these beats begins a "
            "new scene or time frame, and the narration must say so:\n"
            + "\n".join(f"  beat {bid}: {why}" for bid, why in sorted(boundaries.items()))
        )
    else:
        parts.append("SCENE / TIME BOUNDARIES: none — the chapter runs continuously.")
    if lessons:
        parts.append(
            "Known traps on this series (seen in earlier runs):\n"
            + "\n".join(f"  - {t}" for t in lessons[:8])
        )
    parts.append(
        "THE NARRATION, beat by beat:\n"
        + "\n".join(f"[beat {b.beat_id}] {b.narration.strip()}" for b in beats)
    )
    return "\n\n".join(parts)


def review_story(
    beats: list[ScriptBeat],
    synopsis: ChapterSynopsis | None,
    boundaries: dict[int, str],
    config: dict[str, Any],
    *,
    lessons: list[str] | None = None,
    llm: Any | None = None,
) -> StoryReview | None:
    """One structural review of one candidate. None when the call fails or is disabled."""
    if not get_nested(config, "script", "story_review", default=True) or not beats:
        return None
    llm = llm or apply_stage_model(get_stage_llm("script", config), "script", config)
    try:
        raw = llm.complete(
            _REVIEW_PROMPT, _storyboard(beats, synopsis, boundaries, lessons or []),
            json_mode=True,
        )
        return StoryReview.model_validate(json.loads(raw))
    except Exception as exc:
        console.print(f"[yellow]Story review failed ({type(exc).__name__})[/]")
        return None


def issues_by_beat(review: StoryReview, beats: list[ScriptBeat]) -> dict[int, list[str]]:
    """Structural problems as rewrite issues, with the model sentence attached.

    The hint travels verbatim: it was written to be imitated, and paraphrasing it back
    into advice is exactly how four zero-shot rules about time markers already failed.
    """
    valid = {b.beat_id for b in beats}
    out: dict[int, list[str]] = {}
    for problem in review.problems:
        if problem.beat_id not in valid or not problem.problem.strip():
            continue
        hint = problem.fix_hint.strip()
        out.setdefault(problem.beat_id, []).append(
            f"{problem.problem.strip()}"
            + (f' Write it like this: {hint}' if hint else "")
        )
    return out
