"""The closing ask, written INTO the narration rather than stapled on after it.

A static "subscribe" card is a wall the viewer hits; the reference channel instead keeps
talking. The last thing said about the story flows straight into the ask, in the same
voice and the same breath, so the viewer is still listening when it arrives — the ask
rides the cliffhanger's momentum instead of interrupting it.

This runs on the finished narration text, after the audit, so the outro sees the exact
final sentence it has to continue from. It is deliberately NOT panel-grounded: it is the
narrator speaking to the viewer, so `align_script` treats it as the closing paragraph
over the last panels and the end card.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.models import ProjectMeta
from manhwa2vid.script.sentences import split_sentences

console = Console()

_SYSTEM = """You write the final two sentences of a manhwa recap video's narration.

You are given the recap's LAST PARAGRAPH. Write a closing that CONTINUES it — same
narrator, same tense, same register, no greeting, no "hey guys", no restating the plot.

The closing does two things in one breath:
1. names what the viewer is now waiting to find out (the hook the chapter just set up),
2. folds in the ask as the natural way to not miss the answer.

Rules:
- EXACTLY two sentences. No more.
- The ask is an IMPERATIVE the narrator says to the viewer: "Subscribe and turn
  notifications on". Use the word "subscribe" as a command. Never "subscribing".
- NEVER make an -ing phrase the subject of a sentence. "Subscribing and turning on
  notifications ensures you will be there" and "Determining whether he survives is the
  question" are both wrong — they are the shape this prompt keeps producing and they
  read like a form letter. Say "Subscribe and turn notifications on" and "Whether he
  survives is the question".
- Do not begin with "And", "So", "But", "Well", "Now", or "If".
- Do not use the words "guys", "video", "channel", "episode", "recap", "watching",
  "comment", "like and subscribe" as a fixed phrase, or "in today's".
- Never invent story facts. Refer only to what the last paragraph already established.
- The ask must read as the narrator's own aside to the viewer, not an announcement.
- Present tense, second person for the ask ("you"), never first person plural marketing
  ("we'll be back").

Return the two sentences as plain text. Nothing else."""


#: The nominalised hook, which the model produced on BOTH titles: an -ing form as the
#: subject of the sentence ("Determining whether he can raise his stats is now the only
#: question that matters"). It is grammatical, passes every other shape check, and reads
#: like a form letter — and it is the last thing the viewer hears in every video, so a
#: defect here ships on every run. CLAUDE.md's rule applies: a rule the model declined
#: twice belongs in code, not in the prompt.
_NOMINALISED_RE = re.compile(
    r"(?:^|[.!?]\s+)\w+ing\b\s+(?:whether|if|how|what|why|when)\b", re.I
)


def _fallback(meta: ProjectMeta) -> str:
    """Deterministic outro when no LLM is available — still voice-continuous."""
    return (
        f"Where {meta.title} goes from here is the part worth waiting for. "
        "Subscribe and switch notifications on, and the next chapter reaches you the "
        "moment it lands."
    )


def append_outro(
    text: str,
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
) -> str:
    """Return `text` with a voice-continuous closing paragraph appended."""
    if not bool(get_nested(config, "script", "outro_cta", default=True)):
        return text

    body = (text or "").rstrip()
    if not body:
        return text
    last_para = body.split("\n\n")[-1].strip()

    # Idempotent: the script stage can run against a CACHED script.freeform.md that
    # already ends in an outro (write_freeform_script returns the cached prose unless
    # forced), and appending a second ask is a defect that only surfaces in the finished
    # audio. The guard belongs here, not in whatever script happens to call this.
    if "subscri" in last_para.lower():
        return text

    outro = ""
    try:
        from manhwa2vid.llm.provider import get_llm_provider

        provider = get_llm_provider(get_nested(config, "script", "provider", default=None), config)
        outro = (
            provider.complete(
                _SYSTEM,
                f"SERIES: {meta.title}\n\nLAST PARAGRAPH:\n{last_para}\n\n"
                "Write the closing two sentences.",
            )
            or ""
        ).strip()
    except Exception as exc:  # noqa: BLE001 — an outro is never worth failing a run over
        console.print(f"[yellow]Outro generation failed ({exc}) — using the fixed closing[/]")

    # Absolute checks, not preferences: the model gets two sentences and no plot claims.
    sentences = split_sentences(outro)
    banned = ("guys", "this video", "the channel", "like and subscribe", "in today's")
    # 60, not 45: a genuine two-sentence outro measured 40 (FP) and 44 (SL) words, so a
    # 45 cap rejected a perfectly good closing and shipped the canned one instead. The
    # shape checks that matter — sentence count, marketing vocabulary, the ask being
    # present — are unchanged; only the length threshold moved.
    if (
        not 1 <= len(sentences) <= 2
        or len(outro.split()) > 60
        or any(b in outro.lower() for b in banned)
        # The IMPERATIVE, not merely the topic. A "subscri" substring test accepts
        # "subscribing ... ensures you will be right there", which is what shipped on
        # both titles: the prompt handed the model the ask as a gerund phrase and it
        # used that phrase as written, as a sentence subject. See _NOMINALISED_RE.
        or not re.search(r"\bsubscribe\b", outro, re.I)
        or _NOMINALISED_RE.search(outro)
    ):
        if outro:
            console.print("[yellow]Outro rejected by the shape check — using the fixed closing[/]")
        outro = _fallback(meta)

    return f"{body}\n\n{outro.strip()}\n"
