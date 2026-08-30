"""Series memory: what survives from one chapter range to the next, and what must not.

A channel does not restart at chapter 21. Two things outlive a project — identity and
what the viewer already watched — and nothing else. Panels, timings and QA reports are
properties of one range.

The identity half matters most. The glossary is this architecture's entire identity
system, and it was per-project: chapters 21-40 re-derived every name from scratch, so a
human's one-line repair had to be re-made for every part, and nothing stopped part two
from calling a character something new.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manhwa2vid.script import series


@pytest.fixture(autouse=True)
def _isolated_repo(tmp_path, monkeypatch):
    """Series state lives outside the project dir, so the real projects/ tree must
    never be touched by a test run."""
    monkeypatch.setattr(series, "find_repo_root", lambda: tmp_path)
    return tmp_path


def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestRange:
    @pytest.mark.parametrize(
        "text,expected",
        [("1-2", (1, 2)), ("21-40", (21, 40)), ("7", (7, 7)), (" 3 - 9 ", (3, 9))],
    )
    def test_parses(self, text, expected):
        assert series.parse_range(text) == expected

    def test_junk_does_not_raise(self):
        """A malformed range must not take down a run mid-pipeline."""
        assert series.parse_range("chapters one to five") == (0, 0)
        assert series.parse_range("") == (0, 0)


class TestGlossaryCarriesForward:
    def test_a_later_part_starts_from_the_known_cast(self, tmp_path):
        _write(tmp_path / "projects/fp/series/glossary.json",
               {"characters": {"Seo Jun-Ho": ["Specter"]}, "terms": {"Nest": []},
                "protagonist": "Seo Jun-Ho"})
        proj = tmp_path / "p2/glossary.json"
        assert series.seed_project_glossary("fp", proj) == 2
        got = json.loads(proj.read_text())
        assert got["characters"]["Seo Jun-Ho"] == ["Specter"]
        assert got["protagonist"] == "Seo Jun-Ho"

    def test_a_human_edit_in_the_project_wins_over_the_series(self, tmp_path):
        """The project glossary is the repair surface; seeding must not overwrite it."""
        _write(tmp_path / "projects/fp/series/glossary.json",
               {"characters": {"Shim": ["wrong alias"]}})
        proj = _write(tmp_path / "p2/glossary.json",
                      {"characters": {"Shim": ["hand-fixed"]}})
        series.seed_project_glossary("fp", proj)
        assert json.loads(proj.read_text())["characters"]["Shim"] == ["hand-fixed"]

    def test_first_part_seeds_nothing_and_does_not_create_a_file(self, tmp_path):
        proj = tmp_path / "p1/glossary.json"
        assert series.seed_project_glossary("brand-new", proj) == 0
        assert not proj.exists()

    def test_promotion_is_additive_never_destructive(self, tmp_path):
        _write(tmp_path / "projects/fp/series/glossary.json",
               {"characters": {"Seo Jun-Ho": ["Specter", "hand-written"]}})
        proj = _write(tmp_path / "p2/glossary.json",
                      {"characters": {"Seo Jun-Ho": ["Jun-Ho"], "Khali": []}})
        series.promote_to_series("fp", proj)
        chars = series.load_series_glossary("fp")["characters"]
        assert "hand-written" in chars["Seo Jun-Ho"], "a human alias was destroyed"
        assert "Jun-Ho" in chars["Seo Jun-Ho"], "a new alias was not learned"
        assert "Khali" in chars, "a new character was not learned"

    def test_a_round_trip_is_stable(self, tmp_path):
        """seed -> promote -> seed must not grow or mutate the cast."""
        _write(tmp_path / "projects/fp/series/glossary.json",
               {"characters": {"A": ["a1"]}, "terms": {}})
        proj = tmp_path / "p2/glossary.json"
        series.seed_project_glossary("fp", proj)
        series.promote_to_series("fp", proj)
        before = series.load_series_glossary("fp")
        series.seed_project_glossary("fp", proj)
        series.promote_to_series("fp", proj)
        assert series.load_series_glossary("fp") == before


class TestStorySoFar:
    def test_first_part_gets_no_continuation_block(self):
        assert series.story_so_far_prompt("fp", "1-2") == ""

    def test_a_later_part_is_told_what_the_viewer_watched(self):
        series.record_part("fp", "1-2", "He is frozen for 25 years.")
        block = series.story_so_far_prompt("fp", "3-4")
        assert "Chapters 1-2" in block and "frozen for 25 years" in block
        assert "re-introduce" in block.lower()

    def test_a_part_is_never_given_its_own_summary(self):
        """Strictly-before. Re-running a range must not tell the writer the chapters it
        is about to write have already been seen."""
        series.record_part("fp", "1-2", "Part one happened.")
        assert series.story_so_far_prompt("fp", "1-2") == ""

    def test_a_future_part_is_not_leaked_backwards(self):
        series.record_part("fp", "5-6", "Later events.")
        assert series.story_so_far_prompt("fp", "3-4") == ""

    def test_re_running_a_range_replaces_rather_than_duplicates(self):
        series.record_part("fp", "1-2", "first attempt")
        series.record_part("fp", "1-2", "second attempt")
        parts = series.load_parts("fp")
        assert len(parts) == 1 and parts[0]["summary"] == "second attempt"

    def test_parts_arrive_in_chapter_order(self):
        series.record_part("fp", "5-6", "third")
        series.record_part("fp", "1-2", "first")
        series.record_part("fp", "3-4", "second")
        block = series.story_so_far_prompt("fp", "7-8")
        assert block.index("first") < block.index("second") < block.index("third")


class TestSummary:
    def test_it_is_the_beats_topic_sentences(self):
        text = "He draws his blade. Then he waits.\n\nShe answers him. At length."
        assert series.summarise_narration(text) == "He draws his blade. She answers him."

    def test_the_outro_is_not_an_event(self):
        text = "He draws his blade.\n\nSubscribe and turn on notifications for more."
        assert "ubscribe" not in series.summarise_narration(text)

    def test_markdown_scaffolding_never_reaches_a_summary(self):
        """Callers pass clean prose, but a draft file carries headings and panel-id
        comments — and this text is fed to the next part's writer."""
        text = "# Title\n\n<!-- panels: p0001_01 -->\n\nHe draws his blade."
        assert series.summarise_narration(text) == "He draws his blade."

    def test_it_is_bounded(self):
        text = "\n\n".join(f"Sentence number {i} happens here now." for i in range(200))
        assert len(series.summarise_narration(text, max_words=60).split()) <= 60
