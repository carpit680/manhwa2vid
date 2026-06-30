"""Cast linking tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manhwa2vid.characters.link import _heuristic_descriptor_merge
from manhwa2vid.models import CharacterProfile, CharacterRef, CharacterTier, SceneCard, SeriesBible


def test_heuristic_descriptor_merge_links_repeated_descriptor() -> None:
    bible = SeriesBible(
        series_slug="solo-leveling",
        title="Solo Leveling",
        characters={
            "char_sung_jinwoo": CharacterProfile(
                id="char_sung_jinwoo",
                canonical_name="Sung Jin-Woo",
                tier=CharacterTier.MAIN,
            )
        },
    )
    cards = [
        SceneCard(
            panel_ids=["p001_01"],
            people=[
                CharacterRef(
                    ref="char_sung_jinwoo",
                    name_used="Sung Jin-Woo",
                    descriptor="guy in green backpack",
                )
            ],
            action="Sung Jin-Woo walks away.",
        ),
        SceneCard(
            panel_ids=["p001_02"],
            people=[
                CharacterRef(
                    ref="new",
                    descriptor="guy in green backpack",
                    visibility="back_turned",
                )
            ],
            action="Someone with a green backpack turns a corner.",
        ),
    ]
    merges = _heuristic_descriptor_merge(cards, bible)
    assert merges["person in green backpack"] == "char_sung_jinwoo"


def test_run_cast_linking_writes_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from manhwa2vid.models import ProjectMeta, SourceLanguage, project_paths, save_json
    from manhwa2vid.characters.link import run_cast_linking
    from manhwa2vid.config import load_config

    project_dir = tmp_path / "test-ch1"
    paths = project_paths(project_dir)
    paths["root"].mkdir(parents=True)
    meta = ProjectMeta(
        slug="test-ch1",
        title="Test",
        chapters="1",
        source_lang=SourceLanguage.EN,
        series_slug="test",
    )
    save_json(paths["meta"], meta)
    save_json(
        paths["scene_json"],
        [
            SceneCard(
                panel_ids=["p001_01"],
                speakers=["Hero"],
                action="Hero stands ready.",
                people=[CharacterRef(ref="new", name_used="Hero")],
            )
        ],
    )
    config = load_config()
    run_cast_linking(meta, paths, config, force=True)
    assert paths["cast_attribution_json"].exists()
    assert paths["scene_enriched_json"].exists()
    attribution = json.loads(paths["cast_attribution_json"].read_text())
    assert attribution[0]["panel_id"] == "p001_01"
