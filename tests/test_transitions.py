"""Transition detection: the manhwa prints its own time skips and we used to ignore them."""

from __future__ import annotations

from manhwa2vid.models import SceneCard, ScriptOutlineBeat
from manhwa2vid.script.grounding import scene_boundaries, transition_captions


def _card(pid, *, page_text="", action="something happens"):
    return SceneCard(panel_ids=[pid], action=action, source_text=page_text)


def test_captions_are_read_off_the_artwork():
    """Frozen Player's panels literally read "25 YEARS AGO" and "25 YEARS LATER"; vision
    captured both into the cards and nothing downstream ever looked."""
    cards = [
        _card("p0005_01", page_text='"25 YEARS AGO"'),
        _card("p0008_01", action="A time skip to the present day is shown", page_text='"25 YEARS LATER"'),
        _card("p0009_01", page_text='Rell: "WE MOVE OUT."'),
        _card("p0010_01", action="a flashback to the war"),
    ]
    caps = transition_captions(cards)
    assert caps["p0005_01"] == "25 YEARS AGO"
    assert caps["p0008_01"] == "25 YEARS LATER"
    assert "p0009_01" not in caps            # ordinary dialogue is not a transition
    assert caps["p0010_01"] == "flashback"   # paraphrased in action, still caught


def test_boundaries_prefer_the_caption_over_page_arithmetic():
    """Page gaps find nothing on a densely-paginated chapter — every Frozen Player
    beat-to-beat gap is <= 1 — so the caption has to be the primary signal."""
    cards = [_card("p0001_01"), _card("p0002_01", page_text='"25 YEARS LATER"'), _card("p0003_01")]
    beats = [
        ScriptOutlineBeat(beat_id=1, panel_ids=["p0001_01"], plot_beat="the fight"),
        ScriptOutlineBeat(beat_id=2, panel_ids=["p0002_01"], plot_beat="the museum"),
        ScriptOutlineBeat(beat_id=3, panel_ids=["p0003_01"], plot_beat="the crowd"),
    ]
    found = scene_boundaries(beats, cards)
    assert list(found) == [2]
    assert "25 YEARS LATER" in found[2]      # quotable in a fix hint


def test_an_interval_caption_beats_a_bare_flashback_label():
    cards = [_card("p0001_01"),
             _card("p0002_01", action="flashback"),
             _card("p0002_02", page_text='"25 YEARS LATER"')]
    beats = [ScriptOutlineBeat(beat_id=1, panel_ids=["p0001_01"], plot_beat="a"),
             ScriptOutlineBeat(beat_id=2, panel_ids=["p0002_01", "p0002_02"], plot_beat="b")]
    assert "25 YEARS LATER" in scene_boundaries(beats, cards)[2]


def test_flashforward_anchor_and_page_gap_still_work_without_captions():
    """Solo Leveling prints no captions at all — its jump is a white-flash panel, caught
    by the flashforward anchor. One signal set, two titles, opposite shapes."""
    cards = [_card(f"p000{i}_01") for i in range(1, 5)]
    beats = [ScriptOutlineBeat(beat_id=1, panel_ids=["p0001_01"], plot_beat="a"),
             ScriptOutlineBeat(beat_id=2, panel_ids=["p0002_01"], plot_beat="b"),
             ScriptOutlineBeat(beat_id=3, panel_ids=["p0004_01"], plot_beat="c")]
    assert not transition_captions(cards)
    ff = scene_boundaries(beats, cards, flashforward_panel="p0001_01")
    assert 2 in ff and "flashforward" in ff[2]
    gap = scene_boundaries(beats, cards)
    assert 3 in gap and "page" in gap[3]


def test_caption_panels_are_never_curated_out():
    """The panel reading "25 YEARS LATER" was dropped by curation, so the one frame that
    tells a viewer time moved never reached the screen — most of why that jump plays as a
    continuation. A caption panel has no people and no conversation, so every salience
    heuristic scores it like scenery; it is the opposite of skippable."""
    from manhwa2vid.models import ChapterSynopsis
    from manhwa2vid.script.curate import select_narrated_panels

    cards = [_card(f"p{i:04d}_01", page_text=f'Rell -> Vesh: "LINE {i}"', action="they talk")
             for i in range(1, 60)]
    cards.append(_card("p0060_01", page_text='"25 YEARS LATER"', action="a wide empty sky"))
    caps = transition_captions(cards)
    assert "p0060_01" in caps

    cfg = {"script": {"words_per_chapter": 120, "target_wpm": 237},
           "video": {"target_panel_seconds": 2.5}}
    syn = ChapterSynopsis(logline="l", acts=[], named_cast=[], plot_facts=[])
    unpinned, dropped = select_narrated_panels(cards, syn, cfg, n_chapters=1)
    pinned, _ = select_narrated_panels(cards, syn, cfg, n_chapters=1, pinned=set(caps))

    assert "p0060_01" in pinned                     # pinned: always kept
    assert len(pinned) < len(cards)                 # and curation still cut the rest


def test_a_beat_never_straddles_a_printed_time_cut():
    """enforce_reading_order guarantees a beat is contiguous; nothing guaranteed it sits
    inside ONE time frame. Frozen Player's beat 7 held the "25 YEARS LATER" panel in its
    middle while narrating a farewell twenty-five years earlier — so it had to tell two
    time frames at once and no opening sentence could mark the jump."""
    from manhwa2vid.script.grounding import split_beats_at_transitions

    cards = [_card("p0001_01"), _card("p0001_02"),
             _card("p0002_01", page_text='"25 YEARS LATER"'), _card("p0002_02")]
    beats = [ScriptOutlineBeat(beat_id=1,
                               panel_ids=["p0001_01", "p0001_02", "p0002_01", "p0002_02"],
                               plot_beat="the farewell and then the museum")]
    out = split_beats_at_transitions(beats, cards)
    assert [b.panel_ids for b in out] == [["p0001_01", "p0001_02"], ["p0002_01", "p0002_02"]]
    assert [b.beat_id for b in out] == [1, 2]          # renumbered contiguously
    # Pure re-partition: every panel survives, in order, exactly once.
    assert [p for b in out for p in b.panel_ids] == beats[0].panel_ids

    # A caption already at a beat's start is not a straddle and must not split.
    aligned = [ScriptOutlineBeat(beat_id=1, panel_ids=["p0002_01", "p0002_02"], plot_beat="x")]
    assert len(split_beats_at_transitions(aligned, cards)) == 1
    # No captions at all -> untouched (Solo Leveling's shape).
    assert split_beats_at_transitions(aligned, [_card("p0002_01")]) == aligned
