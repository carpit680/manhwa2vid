"""Windowing and allowances for chapter ranges bigger than anything shipped so far.

`read`, `audit` and `align` each used to make ONE vision call carrying every page in
the range. That is fine at 19-60 pages and untested past it — a 20-chapter project has
235. Two things break first at that size: the output JSON grows while the token cap does
not (see tests/test_truncation.py), and the model's attention over the images degrades —
audit.py's own docstring records 5 of 8 findings false at 19-156 pages.

These tests pin the windowing AND, just as importantly, that it changes nothing for the
project sizes already validated.
"""

from __future__ import annotations

import json

import pytest

from manhwa2vid.script.freeform import _page_windows


def test_a_small_range_is_still_exactly_one_call():
    """Every shipped video is 19-158 pages. Windowing must not re-shape those runs —
    a behaviour change there would invalidate the renders already approved."""
    for n in (19, 40, 60):
        assert len(_page_windows([f"p{i}" for i in range(n)], 60)) == 1


def test_a_twenty_chapter_range_is_split():
    assert len(_page_windows([f"p{i}" for i in range(235)], 60)) == 4


def test_windows_are_even_and_cover_every_page():
    """Uneven windows would put a 59-page call beside a 4-page one, and the small one
    would answer with the same allowances as the large."""
    pages = [f"p{i}" for i in range(235)]
    windows = _page_windows(pages, 60)
    assert [p for w in windows for p in w] == pages
    assert max(len(w) for w in windows) - min(len(w) for w in windows) <= 1


class TestFactsMerge:
    """Windows are merged by concatenation, never summarised — the whole point of
    windowing is that no single call has to compress the range."""

    def test_every_windows_facts_survive(self):
        from manhwa2vid.script.read import _merge_facts

        acc = {}
        _merge_facts(acc, {"plot_spine": ["a", "b"], "cast": [{"name": "One"}]})
        _merge_facts(acc, {"plot_spine": ["c"], "cast": [{"name": "Two"}]})
        assert acc["plot_spine"] == ["a", "b", "c"]
        assert [c["name"] for c in acc["cast"]] == ["One", "Two"]

    def test_a_character_seen_in_three_windows_is_one_cast_entry(self):
        from manhwa2vid.script.read import _merge_facts

        acc = {}
        for _ in range(3):
            _merge_facts(acc, {"cast": [{"name": "Recurring"}]})
        assert len(acc["cast"]) == 1

    def test_page_order_is_preserved(self):
        """The spine is explicitly "in the order events occur ON THE PAGE", so windows
        must concatenate in page order, not merge by similarity."""
        from manhwa2vid.script.read import _merge_facts

        acc = {}
        _merge_facts(acc, {"plot_spine": ["first thing"]})
        _merge_facts(acc, {"plot_spine": ["second thing"]})
        assert acc["plot_spine"] == ["first thing", "second thing"]


class TestAllowancesScale:
    """A checklist sized for two chapters is a silent content drop at twenty."""

    def test_the_facts_block_grows_with_the_range(self):
        from manhwa2vid.script.audit import _facts_block

        facts = {
            "plot_spine": [f"turn {i}" for i in range(200)],
            "cast": [{"name": f"C{i}"} for i in range(60)],
            "key_dialogue": [{"speaker": f"C{i}", "line": f"line {i}"} for i in range(60)],
        }
        short, long = _facts_block(facts, 2), _facts_block(facts, 20)
        assert long.count("\n") > short.count("\n")
        assert "C40" in long and "C40" not in short

    def test_the_spine_allowance_in_the_prompt_is_a_placeholder(self):
        """It was hard-coded at 8-25 entries regardless of chapter count."""
        from manhwa2vid.script.read import _SYSTEM

        assert "{spine_lo}" in _SYSTEM and "{spine_hi}" in _SYSTEM
        assert "8-25 entries" not in _SYSTEM

    def test_the_prompt_survives_substitution_despite_its_json_skeleton(self):
        """The prompt shows the model a JSON skeleton; str.format would read every one
        of those braces as a placeholder and raise."""
        from manhwa2vid.script.read import _SYSTEM

        filled = _SYSTEM.replace("{spine_lo}", "16").replace("{spine_hi}", "120")
        assert "16-120" in filled and "{" in filled  # the JSON skeleton is still there
