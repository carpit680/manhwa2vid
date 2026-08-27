"""The script.draft.md round-trip — the human-editable surface of the pipeline.

`<!-- panels: ... -->` is load-bearing: it carries each beat's panel binding through a
human edit. A parse that loses it, silently inherits the previous beat's panels, or
swallows a beat renders narration over the wrong art without failing anything. These
tests are what stops that.

Extracted from the old test_story_script.py when the panel-locked script architecture
was deleted; everything else in that file tested modules that no longer exist.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from manhwa2vid.models import ScriptBeat, ScriptDraft
from manhwa2vid.script.beats import _beats_to_markdown, _parse_markdown_beats
from manhwa2vid.video.timeline import split_beat_durations


def test_split_beat_durations_sum_equals_audio() -> None:
    segs = split_beat_durations(10.0, 4, min_sec=2.5, max_sec=8.0)
    assert len(segs) == 4
    assert abs(sum(segs) - 10.0) < 1e-6
    assert all(abs(s - 2.5) < 1e-6 for s in segs)

    short = split_beat_durations(6.0, 4, min_sec=2.5, max_sec=8.0)
    assert abs(sum(short) - 6.0) < 1e-6


def test_parse_markdown_skips_footer(tmp_path: Path) -> None:
    path = tmp_path / "script.final.md"
    path.write_text(
        "# Title\n\n**Hook:** hi\n\n## Beats\n\n"
        "### Beat 1\n<!-- panels: p0001_01 -->\n\nHello world\n\n"
        "---\nEdit freely. Save approved version as script.final.md\n",
        encoding="utf-8",
    )
    beats = _parse_markdown_beats(path)
    assert len(beats) == 1
    assert "Edit freely" not in beats[0].narration
    assert beats[0].narration == "Hello world"


def test_key_panels_round_trip_through_draft_markdown():
    """The `| key:` extension of the load-bearing panels comment must survive the
    draft -> final -> beats round trip, and stray ids must not import."""
    from manhwa2vid.models import ScriptBeat, ScriptDraft
    from manhwa2vid.script.beats import _beats_to_markdown, _parse_markdown_beats

    draft = ScriptDraft(
        title="T", chapters="1", hook="h",
        beats=[
            ScriptBeat(beat_id=1, panel_ids=["p0001_01", "p0001_02"], narration="First beat.",
                       key_panel_ids=["p0001_02"]),
            ScriptBeat(beat_id=2, panel_ids=["p0002_01"], narration="Second beat."),
        ],
    )
    md = _beats_to_markdown(draft)
    assert "| key: p0001_02" in md

    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "script.final.md"
        f.write_text(md, encoding="utf-8")
        beats = _parse_markdown_beats(f)
    assert beats[0].key_panel_ids == ["p0001_02"]
    assert beats[1].key_panel_ids == []


def test_markdown_beat_without_panel_comment_is_an_error_not_a_silent_wrong_video(tmp_path):
    """A missing panel comment used to produce a wrong video, silently, two ways.

    `current_panels` was never reset between beats, so beat 2 below inherited beat 1's
    panels. With no prior beat to inherit from, the fallback id `unknown_N` maps to page
    9999 in `timeline._panel_sort_key`, making the "nearest" panel the chapter's LAST
    one — so a comment-less beat played the final image of the video.
    """
    from manhwa2vid.script.beats import _parse_markdown_beats

    path = tmp_path / "script.final.md"
    path.write_text(
        "# T — Chapters 1\n\n**Hook:** h\n\n## Beats\n\n"
        "### Beat 1\n<!-- panels: p0001_01, p0001_02 -->\n\nFirst beat.\n\n"
        "### Beat 2\n\nSecond beat, comment deleted by a human editor.\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="beat 2 has no"):
        _parse_markdown_beats(path)


def test_markdown_parse_survives_a_horizontal_rule_inside_narration(tmp_path):
    """A `---` line used to `break` the parse, discarding the rest of the script.

    The trailer that follows the real `---` is terminated by its "Edit freely" line, so
    only that needs to stop parsing. Freeform prose may legitimately contain a rule.
    """
    from manhwa2vid.script.beats import _parse_markdown_beats

    path = tmp_path / "script.final.md"
    path.write_text(
        "# T — Chapters 1\n\n## Beats\n\n"
        "### Beat 1\n<!-- panels: p0001_01 -->\n\nBefore the rule.\n\n---\n\n"
        "### Beat 2\n<!-- panels: p0002_01 -->\n\nAfter the rule.\n\n"
        "---\nEdit freely. Save approved version as script.final.md\n",
        encoding="utf-8",
    )
    beats = _parse_markdown_beats(path)
    assert [b.beat_id for b in beats] == [1, 2]
    assert beats[1].panel_ids == ["p0002_01"]
    assert "Edit freely" not in " ".join(b.narration for b in beats)


def test_markdown_beats_do_not_inherit_the_previous_beats_panels(tmp_path):
    from manhwa2vid.script.beats import _parse_markdown_beats

    path = tmp_path / "script.final.md"
    path.write_text(
        "## Beats\n\n"
        "### Beat 1\n<!-- panels: p0001_01, p0001_02 | key: p0001_02 -->\n\nOne.\n\n"
        "### Beat 2\n<!-- panels: p0009_01 -->\n\nTwo.\n",
        encoding="utf-8",
    )
    beats = _parse_markdown_beats(path)
    assert beats[0].panel_ids == ["p0001_01", "p0001_02"]
    assert beats[0].key_panel_ids == ["p0001_02"]
    assert beats[1].panel_ids == ["p0009_01"]
    assert beats[1].key_panel_ids == []
