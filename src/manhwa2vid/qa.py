"""Stage QA gates and reports.

Every pipeline stage that can silently degrade writes a qa.<stage>.json report and calls
enforce(). A failed gate blocks the run unless the caller passes force_past_qa — the point
is that nothing about the output can drift without a loud, machine-readable record of it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console

console = Console()

PASS = "pass"
WARN = "warn"
FAIL = "fail"


class QAGateFailure(RuntimeError):
    """Raised when a stage's QA gates fail and enforcement is on."""


class GateResult(BaseModel):
    name: str
    status: str  # pass | warn | fail
    details: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


# The stages that write a qa.<stage>.json today. `upstream_failures` gates the render on
# these and IGNORES anything else, because a project directory accumulates reports from
# stages that no longer exist: the classic script path left qa.script.json,
# qa.script-final.json, qa.script-coverage.json and qa.style.json behind, and the retired
# CAST stage left qa.cast.json. Frozen Player's render was blocked for two days by a
# 2026-08-25 qa.script-final.json describing a 31-beat script — the current one has 17.
# Worse than the false alarm: it taught the operator to pass --force-past-qa reflexively,
# which is exactly what the precondition exists to prevent.
# `tests/test_qa_gates.py` AST-scans src/ and fails if a stage writes a name not listed.
CURRENT_QA_STAGES = frozenset(
    {"scene", "align", "script-story-first", "timeline", "render"}
)


class QAReport(BaseModel):
    stage: str
    gates: list[GateResult] = Field(default_factory=list)

    def add(self, name: str, ok: bool | str, details: str = "", **data: Any) -> str:
        """ok may be a bool (pass/fail) or an explicit status string ('warn')."""
        status = ok if isinstance(ok, str) else (PASS if ok else FAIL)
        self.gates.append(GateResult(name=name, status=status, details=details, data=data))
        return status

    @property
    def failed(self) -> list[GateResult]:
        return [g for g in self.gates if g.status == FAIL]

    @property
    def warned(self) -> list[GateResult]:
        return [g for g in self.gates if g.status == WARN]


def save_report(report: QAReport, project_dir: Path) -> Path:
    path = project_dir / f"qa.{report.stage}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def print_report(report: QAReport) -> None:
    styles = {PASS: "green", WARN: "yellow", FAIL: "red"}
    marks = {PASS: "✓", WARN: "⚠", FAIL: "✗"}
    for gate in report.gates:
        style = styles.get(gate.status, "white")
        line = f"  [{style}]{marks.get(gate.status, '?')} {gate.name}[/]"
        if gate.details and gate.status != PASS:
            line += f" — {gate.details}"
        console.print(line)


def enforce(report: QAReport, project_dir: Path, *, force: bool = False) -> None:
    """Save + print the report; raise on failed gates unless force is set."""
    save_report(report, project_dir)
    console.print(f"[bold]QA {report.stage}:[/] {len(report.gates)} gate(s), "
                  f"{len(report.failed)} failed, {len(report.warned)} warned")
    print_report(report)
    if report.failed and not force:
        names = ", ".join(g.name for g in report.failed)
        raise QAGateFailure(
            f"Stage '{report.stage}' failed QA gates: {names}. "
            f"See qa.{report.stage}.json for details, or re-run with --force-past-qa."
        )
    if report.failed and force:
        console.print(f"[red]QA failures overridden by --force-past-qa[/]")


def qa_forced(config: dict[str, Any]) -> bool:
    """Read the force-past-qa flag threaded through the config dict by the CLI."""
    return bool(config.get("_qa_force"))
