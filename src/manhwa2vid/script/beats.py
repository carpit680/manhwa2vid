"""The `script.draft.md` round-trip — the human-editable surface of a script.

`script.draft.md` is where a person reviews and edits narration before it is approved,
and `<!-- panels: ... -->` comments carry each beat's panel binding through that edit.
The comment is LOAD-BEARING: an edit that drops it loses the binding and the beat is
rendered over the wrong art, silently.

These three functions outlived the panel-locked script architecture they were written
in; they are the only part of the old `script/generate.py` the story-first path still
needs, so they live here rather than keeping a 2,400-line module alive around them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from manhwa2vid.models import ScriptBeat, ScriptDraft


def _beats_to_markdown(draft: ScriptDraft) -> str:
    lines = [
        f"# {draft.title} — Chapters {draft.chapters}",
        "",
        f"**Hook:** {draft.hook}",
        "",
        "## Beats",
        "",
    ]
    for beat in draft.beats:
        lines.extend(
            [
                f"### Beat {beat.beat_id}",
                (
                    f"<!-- panels: {', '.join(beat.panel_ids)}"
                    + (f" | key: {', '.join(beat.key_panel_ids)}" if beat.key_panel_ids else "")
                    + " -->"
                ),
                "",
                beat.narration,
                "",
            ]
        )
    lines.append("---")
    lines.append("Edit freely. Save approved version as script.final.md")
    return "\n".join(lines)


def _parse_markdown_beats(path: Path) -> list[ScriptBeat]:
    """Parse beats from markdown (for final script after human edit).

    Three failure modes fixed here, all silent and all producing a WRONG VIDEO
    rather than an error:

    - `current_panels` was never reset between beats, so a beat whose
      `<!-- panels: -->` comment was deleted inherited the PREVIOUS beat's panels and
      played someone else's images under its narration.
    - With no comment at all the fallback id was `unknown_N`, which
      `timeline._panel_sort_key` maps to page 9999 — the "nearest" surviving panel is
      then the LAST panel of the chapter, so every comment-less beat played the
      chapter's final image. The comment is load-bearing; a missing one is now an
      error naming the beat.
    - A `---` line anywhere in the body `break`-ed the parse, silently discarding the
      whole rest of the script. Only the trailer's "Edit freely" line terminates now,
      so a horizontal rule inside narration is harmless.
    """
    text = path.read_text(encoding="utf-8")
    beats: list[ScriptBeat] = []
    current_panels: list[str] = []
    current_keys: list[str] = []
    current_lines: list[str] = []
    beat_id = 0
    seen_comment = False

    def _flush() -> None:
        if not (current_lines and beat_id):
            return
        if not seen_comment:
            raise ValueError(
                f"{path.name}: beat {beat_id} has no '<!-- panels: ... -->' comment. "
                "That comment binds the beat to its panels; without it the beat cannot "
                "be rendered. Re-run the script stage rather than hand-restoring it."
            )
        beats.append(
            ScriptBeat(
                beat_id=beat_id,
                panel_ids=list(current_panels),
                narration=" ".join(current_lines).strip(),
                key_panel_ids=[k for k in current_keys if k in current_panels],
            )
        )

    for line in text.splitlines():
        if line.startswith("<!-- panels:"):
            body = line.replace("<!-- panels:", "").replace("-->", "")
            panels_part, _, key_part = body.partition("|")
            current_panels = [p.strip() for p in panels_part.split(",") if p.strip()]
            current_keys = [
                p.strip()
                for p in key_part.replace("key:", "").split(",")
                if p.strip()
            ]
            seen_comment = True
        elif line.startswith("### Beat"):
            _flush()
            beat_id += 1
            current_lines = []
            current_panels = []
            current_keys = []
            seen_comment = False
        elif line.startswith("#") or line.startswith("**Hook:") or line == "---":
            continue
        elif beat_id > 0 and line.strip():
            if line.strip().lower().startswith("edit freely"):
                break
            current_lines.append(line.strip())

    _flush()
    return beats


def load_script_beats(paths: dict[str, Path]) -> ScriptDraft:
    if paths["script_json"].exists():
        data = json.loads(paths["script_json"].read_text())
        return ScriptDraft.model_validate(data)
    final = paths["script_final"] if paths["script_final"].exists() else paths["script_draft"]
    beats = _parse_markdown_beats(final)
    meta = json.loads(paths["meta"].read_text())
    return ScriptDraft(title=meta["title"], chapters=meta["chapters"], beats=beats)
