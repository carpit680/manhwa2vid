"""Title conventions, from the two packaging findings that survived a within-channel test.

Most of the "packaging formula" did not survive. Reversal clauses measured 0.76-1.37x
with four of five channels BELOW 1.0, and CAPS density was equally directionless — so
neither is enforced. What survived is categorical rather than correlational, which is
why it is trustworthy: across 864 videos on six channels, no title names its source
series, and every channel's median title length is exactly 70 characters (where YouTube
truncates). See reports/field_measurement_2026-08-29.md.
"""

from __future__ import annotations

from manhwa2vid.export.youtube import TITLE_MAX_CHARS, title_problems

SERIES = "Return of the Frozen Player"


class TestTitleLength:
    def test_at_the_limit_is_fine(self):
        assert title_problems("A" * TITLE_MAX_CHARS, SERIES) == []

    def test_over_the_limit_is_flagged(self):
        assert any("truncation" in p for p in title_problems("A" * 80, SERIES))


class TestSeriesNaming:
    def test_the_current_shipped_format_is_flagged(self):
        """What write_metadata used to emit, and what no competitor does."""
        bad = f"{SERIES} Chapters 1-2 | Manhwa Recap"
        assert any("names the source series" in p for p in title_problems(bad, SERIES))

    def test_a_descriptive_title_sharing_one_word_is_not_flagged(self):
        """"He Was Frozen For 25 Years" contains "Frozen", which is also in the series
        name — but it is describing the story, which is exactly what field titles do.
        Single-word matching flagged this; only a contiguous run means the NAME."""
        ok = "He Was Frozen For 25 Years And Came Back To Clear The Tower"
        assert title_problems(ok, SERIES) == []

    def test_a_partial_series_name_is_still_the_name(self):
        assert any(
            "names the source series" in p
            for p in title_problems("The Frozen Player Returns After 25 Years", SERIES)
        )

    def test_a_short_series_word_pair_does_not_false_positive(self):
        """Runs shorter than 7 letters are too common to be evidence of a name."""
        assert title_problems("He Is The One Who Waited", "The One") == []


def test_metadata_carries_the_source_name_out_of_the_title(tmp_path):
    """The name is not suppressed — it moves to the pinned comment, which is where the
    field puts it and is a deliberate engagement mechanic."""
    import yaml

    from manhwa2vid.export.youtube import write_metadata
    from manhwa2vid.models import ProjectMeta, Timeline

    meta = ProjectMeta(slug="fp", title=SERIES, chapters="1-2", source_lang="ko")
    out = tmp_path / "metadata.yaml"
    write_metadata(meta, Timeline(entries=[], total_duration=0.0), out)
    d = yaml.safe_load(out.read_text())

    assert SERIES in d["pinned_comment"]
    assert SERIES not in d["title"]
    assert "#" not in d["description"], "hashtags: none of the large channels use them"
