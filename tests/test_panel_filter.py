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
