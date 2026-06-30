"""Review checkpoint helpers."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from manhwa2vid.characters.bible import load_series_bible, save_series_bible
from manhwa2vid.models import CheckpointState, ProjectMeta, load_json, save_json


def open_for_review(path: Path) -> None:
    editor = os.environ.get("EDITOR", "nano")
    subprocess.run([editor, str(path)], check=False)


def _chapter_summary_from_script(paths: dict[str, Path], meta: ProjectMeta) -> str:
    script_path = paths["script_final"] if paths["script_final"].exists() else paths["script_draft"]
    if not script_path.exists():
        return ""
    text = script_path.read_text(encoding="utf-8")
    hook_match = re.search(r"\*\*Hook:\*\*\s*(.+)", text)
    hook = hook_match.group(1).strip() if hook_match else ""
    beat_lines = []
    for line in text.splitlines():
        if line.startswith("### Beat"):
            continue
        if line.startswith("<!--") or line.startswith("#") or line.startswith("**") or line == "---":
            continue
        stripped = line.strip()
        if stripped:
            beat_lines.append(stripped)
    body = " ".join(beat_lines[:6])[:500]
    if hook and body:
        return f"{hook} {body}"
    return hook or body[:500]


def approve_script(paths: dict[str, Path], checkpoint: CheckpointState) -> None:
    draft = paths["script_draft"]
    final = paths["script_final"]
    if not draft.exists():
        raise FileNotFoundError(f"Missing draft script: {draft}")
    shutil.copy2(draft, final)
    checkpoint.script_approved = True
    save_json(paths["checkpoint"], checkpoint)

    meta = load_json(paths["meta"], ProjectMeta)
    bible = load_series_bible(meta.series_slug, meta.title)
    chapter_key = meta.chapters.split("-")[0].strip()
    summary = _chapter_summary_from_script(paths, meta)
    if summary:
        bible.chapter_summaries[chapter_key] = summary
        save_series_bible(bible)


def approve_preview(checkpoint: CheckpointState, paths: dict[str, Path]) -> None:
    preview = paths["output"] / "preview.mp4"
    if not preview.exists():
        raise FileNotFoundError(f"Missing preview: {preview}")
    checkpoint.preview_approved = True
    save_json(paths["checkpoint"], checkpoint)
