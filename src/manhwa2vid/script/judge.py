"""Pairwise judge: decide BETWEEN two candidate narrations instead of scoring one.

The alignment audit is an ABSOLUTE test — "list claims these panels do not support" —
and on failure the pipeline substituted outline text that was never judged at all. Two
problems with that, both observed:

1. **The substitution was unjudged.** We discarded an artefact we had evaluated in
   favour of one we had not. Outline prose is a synopsis written for panel-binding; it
   is not narration, and it was winning by default.

2. **Absolute tests are decided by SHARED confounds.** Four of five "major
   misattributions" in one run came from the cast sheet describing a character in a way
   the art had moved past (a president called "bald" from a dialogue joke; a masked
   swordsman now in hospital pyjamas). That confound sits in BOTH candidates equally —
   so under an absolute test it determines the outcome, while under a comparative test
   it cancels and the judge is forced to discriminate on what actually differs.

Known judge biases and what is done about them here:
  - POSITION bias: every comparison runs twice with the candidates swapped, and only an
    agreeing verdict counts. Disagreement means the judge cannot tell them apart, which
    is itself the answer — the caller's default wins.
  - VERBOSITY bias: judges prefer longer text, and outline prose is denser than
    narration, so this bias points exactly the wrong way for us. The prompt says
    outright that length is not a criterion.

Scope limit, deliberately: this fixes the DECISION, not DETECTION. The absolute verifier
still produces the claim list that drives rewrites, and no judge can discover a defect
that neither candidate exposes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.llm.provider import apply_stage_model, get_stage_llm
from manhwa2vid.models import Panel

console = Console()

MAX_JUDGE_PANELS = 8

# Must not collide with any MockLLMProvider vision branch ("fact-check", "panel sample",
# "annotate ONLY these", ...) or the mock silently answers with the wrong shape.
_JUDGE_PROMPT = """Choose the better narration for one beat of a manhwa recap video.
You see the beat's actual panels, then two candidates labelled A and B.

Rank on these criteria, in this order:
1. SUPPORTED — every claim matches what these panels actually show; the right person
   says and does the right thing.
2. ATTRIBUTION — speech and action belong to whoever the panels show performing them.
3. NARRATION — it tells the moment as a story someone would listen to, rather than
   summarizing it as a plot note.

Length is NOT a criterion. A shorter candidate that is accurate and reads as narration
beats a longer one that is dense or list-like. Ignore which candidate is longer.

Clothing, masks, injuries and posture change between scenes: a candidate is not wrong
merely because a character looks different from another scene.

Return ONE JSON object: {"winner": "A" or "B", "why": "one short sentence"}"""


def _panel_paths(panels: list[Panel], project_root: Path) -> list[Path]:
    out: list[Path] = []
    for panel in panels[:MAX_JUDGE_PANELS]:
        path = project_root / panel.image_path
        if path.exists():
            out.append(path)
    return out


def _ask(llm: Any, images: list[Path], first: str, second: str) -> str | None:
    """One comparison. Returns "A"/"B" as labelled in THIS call, or None."""
    prompt = f"{_JUDGE_PROMPT}\n\nCandidate A:\n{first}\n\nCandidate B:\n{second}"
    try:
        raw = llm.describe_panels(images, prompt)
        data = json.loads(raw)
    except Exception as exc:
        console.print(f"[yellow]Judge call failed ({type(exc).__name__})[/]")
        return None
    winner = str(data.get("winner", "")).strip().upper()
    return winner if winner in {"A", "B"} else None


def pick_better(
    panels: list[Panel],
    project_root: Path,
    config: dict[str, Any],
    a_text: str,
    b_text: str,
    *,
    a_label: str = "A",
    b_label: str = "B",
    default: str = "a",
    llm: Any | None = None,
) -> tuple[str, str]:
    """Return (winning_text, reason). `default` ("a"/"b") wins ties and failures.

    The comparison runs twice with the candidates swapped; only an agreeing verdict
    counts, so a judge that merely prefers the first slot cannot decide anything.
    """
    if not a_text.strip():
        return b_text, f"{a_label} was empty"
    if not b_text.strip():
        return a_text, f"{b_label} was empty"

    fallback = (a_text, f"judge undecided — kept {a_label}") if default == "a" else (
        b_text, f"judge undecided — kept {b_label}"
    )
    if not get_nested(config, "script", "pairwise_judge", default=True):
        return fallback
    images = _panel_paths(panels, project_root)
    if not images:
        return fallback

    llm = llm or apply_stage_model(get_stage_llm("scene", config), "scene", config)
    first = _ask(llm, images, a_text, b_text)          # A=a_text
    second = _ask(llm, images, b_text, a_text)         # A=b_text (swapped)
    if first is None or second is None:
        return fallback
    # Translate both verdicts into "did a_text win?"
    a_won_first = first == "A"
    a_won_second = second == "B"
    if a_won_first != a_won_second:
        return fallback
    if a_won_first:
        return a_text, f"{a_label} preferred over {b_label} (both orderings)"
    return b_text, f"{b_label} preferred over {a_label} (both orderings)"


# Separate from _JUDGE_PROMPT: that one ranks a single beat against its panels and owns
# accuracy. This one ranks whole scripts on TELLING, with no images at all — both
# candidates were written from the same evidence, so accuracy is held equal here and the
# panel-grounded audit still runs on whatever wins. Must not collide with any mock branch.
_SCRIPT_JUDGE_PROMPT = """Two narrations of the same manhwa chapter, for a recap video.
Pick the one a viewer would rather listen to.

Judge on these, in order:
1. FOLLOWABLE — a listener who cannot see the pages always knows who is acting and when
   the story has moved in time or place. Jumps are spoken, not implied.
2. TOLD, NOT LISTED — it sounds like a person telling you what happened, with stakes and
   reactions, rather than a plot summary read aloud.
3. RHYTHM — sentences vary; some land short and hard. A wall of same-length statements is
   worse than a mix.

Both were written from the same source, so assume they are equally accurate and do not
try to fact-check them. Length is NOT a criterion.

Return ONE JSON object: {"winner": "A" or "B", "why": "one short sentence"}"""


def _ask_text(llm: Any, first: str, second: str) -> str | None:
    prompt = f"Candidate A:\n{first}\n\nCandidate B:\n{second}"
    try:
        raw = llm.complete(_SCRIPT_JUDGE_PROMPT, prompt, json_mode=True)
        winner = str(json.loads(raw).get("winner", "")).strip().upper()
    except Exception as exc:
        console.print(f"[yellow]Script judge call failed ({type(exc).__name__})[/]")
        return None
    return winner if winner in {"A", "B"} else None


def pick_best_script(
    candidates: list[str],
    config: dict[str, Any],
    *,
    tiebreak: list[float] | None = None,
    llm: Any | None = None,
) -> tuple[int, str]:
    """Index of the best candidate, plus a one-line trace of how it was chosen.

    A knockout run down the list: the current champion meets the next candidate, and each
    meeting is judged TWICE with the order swapped so a judge that merely prefers the
    first slot decides nothing. When the two orderings disagree the judge genuinely cannot
    separate them, and `tiebreak` (the viewer scores) settles it — falling back to the
    earlier index, which keeps the whole selection deterministic given fixed model output.

    K candidates cost 2*(K-1) small text calls: three candidates is four calls.
    """
    if not candidates:
        return 0, "no candidates"
    if len(candidates) == 1:
        return 0, "single candidate"
    scores = tiebreak or [0.0] * len(candidates)
    llm = llm or apply_stage_model(get_stage_llm("script", config), "script", config)

    champion = 0
    notes: list[str] = []
    for challenger in range(1, len(candidates)):
        first = _ask_text(llm, candidates[champion], candidates[challenger])
        second = _ask_text(llm, candidates[challenger], candidates[champion])
        if first is None or second is None:
            notes.append(f"{champion}v{challenger}: judge unavailable")
            continue
        champ_won = (first == "A") and (second == "B")
        chall_won = (first == "B") and (second == "A")
        if chall_won:
            notes.append(f"{challenger} beat {champion}")
            champion = challenger
        elif champ_won:
            notes.append(f"{champion} beat {challenger}")
        else:
            better = challenger if scores[challenger] > scores[champion] else champion
            notes.append(f"{champion}v{challenger}: split, viewer score kept {better}")
            champion = better
    return champion, "; ".join(notes) or "no comparisons"
