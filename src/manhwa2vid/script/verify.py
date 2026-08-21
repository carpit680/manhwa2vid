"""Adversarial frame-alignment audit.

A second VLM pass with a verifier persona — not the co-author that wrote the scene cards —
looks at each beat's actual panels next to its narration and lists claims the images do not
support. This is the check that catches "the weakest hunter boasts about being highest
ranked" over a panel he is not even in.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress

from manhwa2vid.config import get_nested
from manhwa2vid.llm.provider import apply_stage_model, get_stage_llm
from manhwa2vid.models import Panel, ScriptBeat, SeriesBible
from manhwa2vid.qa import QAReport

console = Console()

# Panels are already downscaled to vision_max_side, so a beat's whole set costs little.
# The cap only guards against a pathological beat (a collapsed outline can hand over 30+).
_MAX_AUDIT_PANELS = 8

_VERIFY_PROMPT = """You are a fact-checker for a manhwa recap channel. This is a fact-check task.
You see the actual panels for one narration beat. List claims the images do NOT support.

Who's who in this series (match people by these visual descriptions):
{cast}

Names are established series-wide, NOT from these panels alone. A panel never captions
its characters, so "this person is not named in the panel" is NEVER a finding. Judge a
naming claim ONLY against the visual descriptions above:
- If someone matching the description is visible, the name is SUPPORTED.
- Flag a name ONLY when the visible person clearly CONTRADICTS that description
  (wrong hair, wrong outfit, wrong sex, wrong age) or when nobody is visible at all.
- If the description is too thin to tell either way, the claim is SUPPORTED. Say nothing.

Each cast entry lists STABLE marks and CURRENT-STATE marks. Only STABLE marks can
contradict an identity: clothing, masks, hairstyle/baldness, injuries, posture and
condition change from scene to scene within one recap, so a mismatch there is NEVER a
finding — the same person in different clothes is the same person.

severity=major ONLY for story-breaking errors:
- an action or line attributed to a person who contradicts that person's STABLE marks
- a named person claimed ON-SCREEN when NOBODY matching their STABLE marks is visible.
  NOT a finding when the beat reports what that person THINKS or SAYS: a manhwa runs
  inner monologue over whatever art it likes, so a panel drawn on one character while
  another character's bubble carries first-person thought belongs to whoever SAYS it,
  and the narration is SUPPORTED. Attribution follows the bubble, never who is drawn.
- an event, object handoff, or location that does not appear at all
- a reported line given to the WRONG SPEAKER, or aimed at the WRONG LISTENER —
  read the bubble text in the panels: its tail points at the speaker, a name in
  the words ('MR. SONG, take care of us') names who is addressed, and first-person
  content ('MY sick mother') belongs to whoever says it, not to a group

severity=minor for everything else. Explicitly NOT unsupported (do not list at all):
- reasonable paraphrase or interpretation of what is visible
- texture/color/material quibbles (e.g. 'cracked pavement' vs 'stone pavement')
- left/right, near/far, or count-off-by-one details
- emotional readings consistent with the expression shown
- narration of sounds implied by the art (a strike landing, a gasp)
- a name you merely cannot confirm from the art
- summarization: a beat covers SEVERAL panels at once, and a claim is supported if ANY
  of the beat's panels supports it. Skipping panels, compressing a sequence into one
  sentence, or stating an outcome the panel run adds up to is how a recap works and is
  NEVER a finding.

A recap summarizes; it is not a caption. When in doubt, the claim is supported.

Narration:
{narration}

Return JSON: {{"unsupported": ["short description of each unsupported claim"], "severity": "none|minor|major"}}"""


# Words that make a description about a character's CURRENT STATE rather than their
# identity. A recap spans scenes: masks come off, coats become hospital gowns, hair is
# cut, wounds appear. Generic English apparel/condition vocabulary, no series knowledge.
_MUTABLE_HINTS = (
    "mask", "masked", "unmasked", "coat", "jacket", "suit", "robe", "robes", "gown",
    "pajama", "pyjama", "uniform", "armor", "armour", "hoodie", "shirt", "cape", "hat",
    "cap", "glasses", "bandage", "wounded", "injured", "bleeding", "frozen", "wearing",
    "holding", "carrying", "bald", "balding", "shirtless", "dressed", "outfit", "boots",
)


def _split_marks(profile: Any) -> tuple[list[str], list[str]]:
    """Partition a profile's visual marks into (stable identity, mutable state).

    Written after four of five "major misattributions" in one run turned out to be the
    verifier holding a character to a description that had simply moved on: a president
    called "bald" because a joke in the dialogue said so, and a protagonist described as
    "masked swordsman in a black coat" while he sits in hospital pyjamas a chapter later.
    Correct narration was discarded for both.
    """
    stable: list[str] = []
    mutable: list[str] = []
    candidates = [
        profile.visual.hair,
        profile.visual.build,
        *profile.visual.accessories,
        profile.visual.outfit,
        *profile.descriptors[:3],
    ]
    for mark in candidates:
        text = (mark or "").strip()
        if not text:
            continue
        low = text.lower()
        (mutable if any(h in low for h in _MUTABLE_HINTS) else stable).append(text)
    return list(dict.fromkeys(stable)), list(dict.fromkeys(mutable))


def _cast_visuals(bible: SeriesBible | None) -> str:
    """Visual descriptions the verifier needs to judge a naming claim. Without these it
    cannot distinguish 'wrong person' from 'panels don't caption names', and flags every
    named character as unsupported.

    Marks are presented in two groups because they carry different authority: STABLE
    marks can contradict an identity claim, CURRENT-STATE marks cannot.
    """
    if bible is None:
        return "(unavailable — do not flag any naming claim)"
    lines: list[str] = []
    for profile in bible.characters.values():
        if profile.merged_into:
            continue
        stable, mutable = _split_marks(profile)
        if not stable and not mutable:
            continue
        tag = " [PROTAGONIST]" if profile.id == bible.protagonist_id else ""
        parts = []
        if stable:
            parts.append(f"STABLE: {'; '.join(stable)}")
        if mutable:
            parts.append(f"CURRENT-STATE (may differ scene to scene): {'; '.join(mutable)}")
        lines.append(f"- {profile.canonical_name}{tag}: {' | '.join(parts)}")
    return "\n".join(lines) or "(no visual descriptions on file — do not flag any naming claim)"


def audit_frame_alignment(
    beats: list[ScriptBeat],
    panels: dict[str, Panel],
    project_root: Path,
    config: dict[str, Any],
    bible: SeriesBible | None = None,
) -> tuple[QAReport, dict[int, list[str]]]:
    """Returns (report, {beat_id: unsupported claims}) for beats judged 'major'."""
    report = QAReport(stage="alignment")
    cast = _cast_visuals(bible)
    max_beats = int(get_nested(config, "script", "verify_max_beats", default=24))
    # Striding means some beats are never audited at all; downstream gates divide by the
    # AUDITED count, not len(beats), or the fallback fraction is computed against a
    # denominator that was never checked.
    sample = beats if len(beats) <= max_beats else beats[:: max(1, len(beats) // max_beats)][:max_beats]

    llm = apply_stage_model(get_stage_llm("scene", config), "scene", config)

    major: dict[int, list[str]] = {}
    minor_count = 0
    checked = 0
    with Progress() as progress:
        task = progress.add_task("Frame-alignment audit", total=len(sample))
        for beat in sample:
            # EVERY panel the narration covers, not a prefix. Judging a 5-panel beat
            # against its first 3 images makes the verifier flag whatever the narration
            # drew from panels 4-5 ("no aerial view of Seoul" — Seoul was on panel 4),
            # and those false majors survive the rewrite and force the grounded fallback.
            image_paths = [
                project_root / panels[pid].image_path
                for pid in beat.panel_ids[:_MAX_AUDIT_PANELS]
                if pid in panels
            ]
            image_paths = [p for p in image_paths if p.exists()]
            progress.advance(task)
            if not image_paths:
                continue
            checked += 1
            try:
                raw = llm.describe_panels(
                    image_paths, _VERIFY_PROMPT.format(narration=beat.narration, cast=cast)
                )
                data = json.loads(raw)
            except Exception as exc:
                console.print(f"[yellow]Alignment audit skipped beat {beat.beat_id}:[/] {type(exc).__name__}")
                continue
            unsupported = [str(u) for u in data.get("unsupported", []) if str(u).strip()]
            severity = str(data.get("severity", "none")).lower()
            if severity == "major" and unsupported:
                major[beat.beat_id] = unsupported
            elif unsupported:
                minor_count += 1

    report.add(
        "beats-checked",
        checked > 0 if beats else True,
        f"{checked}/{len(beats)} beats audited" if checked < len(beats) else "",
        checked=checked, total=len(beats),
    )
    report.add(
        "no-major-misattribution",
        "warn" if major else True,
        f"{len(major)} beat(s) with major unsupported claims: {sorted(major)}" if major else "",
        major={str(k): v for k, v in major.items()},
    )
    report.add(
        "minor-unsupported",
        "warn" if minor_count else True,
        f"{minor_count} beat(s) with minor unsupported claims" if minor_count else "",
        count=minor_count,
    )
    return report, major
