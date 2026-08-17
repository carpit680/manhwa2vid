"""Beat-by-beat storyboard: the review artifact whose absence let panel/narration
misalignment ship. One scroll shows every beat's narration next to thumbnails of the exact
panels it will play over — id drift, blank slivers, and excluded panels are all visible
before a second of TTS is spent."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path

from manhwa2vid.models import ScriptDraft
from manhwa2vid.panels.filter import load_story_panels

_STYLE = """
body{font-family:system-ui,sans-serif;background:#14161a;color:#e8e8e8;margin:0;padding:24px}
h1{font-size:1.2rem}  .beat{border:1px solid #333;border-radius:8px;margin:16px 0;padding:12px 16px}
.beat h2{font-size:0.95rem;margin:0 0 6px;color:#7fc4e8}
.narration{margin:0 0 10px;max-width:70ch;line-height:1.5}
.strip{display:flex;gap:8px;overflow-x:auto;padding-bottom:6px}
.cell{flex:0 0 auto;text-align:center}
.cell img{height:220px;width:auto;display:block;border-radius:4px;background:#000}
.cell .pid{font-family:monospace;font-size:0.7rem;color:#9aa;margin-top:3px}
.cell.missing{border:2px dashed #c33;border-radius:6px;padding:6px;color:#e88}
.cell.missing .box{height:220px;width:120px;display:flex;align-items:center;justify-content:center;font-size:0.7rem}
"""


def write_storyboard(paths: dict[str, Path], draft: ScriptDraft) -> Path:
    debug_dir = paths["debug"]
    debug_dir.mkdir(parents=True, exist_ok=True)
    out = debug_dir / "storyboard.html"

    panel_map = {p.id: p for p in load_story_panels(paths)}
    excluded: dict[str, str] = {}
    if paths["excluded_panels_json"].exists():
        excluded = json.loads(paths["excluded_panels_json"].read_text(encoding="utf-8"))

    parts: list[str] = [
        f"<title>Storyboard — {html.escape(draft.title)} ch.{html.escape(draft.chapters)}</title>",
        f"<style>{_STYLE}</style>",
        f"<h1>Storyboard — {html.escape(draft.title)} — Chapters {html.escape(draft.chapters)} "
        f"({len(draft.beats)} beats)</h1>",
        f"<p class='narration'><strong>Hook:</strong> {html.escape(draft.hook)}</p>",
    ]

    for beat in draft.beats:
        parts.append("<div class='beat'>")
        parts.append(
            f"<h2>Beat {beat.beat_id} — {len(beat.panel_ids)} panel(s) — "
            f"{len(beat.narration.split())} words</h2>"
        )
        parts.append(f"<p class='narration'>{html.escape(beat.narration)}</p>")
        parts.append("<div class='strip'>")
        for pid in beat.panel_ids:
            panel = panel_map.get(pid)
            if panel is None:
                why = excluded.get(pid, "missing from story inventory")
                parts.append(
                    f"<div class='cell missing'><div class='box'>{html.escape(why)}</div>"
                    f"<div class='pid'>{html.escape(pid)}</div></div>"
                )
                continue
            src = os.path.relpath(paths["root"] / panel.image_path, debug_dir)
            parts.append(
                f"<div class='cell'><img src='{html.escape(src)}' loading='lazy' "
                f"alt='{html.escape(pid)}'><div class='pid'>{html.escape(pid)}</div></div>"
            )
        parts.append("</div></div>")

    out.write_text("\n".join(parts), encoding="utf-8")
    return out
