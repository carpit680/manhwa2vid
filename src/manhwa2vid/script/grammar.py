"""LanguageTool grammar pass — the deterministic net under all the targeted repairs.

The targeted lint/polish functions each encode ONE observed defect class; grammar is an
open class, so a general net is worth having. Measured honestly against the four defect
sentences that actually shipped: LanguageTool (picky mode) catches ONE class
(subject-verb agreement, "He tell her") and misses the other three ("containing he",
the welded appositive, a subject-less sentence) — rule matching cannot parse those, and
the targeted deterministic repairs in lint.py are what catch them. Keep expectations
calibrated: LT is the net under NEW error classes, not a substitute for the repairs.
LanguageTool is rule-based — same input, same findings — open source (LGPL), and runs
as a LOCAL offline server via
`language_tool_python` (optional extra: pip install -e ".[grammar]"; needs a Java
runtime; first use downloads the LT server once, then fully offline).

Conservatism rules the integration:
  - only `issueType == "grammar"` findings count — style/redundancy/typography categories
    are noise against fiction narration and are ignored wholesale;
  - a finding auto-applies ONLY when LanguageTool proposes exactly one replacement
    (the "containing he" -> "him" class): deterministic, single-candidate, in-place;
  - everything else becomes a humanized `grammar:` issue for the existing rewrite loop;
  - unavailable tool (no package, no Java) skips with a console note, never fails a run.
"""

from __future__ import annotations

import shutil
from typing import Any, Protocol

from rich.console import Console

from manhwa2vid.models import ScriptBeat

console = Console()


class _Match(Protocol):
    message: str
    offset: int
    replacements: list[str]


def _attr(m: Any, snake: str, camel: str, default: Any = None) -> Any:
    """language_tool_python renamed its Match attributes to snake_case between
    versions; read either spelling so a wrapper upgrade cannot silently turn the
    whole pass into a no-op (which is exactly what the camelCase-only first draft
    did — getattr defaults ate every finding)."""
    for name in (snake, camel):
        try:
            v = getattr(m, name)
        except AttributeError:
            continue
        if v is not None:
            return v
    return default


class GrammarTool(Protocol):
    def check(self, text: str) -> list[_Match]: ...


def make_language_tool() -> GrammarTool | None:
    """The real LanguageTool, or None when the environment can't run it."""
    if shutil.which("java") is None:
        console.print("[dim]Grammar pass skipped — no Java runtime[/]")
        return None
    try:
        import language_tool_python
    except ImportError:
        console.print(
            "[dim]Grammar pass skipped — install with: pip install -e '.[grammar]'[/]"
        )
        return None
    try:
        tool = language_tool_python.LanguageTool("en-US")
        # Picky mode enables additional rules; our register (present-tense fiction) is
        # unaffected because only issueType==grammar findings are consumed anyway.
        try:
            tool.picky = True
        except Exception:
            pass
        return tool
    except Exception as exc:
        console.print(f"[yellow]Grammar pass unavailable ({type(exc).__name__})[/]")
        return None


def grammar_pass(
    beats: list[ScriptBeat],
    tool: GrammarTool | None,
) -> tuple[list[ScriptBeat], dict[int, list[str]]]:
    """Auto-apply single-replacement grammar fixes; report the rest per beat.

    Returns (possibly-updated beats, {beat_id: ["grammar:<message> @ '<context>'"]}).
    """
    if tool is None:
        return beats, {}
    out: list[ScriptBeat] = []
    issues: dict[int, list[str]] = {}
    for beat in beats:
        text = beat.narration
        try:
            matches = tool.check(text)
        except Exception as exc:
            console.print(f"[yellow]Grammar check failed on beat {beat.beat_id} ({type(exc).__name__})[/]")
            out.append(beat)
            continue
        # Apply from the END so earlier offsets stay valid.
        deferred: list[str] = []
        for m in sorted(matches, key=lambda m: -m.offset):
            if _attr(m, "rule_issue_type", "ruleIssueType", "") != "grammar":
                continue
            length = int(_attr(m, "error_length", "errorLength", 0))
            span = text[m.offset : m.offset + length]
            reps = list(_attr(m, "replacements", "replacements", []) or [])
            if len(reps) == 1 and reps[0] and reps[0] != span and length > 0:
                text = text[: m.offset] + reps[0] + text[m.offset + length :]
            else:
                context = text[max(0, m.offset - 25) : m.offset + length + 25]
                deferred.append(f"grammar:{m.message} @ '…{context}…'")
        if deferred:
            issues[beat.beat_id] = deferred
        out.append(beat.model_copy(update={"narration": text}) if text != beat.narration else beat)
    return out, issues
