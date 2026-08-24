"""Defect memory: what has already gone wrong telling THIS series.

The character bible is long-term memory for who is in the story and survives across every
chapter of a title. There has been no equivalent for what goes wrong in the telling, so
the pipeline re-makes the same mistake on every run — the world-history exposition beat
("Global leaders and association representatives gather around a glowing conference
table...") was flagged flat by the viewer on three consecutive Frozen Player runs and
came back flat each time.

A lesson is only recorded when a complaint SURVIVED its corrective rounds. A defect that
got fixed is not worth remembering; one that resisted fixing is exactly what a later run
should be warned about.

Deliberately small and hint-shaped. Capped, most-recent-first, and handed to the writer as
"traps on this series" rather than as rules — an unbounded ledger would become another
checklist, and a writer buried in a checklist is what produced report-prose in the first
place. The file is plain JSON so a human can edit or delete anything they disagree with.
"""

from __future__ import annotations

import json
from pathlib import Path

MAX_LESSONS = 15


def load_lessons(paths: dict[str, Path]) -> list[str]:
    """Lesson lines for the prompt, newest first. Never raises."""
    path = paths.get("lessons_json")
    if path is None or not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for entry in data[:MAX_LESSONS]:
        if not isinstance(entry, dict):
            continue
        pattern = str(entry.get("pattern", "")).strip()
        fix = str(entry.get("fix", "")).strip()
        if pattern:
            out.append(f"{pattern}{f' — {fix}' if fix else ''}")
    return out


def record_lessons(paths: dict[str, Path], survivors: list[str]) -> None:
    """Append defects that outlived their rewrites, merging repeats by their text.

    `runs` counts how many separate runs a defect has survived, which is the signal worth
    having: something that resists three runs is structural, not bad luck.
    """
    path = paths.get("lessons_json")
    if path is None or not survivors:
        return
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(existing, list):
            existing = []
    except Exception:
        existing = []

    by_pattern = {
        str(e.get("pattern", "")).strip().lower(): e
        for e in existing
        if isinstance(e, dict) and str(e.get("pattern", "")).strip()
    }
    for text in survivors:
        pattern = " ".join(text.split())[:160]
        key = pattern.lower()
        if key in by_pattern:
            by_pattern[key]["runs"] = int(by_pattern[key].get("runs", 1)) + 1
        else:
            entry = {"pattern": pattern, "fix": "", "runs": 1}
            existing.insert(0, entry)
            by_pattern[key] = entry
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(existing[:MAX_LESSONS], indent=1), encoding="utf-8")
    except Exception:
        pass
