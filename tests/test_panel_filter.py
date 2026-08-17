"""Panel filtering tests."""

from __future__ import annotations

from manhwa2vid.models import Panel, PanelBBox, SceneCard
from manhwa2vid.panels.filter import build_exclusion_map, exclude_by_filename, exclude_by_scene_content


def _panel(panel_id: str, page_num: int) -> Panel:
    return Panel(
        id=panel_id,
        page_num=page_num,
        bbox=PanelBBox(x=0, y=0, width=100, height=100),
        image_path=f"panels/{panel_id}.png",
    )


def test_exclude_by_filename() -> None:
    assert exclude_by_filename("/path/thanksmeraki.jpg") == "filename match: thanksmeraki.jpg"
    assert exclude_by_filename("/path/012.png") is None


def test_exclude_credit_scene_card() -> None:
    card = SceneCard(
        panel_ids=["p0028_01"],
        action="None",
        key_terms=["Meraki Scans", "website", "discord"],
        panel_type="credit",
    )
    assert exclude_by_scene_content(card) == "credit panel"


def test_exclude_title_splash() -> None:
    card = SceneCard(
        panel_ids=["p0003_01"],
        action="Large Korean chapter title",
        panel_type="title_splash",
    )
    assert "title" in (exclude_by_scene_content(card) or "").lower()


def test_keep_story_scene_card() -> None:
    card = SceneCard(
        panel_ids=["p0002_01"],
        action="Jin-Woo introduces himself as an E-Rank hunter.",
        dialogue_summary="Introduction scene.",
        key_terms=["Jin-Woo", "E-Rank"],
    )
    assert exclude_by_scene_content(card) is None


def test_build_exclusion_map_marks_credit_pages() -> None:
    panels = [_panel("p0001_01", 1), _panel("p0028_01", 28), _panel("p0002_01", 2)]
    cards = [
        SceneCard(
            panel_ids=["p0001_01"],
            action="No specific action described in the image",
            key_terms=["Merakiscans", "Discord"],
        ),
        SceneCard(panel_ids=["p0002_01"], action="Story beat", dialogue_summary="Intro"),
        SceneCard(panel_ids=["p0028_01"], action="None", key_terms=["Meraki Scans"]),
    ]
    sources = [
        {"page_num": 28, "source_path": "/chapter/thanksmeraki.jpg"},
    ]
    excluded = build_exclusion_map(panels, cards, sources, {"panels": {}})
    assert "p0028_01" in excluded
    assert "p0001_01" in excluded
    assert "p0002_01" not in excluded


def test_blank_sliver_panel_is_excluded(tmp_path) -> None:
    """Regression: three near-white transition slivers shipped as blank video segments."""
    import numpy as np
    import cv2

    from manhwa2vid.config import load_config
    from manhwa2vid.models import project_paths
    from manhwa2vid.panels.filter import apply_panel_filter

    paths = project_paths(tmp_path)
    (tmp_path / "panels").mkdir(parents=True)
    (tmp_path / "pages").mkdir(parents=True)

    # near-white sliver with a faint line (like a bubble-tail crop)
    sliver = np.full((200, 1080, 3), 252, dtype=np.uint8)
    sliver[100:104, :, :] = 200
    cv2.imwrite(str(tmp_path / "panels" / "p0001_01.png"), sliver)
    # real panel: half the pixels dark
    real = np.full((800, 1080, 3), 250, dtype=np.uint8)
    real[:400, :, :] = 40
    cv2.imwrite(str(tmp_path / "panels" / "p0001_02.png"), real)

    panels = [_panel("p0001_01", 1), _panel("p0001_02", 1)]
    cards = [
        SceneCard(panel_ids=["p0001_01"], action="The sky clears."),  # hallucinated card
        SceneCard(panel_ids=["p0001_02"], action="Jin-Woo walks on."),
    ]
    import json as _json

    (tmp_path / "panels.json").write_text(
        _json.dumps([p.model_dump(mode="json") for p in panels])
    )
    active = apply_panel_filter(paths, panels, cards, load_config())
    excluded = _json.loads((tmp_path / "excluded_panels.json").read_text())
    assert excluded.get("p0001_01") == "blank transition sliver"
    assert [p.id for p in active] == ["p0001_02"]


def test_blank_stats_backfilled_from_image(tmp_path) -> None:
    import numpy as np
    import cv2

    from manhwa2vid.config import load_config
    from manhwa2vid.models import project_paths
    from manhwa2vid.panels.filter import apply_panel_filter

    paths = project_paths(tmp_path)
    (tmp_path / "panels").mkdir(parents=True)
    (tmp_path / "pages").mkdir(parents=True)
    img = np.full((300, 300, 3), 30, dtype=np.uint8)
    cv2.imwrite(str(tmp_path / "panels" / "p0001_01.png"), img)

    panel = _panel("p0001_01", 1)
    assert panel.ink_ratio is None
    import json as _json

    (tmp_path / "panels.json").write_text(_json.dumps([panel.model_dump(mode="json")]))
    apply_panel_filter(paths, [panel], [], load_config())
    assert panel.ink_ratio is not None and panel.ink_ratio > 0.9
    assert panel.dark_ratio is not None and panel.dark_ratio > 0.9
