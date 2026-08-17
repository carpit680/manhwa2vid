"""Storyboard review artifact smoke test."""

from __future__ import annotations

import json
from pathlib import Path

from manhwa2vid.models import Panel, PanelBBox, ScriptBeat, ScriptDraft, project_paths, save_json
from manhwa2vid.review.storyboard import write_storyboard


def test_storyboard_smoke(tmp_path: Path) -> None:
    paths = project_paths(tmp_path)
    (tmp_path / "panels").mkdir(parents=True)
    panels = [
        Panel(id=f"p000{i}_01", page_num=i, bbox=PanelBBox(x=0, y=0, width=10, height=10),
              image_path=f"panels/p000{i}_01.png")
        for i in (1, 2, 3)
    ]
    save_json(paths["panels_json"], panels)
    save_json(paths["excluded_panels_json"], {"p0009_01": "blank transition sliver"})

    draft = ScriptDraft(
        title="T", chapters="1", hook="A hook.",
        beats=[
            ScriptBeat(beat_id=1, panel_ids=["p0001_01", "p0002_01"],
                       narration="He walks into the gate site."),
            ScriptBeat(beat_id=2, panel_ids=["p0003_01", "p0009_01"],
                       narration="The party heads in."),
        ],
    )
    out = write_storyboard(paths, draft)
    assert out.exists()
    html = out.read_text()
    assert "He walks into the gate site." in html
    assert html.count("<img") == 3  # 3 real panels
    assert "p0002_01" in html
    assert "blank transition sliver" in html  # excluded id rendered with its reason
