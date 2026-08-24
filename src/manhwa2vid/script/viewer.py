"""The viewer agent: somebody who actually listens to the narration.

Every gate in this pipeline checks the script against SOURCE material — do the panels
support this claim, did the outline's story survive, is every panel bound. Not one of
them ever asked the only question the product is judged on: *does this make sense and is
it any fun to listen to?*

That gap is exactly where the defects the reviewer keeps finding live. "Who broke out of
the ice?" and "the narration is blind to time skips" are not factual errors — every
sentence in those beats was true and panel-supported, and every gate passed them. They
are LISTENER-EXPERIENCE defects, and you can only find them from the listener's seat.

So this agent is given what a viewer is given and nothing else: the hook and the beat
text, in order, as continuous prose. No panels, no beat ids, no evidence, no bible. If a
character cannot be identified from the words alone, the viewer cannot identify them
either — which is the whole point. It returns quotes rather than beat numbers because a
listener does not know beat numbers; `beats_for_complaint` maps a quote back to a beat
using the same stemmed overlap the rest of the module uses, so a complaint becomes an
ordinary `issues=` payload for the rewrite loop that already exists.

This does NOT replace the panel-grounded audit. It ranks TELLING; `verify.py` still owns
TRUTH, and runs after whatever this selects.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.llm.provider import apply_stage_model, get_stage_llm
from manhwa2vid.models import ScriptBeat

console = Console()


class ViewerComplaint(BaseModel):
    quote: str = ""
    why: str = ""


class ViewerReport(BaseModel):
    lost: list[ViewerComplaint] = Field(default_factory=list)
    flat: list[ViewerComplaint] = Field(default_factory=list)
    best_moment: str = ""
    # Four independent 1-5 judgments instead of one scalar 1-10 score. Three visibly
    # different candidates once scored a flat 6/10 each from a single scalar ask — an LLM
    # has no resolution at that granularity, and the loop's ranking fell through to index
    # order. Separate axes spread out where one number collapses, and each is legible on
    # its own in the candidate logs.
    followable: int = 3   # could a listener track who/when/where throughout
    told_not_listed: int = 3  # events landed as a story, not a bulleted recitation
    payoffs_landed: int = 3   # the chapter's key reveals/stakes actually registered
    rhythm: int = 3           # sentence variety and pacing, not a monotone drone
    keep_watching: bool = True

    @property
    def score(self) -> float:
        """Sum of the four sub-scores, scaled to the legacy 1-10 band (max 20 -> /2) so
        the existing threshold (viewer-score >= 6) and ranking formula keep their meaning
        without every caller needing to know the scale changed."""
        return (self.followable + self.told_not_listed + self.payoffs_landed + self.rhythm) / 2.0

    @property
    def complaint_count(self) -> int:
        return len(self.lost) + len(self.flat)


# "You are watching a recap video" must not collide with any MockLLMProvider branch
# ("beat-by-beat", "rewrite this recap beat", "Choose the better narration", "fact-check",
# "panel sample", "annotate ONLY these", "Read it as a story", ...).
_VIEWER_PROMPT = """You are watching a recap video of a manhwa you have never read, on a
channel you subscribe to for fun. You are not an editor and not a fact-checker — you
cannot see the pages, you only hear the narrator. You scroll away the moment you get lost
or bored.

Two things make you stop watching, and you report ONLY these:

LOST — a moment where you could not follow. You do not know who "he" or "she" is. The
story jumped to another time or place and nobody told you. Somebody acts and you have no
idea who they are. A thing is referred to as if you already know it.

FLAT — a stretch that reads like somebody summarizing a plot instead of telling you a
story. Events listed one after another with no reaction, no stakes, nothing that makes
you care. If a passage would fit unchanged in a Wikipedia summary, it is flat.

For each, quote the EXACT words from the narration that made you feel it, and say why in
one plain sentence, as a viewer would put it.

Also name the single best moment, and rate FOUR separate things 1-5 (1=bad, 5=great) — do
not just repeat the same number four times, they usually differ:
- followable: could you track who/when/where the whole way through
- told_not_listed: did it feel like a STORY, not a list of things that happened
- payoffs_landed: did the big reveals/stakes actually land and register with you
- rhythm: did the sentences vary in length and pace, or drone on the same way

Say whether you would keep watching.

Be honest and specific. A narration with no problems gets empty lists — do not invent
complaints to seem useful.

Return ONE JSON object:
{"lost": [{"quote": "...", "why": "..."}],
 "flat": [{"quote": "...", "why": "..."}],
 "best_moment": "...", "followable": 4, "told_not_listed": 3, "payoffs_landed": 4,
 "rhythm": 3, "keep_watching": true}"""


def as_listener_hears(beats: list[ScriptBeat], hook: str = "") -> str:
    """The narration as continuous speech — no ids, no structure, no scaffolding."""
    parts = [hook.strip()] if hook.strip() else []
    parts += [b.narration.strip() for b in beats if b.narration.strip()]
    return "\n\n".join(parts)


def review_script(
    beats: list[ScriptBeat],
    hook: str,
    config: dict[str, Any],
    *,
    llm: Any | None = None,
) -> ViewerReport | None:
    """One viewer's reaction to one candidate. None when the call fails or is disabled."""
    if not get_nested(config, "script", "viewer_review", default=True):
        return None
    if not beats:
        return None
    llm = llm or apply_stage_model(get_stage_llm("script", config), "script", config)
    try:
        raw = llm.complete(_VIEWER_PROMPT, as_listener_hears(beats, hook), json_mode=True)
        return ViewerReport.model_validate(json.loads(raw))
    except Exception as exc:
        console.print(f"[yellow]Viewer review failed ({type(exc).__name__})[/]")
        return None


def beats_for_complaint(quote: str, beats: list[ScriptBeat]) -> list[int]:
    """Map a viewer's quote back to the beat(s) it came from.

    Exact substring first, since the viewer is asked to quote verbatim. Falling back to
    stemmed overlap matters more than it looks: models paraphrase quotes constantly, and
    a complaint that cannot be located is a complaint that silently does nothing.
    """
    from manhwa2vid.script.lint import _stemmed_words

    needle = " ".join(quote.split()).strip().lower()
    if not needle:
        return []
    hits = [b.beat_id for b in beats if needle in " ".join(b.narration.split()).lower()]
    if hits:
        return hits
    q = _stemmed_words(quote)
    if not q:
        return []
    scored = [
        (len(q & _stemmed_words(b.narration)) / len(q), b.beat_id)
        for b in beats
    ]
    best_score, best_id = max(scored, default=(0.0, 0))
    return [best_id] if best_score >= 0.5 else []


def issues_by_beat(report: ViewerReport, beats: list[ScriptBeat]) -> dict[int, list[str]]:
    """Viewer complaints as rewrite issues, keyed by beat.

    Phrased as the viewer phrased them. A rewrite prompt that says "a viewer could not
    tell who 'he' is here" carries the failure a rule-shaped instruction loses.
    """
    out: dict[int, list[str]] = {}
    for kind, items in (("could not follow", report.lost), ("read as flat", report.flat)):
        for item in items:
            for beat_id in beats_for_complaint(item.quote, beats):
                out.setdefault(beat_id, []).append(
                    f'a viewer {kind} this: "{item.quote.strip()[:80]}" — {item.why.strip()}'
                )
    return out
