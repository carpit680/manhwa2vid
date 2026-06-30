"""Scout chapter range tests."""

from __future__ import annotations

from manhwa2vid.characters.scout import _lookahead_range


def test_lookahead_range_from_chapter_1() -> None:
    assert _lookahead_range("1", 3) == "2-4"


def test_lookahead_range_from_range() -> None:
    assert _lookahead_range("1-2", 2) == "3-4"
