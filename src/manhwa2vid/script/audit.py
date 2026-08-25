"""Check finished narration against the pages, and allow exactly one revision.

The one-shot writer is good but not audit-free: the best script in the 2x2 said
"humanity has only cleared the second floor" where the pages say humanity is *on* the
second floor — a one-word drift that contradicts the next sentence's premise. So a
grounding pass is required. What is NOT permitted is a loop.

Every previous quality push added another rewrite round, and the dominant defect class
of this project became "a later pass undoes an earlier pass's work" — seven-plus
documented instances, including a voice pass that stripped landed system messages and an
alignment audit that reverted 21 of 28 beats. The rule here is therefore structural:

    at most ONE revision, and it is accepted only if it strictly improves.

If the revision does not reduce findings, the ORIGINAL is kept and the residue is
reported to the human. That makes regression impossible by construction rather than by
vigilance, which is the whole reason this architecture exists.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.llm.vision_utils import page_max_width
from manhwa2vid.models import save_json

console = Console()

#: Distinctive words a system message needs before the recap is held to it.
_MIN_SPINE_WORDS = 3

_AUDIT_SYSTEM = """You are fact-checking a finished manhwa recap against the chapter's
actual pages. You do not rewrite anything — you report.

You are given the recap narration and then the pages in reading order.

Return JSON only:
{
  "findings": [
    {"severity": "major", "quote": "the exact sentence from the narration",
     "problem": "what the pages actually show", "page": "0012"}
  ]
}

severity is "major" only when the narration states something the pages contradict, or
attributes an action or line to the wrong character, or gets a number, rank, count or
time reference wrong. Everything else — compression, omission, an interpretive flourish,
a stylistic aside, casual or profane register — is NOT a finding. A recap is allowed to
leave things out, to editorialise, and to be crude; it is not allowed to be wrong.

Do not report a claim as unsupported merely because a detail is small or off-page-centre.
Report only what you can see is WRONG."""

_REVISE_SYSTEM = """You are correcting specific factual errors in a finished recap.

Change ONLY what the findings identify. Preserve every other sentence verbatim —
including voice, asides, casual register, profanity, paragraph breaks and the overall
shape. Do not reorder, do not tighten, do not improve anything you were not asked about.
Do not add new material.

Return the full corrected narration as plain prose paragraphs, nothing else."""


def _undelivered_spine(text: str, facts: dict[str, Any]) -> list[str]:
    """System messages the narration never delivered.

    Compared on content words rather than verbatim: a recap SHOULD paraphrase
    "[YOU HAVE COMPLETELY ABSORBED THE FROST QUEEN'S NUCLEUS.]" rather than read it out,
    so requiring the literal string would flag correct writing. Half the message's
    distinctive words appearing somewhere in the narration is the bar.
    """
    lowered = set(re.findall(r"[a-z']+", (text or "").lower()))
    missing: list[str] = []
    seen: set[str] = set()
    for message in facts.get("system_messages") or []:
        text_of = str(message).strip()
        key = text_of.lower()
        if key in seen:
            # A chapter prints the same message twice; asking for it twice made the
            # reviser paste it in twice.
            continue
        seen.add(key)
        words = [w for w in re.findall(r"[a-z']+", key) if len(w) > 3]
        # Ceremony with no story content is not spine. Requiring it drove the reviser to
        # paste bracketed text verbatim into the prose — which the writer's own brief
        # forbids, and which reads as a screen-reader rather than a narrator.
        #
        # Threshold measured against Frozen Player's 22 real messages, not guessed. At 3
        # distinctive words it drops exactly the ceremony ("[CONGRATULATIONS.]" 1,
        # "[2ND FLOOR]" 1, "[ABSORPTION RATE 100%.]" 2, "[AUTHENTICATION SUCCESSFUL.]" 2)
        # and keeps every plot-bearing one. Note "[INSUFFICIENT MAGIC STATS.]" sits
        # EXACTLY at 3 and is genuine spine — it is the cliffhanger's mechanism — so 3 is
        # the only workable value: 4 would discard the beat this gate most exists for.
        if len(set(words)) < _MIN_SPINE_WORDS:
            continue
        hits = sum(1 for w in set(words) if w in lowered)
        if hits < max(1, len(set(words)) // 2):
            missing.append(text_of)
    return missing


def audit_script(
    text: str,
    paths: dict[str, Path],
    config: dict[str, Any],
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Grounding findings plus undelivered spine items. Pure reporting."""
    from manhwa2vid.llm.provider import get_llm_provider

    pages = sorted(paths["pages"].glob("*.png"))
    provider = get_llm_provider(get_nested(config, "audit", "provider", default=None), config)
    model = get_nested(config, "audit", "model", default=None)
    if model:
        provider.vision_model = model
    provider.temperature = 0.0

    raw = provider.describe_labeled_panels(
        [(f"[page {p.stem}]", p) for p in pages],
        f"{_AUDIT_SYSTEM}\n\nRECAP NARRATION:\n\n{text}",
        max_width=page_max_width(config),
    )
    data = json.loads(raw) if isinstance(raw, str) else raw
    findings = [f for f in (data.get("findings") or []) if isinstance(f, dict)]
    majors = [f for f in findings if str(f.get("severity", "")).lower() == "major"]
    return {
        "findings": findings,
        "majors": majors,
        "undelivered_system_messages": _undelivered_spine(text, facts or {}),
    }


def revise_once(
    text: str,
    audit: dict[str, Any],
    paths: dict[str, Path],
    config: dict[str, Any],
    facts: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """One corrective pass, kept only if it strictly improves. Returns (text, report)."""
    majors = audit.get("majors") or []
    missing = audit.get("undelivered_system_messages") or []
    if not majors and not missing:
        return text, {"revised": False, "reason": "clean", "before": 0, "after": 0}

    issues = [
        f"- WRONG: {f.get('quote', '')!r} — {f.get('problem', '')} (page {f.get('page', '?')})"
        for f in majors
    ]
    issues += [
        f"- MISSING: the narration never conveys what {m!r} SAYS. Work its meaning into "
        "the prose in your own words — do NOT quote the bracketed text."
        for m in missing
    ]

    from manhwa2vid.llm.provider import get_llm_provider

    provider = get_llm_provider(get_nested(config, "audit", "provider", default=None), config)
    model = get_nested(config, "audit", "model", default=None)
    if model:
        provider.vision_model = model
    provider.temperature = 0.0

    pages = sorted(paths["pages"].glob("*.png"))
    revised = provider.describe_labeled_panels_text(
        [(f"[page {p.stem}]", p) for p in pages],
        _REVISE_SYSTEM,
        "FINDINGS TO FIX:\n" + "\n".join(issues) + f"\n\nCURRENT NARRATION:\n\n{text}",
        max_width=page_max_width(config),
    ).strip()

    before = len(majors) + len(missing)
    if not revised:
        return text, {"revised": False, "reason": "empty revision", "before": before, "after": before}

    recheck = audit_script(revised, paths, config, facts)
    after = len(recheck.get("majors") or []) + len(recheck.get("undelivered_system_messages") or [])

    if after >= before:
        # The revision did not improve. Keeping it anyway is how "a later pass undoes an
        # earlier pass's work" became this project's most repeated defect; the original
        # stands and the human is told what is still wrong.
        console.print(
            f"[yellow]Revision rejected[/] — findings {before} → {after}, keeping the original"
        )
        return text, {
            "revised": False,
            "reason": "no improvement",
            "before": before,
            "after": after,
            "residual": majors + [{"missing": m} for m in missing],
        }

    console.print(f"[green]Revision accepted[/] — findings {before} → {after}")
    return revised, {
        "revised": True,
        "before": before,
        "after": after,
        "residual": (recheck.get("majors") or [])
        + [{"missing": m} for m in recheck.get("undelivered_system_messages") or []],
    }


def audit_and_revise(
    text: str,
    paths: dict[str, Path],
    config: dict[str, Any],
    facts: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """The whole accountability step: audit, at most one revision, persist the record."""
    audit = audit_script(text, paths, config, facts)
    console.print(
        f"[cyan]Audit[/] — {len(audit['majors'])} major finding(s), "
        f"{len(audit['undelivered_system_messages'])} undelivered system message(s)"
    )
    final, revision = revise_once(text, audit, paths, config, facts)
    record = {"audit": audit, "revision": revision}
    save_json(paths["script_audit_json"], record)
    return final, record
