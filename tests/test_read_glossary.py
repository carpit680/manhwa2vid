"""The glossary is the whole identity system — and human edits must survive it.

`merge_cast_into_glossary` runs on every script pass and writes back to a file a person
is expected to hand-edit. If it ever overwrites an entry, the one repair surface the
pipeline offers stops working, and the failure is silent: the name simply reverts on the
next run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manhwa2vid.script.read import glossary_names, merge_cast_into_glossary


@pytest.fixture
def paths(tmp_path: Path) -> dict[str, Path]:
    return {"root": tmp_path, "glossary": tmp_path / "glossary.json"}


def _write(paths, data):
    paths["glossary"].write_text(json.dumps(data), encoding="utf-8")


def test_new_names_are_added(paths):
    _write(paths, {"characters": {}, "terms": {}})
    merge_cast_into_glossary([{"name": "Seo Jun-Ho", "aliases": ["Specter"]}], paths)
    out = json.loads(paths["glossary"].read_text())
    assert out["characters"]["Seo Jun-Ho"] == ["Specter"]


def test_a_human_edit_is_never_overwritten(paths):
    """The whole point of the flat glossary: when it is wrong, a person fixes one line
    and it STAYS fixed."""
    _write(paths, {"characters": {"Seo Jun-Ho": ["the Specter", "hand-written alias"]}})
    merge_cast_into_glossary(
        [{"name": "Seo Jun-Ho", "aliases": ["Specter", "the Specter"]}], paths
    )
    aliases = json.loads(paths["glossary"].read_text())["characters"]["Seo Jun-Ho"]
    assert "hand-written alias" in aliases, "a human alias was dropped"
    assert "the Specter" in aliases
    assert "Specter" in aliases, "genuinely new aliases still get added"


def test_aliases_extend_rather_than_replace(paths):
    _write(paths, {"characters": {"Khali": ["A"]}})
    merge_cast_into_glossary([{"name": "Khali", "aliases": ["B"]}], paths)
    assert json.loads(paths["glossary"].read_text())["characters"]["Khali"] == ["A", "B"]


def test_a_name_is_never_its_own_alias(paths):
    _write(paths, {"characters": {"Mio": []}})
    merge_cast_into_glossary([{"name": "Mio", "aliases": ["Mio"]}], paths)
    assert json.loads(paths["glossary"].read_text())["characters"]["Mio"] == []


def test_blank_and_malformed_entries_are_ignored(paths):
    _write(paths, {"characters": {}})
    merge_cast_into_glossary(
        [{"name": "  "}, {"aliases": ["orphan"]}, {"name": "Real", "aliases": [None, "", "ok"]}],
        paths,
    )
    chars = json.loads(paths["glossary"].read_text())["characters"]
    assert list(chars) == ["Real"] and chars["Real"] == ["ok"]


def test_missing_glossary_file_is_created(paths):
    assert not paths["glossary"].exists()
    merge_cast_into_glossary([{"name": "Skaya", "aliases": []}], paths)
    assert json.loads(paths["glossary"].read_text())["characters"] == {"Skaya": []}


def test_glossary_names_feeds_the_identity_gate_names_and_aliases(paths):
    """The name-integrity gate compares narration against exactly this set — an alias
    missing here is reported as an invented name."""
    _write(paths, {
        "characters": {"Seo Jun-Ho": ["Specter"]},
        "terms": {"Carthenon Temple": ["the Temple"]},
        "protagonist": "Seo Jun-Ho",
    })
    names = glossary_names(paths)
    assert {"Seo Jun-Ho", "Specter", "Carthenon Temple", "the Temple"} <= names


def test_glossary_names_on_a_missing_file_is_empty_not_an_error(paths):
    assert glossary_names(paths) == set()
