"""The aligner's deterministic half: given a fixed paragraph->page map, the panel
expansion must be stable, order-preserving, and never leave a beat without images."""

from __future__ import annotations

from manhwa2vid.models import Panel, PanelBBox
from manhwa2vid.script.align import expand_to_panels, key_panels_for
from manhwa2vid.script.freeform import paragraphs


def _panels(spec: dict[str, int]) -> list[Panel]:
    out: list[Panel] = []
    for page, count in spec.items():
        for i in range(1, count + 1):
            out.append(
                Panel(
                    id=f"p{page}_{i:02d}",
                    page_num=int(page),
                    bbox=PanelBBox(x=0, y=0, width=100, height=100),
                    image_path=f"panels/p{page}_{i:02d}.png",
                )
            )
    return out


PANELS = _panels({"0001": 2, "0002": 3, "0003": 1, "0004": 2, "0020": 2})


def test_expansion_is_deterministic_and_page_ordered():
    entries = [
        {"paragraph": 1, "first_page": "0001", "last_page": "0002"},
        {"paragraph": 2, "first_page": "0003", "last_page": "0004"},
    ]
    first = expand_to_panels(entries, 2, PANELS)
    assert first == expand_to_panels(entries, 2, PANELS), "same map must give same panels"
    assert first[0] == ["p0001_01", "p0001_02", "p0002_01", "p0002_02", "p0002_03"]
    assert first[1] == ["p0003_01", "p0004_01", "p0004_02"]


def test_cold_open_keeps_late_pages_in_the_first_beat():
    """The whole point of the inversion: paragraph order is not page order.

    A recap may open on the climax and jump back. The old architecture forbade this by
    construction (`enforce_reading_order` + panel conservation); here it must simply work.
    """
    entries = [
        {"paragraph": 1, "first_page": "0020", "last_page": "0020"},
        {"paragraph": 2, "first_page": "0001", "last_page": "0001"},
    ]
    out = expand_to_panels(entries, 2, PANELS)
    assert out[0] == ["p0020_01", "p0020_02"]
    assert out[1] == ["p0001_01", "p0001_02"]


def test_unmapped_paragraph_interpolates_between_its_neighbours():
    """A missing entry must not default to page 1 — that silently narrates the opening
    over a late moment, which is the class of bug this architecture exists to remove."""
    entries = [
        {"paragraph": 1, "first_page": "0001", "last_page": "0001"},
        {"paragraph": 3, "first_page": "0004", "last_page": "0004"},
    ]
    out = expand_to_panels(entries, 3, PANELS)
    assert out[1], "unmapped paragraph must still get panels"
    assert all(p.startswith(("p0001", "p0002", "p0003", "p0004")) for p in out[1])
    assert not any(p.startswith("p0020") for p in out[1])


def test_range_with_no_story_panels_borrows_the_nearest_page():
    """A beat resolving to zero panels has its audio dropped from the mix entirely, so
    an empty range must degrade to nearby images rather than to silence."""
    entries = [{"paragraph": 1, "first_page": "0010", "last_page": "0012"}]
    out = expand_to_panels(entries, 1, PANELS)
    assert out[0], "must borrow rather than return empty"
    assert all(p.startswith("p0004") for p in out[0]), "0004 is the nearest page with panels"


def test_bad_map_entries_are_ignored_not_fatal():
    entries = [
        {"paragraph": "not-a-number", "first_page": "0001"},
        {"paragraph": 99, "first_page": "0001"},          # out of range
        {"paragraph": 1, "first_page": "0002", "last_page": "0002"},
    ]
    out = expand_to_panels(entries, 1, PANELS)
    assert out[0] == ["p0002_01", "p0002_02", "p0002_03"]


def test_key_panels_spread_across_the_beat():
    ids = [f"p0001_{i:02d}" for i in range(1, 10)]
    keys = key_panels_for(ids)
    assert keys[0] == ids[0] and keys[-1] == ids[-1]
    assert len(keys) == 3
    assert key_panels_for(ids[:2]) == ids[:2]


def test_paragraph_split_is_the_beat_boundary():
    text = "First movement.\n\nSecond movement.\n\n\nThird movement.\n"
    assert paragraphs(text) == ["First movement.", "Second movement.", "Third movement."]


# --- identity gate -------------------------------------------------------------------

def test_name_integrity_flags_invented_names_and_accepts_known_aliases():
    """The whole identity system, replacing protagonist election + pronoun inference +
    alias scoring + descriptor consolidation: is this name one we actually know?

    A wrongly-elected protagonist once put "large orange demon" into five beats and a
    174-descriptor profile made the lead "they". Neither can happen against a flat
    glossary — and when this gate fires, the fix is one line of glossary.json.
    """
    from manhwa2vid.script.story_first import unknown_names

    allowed = {"Seo Jun-Ho", "Specter", "Deok-gu", "Frost Queen"}
    text = (
        "Deep in the cavern, Seo Jun-Ho draws his blade. The Frost Queen laughs at him. "
        "Later, Deok-gu explains the elevator. Then Kang Min-Su interrupts them."
    )
    assert unknown_names(text, allowed) == ["Kang Min-Su"]

    # A first-name-only reference to a known full name is fine.
    assert unknown_names("The healer nods. Jun-Ho says nothing.", allowed) == []
    # No glossary means the gate cannot judge, so it must not block.
    assert unknown_names(text, set()) == []


def test_name_integrity_ignores_sentence_openers():
    """Sentence-case openers are not names; flagging them would drown the signal."""
    from manhwa2vid.script.story_first import unknown_names

    text = "Deep breaths. Cold air bites. Nothing moves in the throne room."
    assert unknown_names(text, {"Seo Jun-Ho"}) == []


def test_long_paragraph_split_preserves_every_word():
    """Granularity is a production concern, handled here rather than in the prompt.

    The first freeform run told the WRITER that "a paragraph is the unit that will later
    be matched to images" — leaking panel-thinking straight back into the creative act
    this architecture exists to keep clean — and produced 10 paragraphs for 198 panels,
    about 20 panels of screen time per audio file. Splitting after the fact fixes the
    granularity without the writer ever knowing images exist.
    """
    from manhwa2vid.script.align import split_long_paragraphs

    para = " ".join(f"Sentence number {i} runs on for a little while." for i in range(1, 21))
    out = split_long_paragraphs([para], max_words=40)
    assert len(out) > 1
    assert " ".join(out).split() == para.split(), "no word may be lost or reordered"
    assert all(len(p.split()) >= 20 for p in out), "no stub chunks"


def test_short_paragraphs_are_left_alone():
    from manhwa2vid.script.align import split_long_paragraphs

    paras = ["Short and complete.", "Also short."]
    assert split_long_paragraphs(paras, max_words=90) == paras


def test_identity_gate_ignores_places_caps_and_merged_proper_nouns():
    """Three false-positive classes that all fired on the first readable-pages run.

    The gate must stay quiet on things that are correct, or it teaches the reader to
    ignore it — while still catching an invented person, which is its whole job.
    """
    from manhwa2vid.script.story_first import unknown_names

    allowed = {"Seo Jun-Ho", "Deok-gu"}

    # Places are not characters and will never be in a CHARACTER glossary.
    assert unknown_names("He runs to the Pacific Ocean. Then he stops.", allowed) == []
    assert unknown_names("It happened in Seoul History Museum. Lights flicker.", allowed) == []

    # Transcribed bracketed system text is caps, not a name.
    assert unknown_names("A window reads CONGRATULATIONS SURVIVOR. He blinks.", allowed) == []

    # Adjacent proper nouns from different noun phrases merge under a greedy match:
    # "the modern Earth Jun-Ho sees" is not a character called "Earth Jun-Ho".
    assert unknown_names("He studies the modern Earth Jun-Ho sees now. It is quiet.", allowed) == []

    # ...and the real thing still fires.
    assert unknown_names("The room stills. Then Kang Min-Su interrupts him.", allowed) == ["Kang Min-Su"]


def test_ceremonial_system_messages_are_not_spine():
    """Requiring every bracketed line drove the reviser to paste them in verbatim.

    "[CONGRATULATIONS.]" and "[AUTHENTICATION SUCCESSFUL.]" carry no story; demanding
    them produced narration that reads like a screen reader, which the writer's own
    brief forbids. A duplicate message asked for twice got pasted twice.
    """
    from manhwa2vid.script.audit import _undelivered_spine

    facts = {
        "system_messages": [
            "[CONGRATULATIONS.]",
            "[CONGRATULATIONS.]",
            "[AUTHENTICATION SUCCESSFUL.]",
            "[YOU ARE ABLE TO REMOVE THE SEAL ON THE ICE STATUS.]",
        ]
    }
    narration = "He wakes up and walks to the hall. The ice holds his friends."
    missing = _undelivered_spine(narration, facts)
    assert missing == ["[YOU ARE ABLE TO REMOVE THE SEAL ON THE ICE STATUS.]"]

    delivered = "He learns he can remove the seal on the ice once he is strong enough."
    assert _undelivered_spine(delivered, facts) == []


def test_identity_gate_is_advisory_and_its_limit_is_pinned():
    """The gate reports; it does not block. This test records WHY.

    Across three real runs on two titles it produced five false-positive classes and no
    true positives. Four are now handled; the fifth — a correctly-named place that is
    not preceded by a locative preposition, like "the commandments of the Carthenon
    Temple" — needs a POS tagger to separate from an invented person, so it is recorded
    as a known limit rather than chased with another heuristic.
    """
    from manhwa2vid.script.story_first import unknown_names

    allowed = {"Sung Jin-Woo"}
    # Handled classes stay quiet.
    assert unknown_names("He is nobody. Jin-Woo is an E-Rank Hunter now.", allowed) == []
    assert unknown_names("They run to the Carthenon Temple. It is cold.", allowed) == []
    # KNOWN LIMIT: same place, no locative preposition, still reported.
    assert unknown_names(
        "He reads them. It lists the commandments of the Carthenon Temple.", allowed
    ) == ["Carthenon Temple"]
    # The case it exists for still fires.
    assert unknown_names("The hall stills. Then Kang Min-Su interrupts him.", allowed) == [
        "Kang Min-Su"
    ]


def test_thin_range_borrows_adjacent_pages_for_airtime():
    """A paragraph must own enough panels for its airtime — one FP beat ended up as a
    single panel frozen for 17 seconds after the emptiness filter thinned its range."""
    from manhwa2vid.script.align import expand_to_panels

    entries = [{"paragraph": 1, "first_page": "0003", "last_page": "0003"}]
    # page 0003 has 1 panel; a ~40s paragraph at 5s/panel needs 8.
    out = expand_to_panels(entries, 1, PANELS, min_panels={1: 8})
    assert len(out[0]) >= 8, f"got only {len(out[0])} panels"
    assert "p0003_01" in out[0], "the original range must survive"
    # without a requirement, the thin range stays thin
    assert expand_to_panels(entries, 1, PANELS) == [["p0003_01"]]


def test_time_blocks_stop_panels_crossing_a_printed_scene_break():
    """The user's report: narration still on the Frost Queen fight while the panels had
    already cut to the 76-hours-earlier flashback.

    The manhwa prints "76 HOURS AGO, ANTARCTICA" and the read stage records its page —
    but these pages are 10-14k-pixel scroll strips, so page 0005 holds the END of the
    fight in panels 1-13 and the flashback caption in panel 14. Cutting on the PAGE
    would strand thirteen fight panels: the boundary must be the panel.
    """
    from manhwa2vid.script.align import clamp_to_time_blocks

    ordered = [f"p0005_{i:02d}" for i in range(1, 15)] + [f"p0006_{i:02d}" for i in range(1, 5)]
    paras = [
        "The queen of ice stands tall in her frozen throne room.",
        "The Frost Queen crumbles into nothing.",
        "Seventy-six hours earlier, the Nest Attack Team stands at the stairs.",
    ]
    # As mis-aligned: paragraph 1 reaches past the boundary into the flashback.
    lists = [
        ordered[0:14],      # para 1 — includes p0005_14, the flashback caption
        ordered[8:14],      # para 2 — same overreach
        ordered[13:18],     # para 3 — the flashback
    ]
    out = clamp_to_time_blocks(lists, paras, ordered, ["p0005_14"])
    assert "p0005_14" not in out[0], "fight narration must not show the flashback caption"
    assert "p0005_14" not in out[1]
    assert out[2][0] == "p0005_14", "the flashback paragraph starts ON the caption"
    assert "p0005_13" in out[0], "the fight's own panels must survive"
    # No boundary -> untouched.
    assert clamp_to_time_blocks(lists, paras, ordered, []) == lists


def test_time_block_clamp_never_strands_a_paragraph():
    from manhwa2vid.script.align import clamp_to_time_blocks

    ordered = [f"p0001_{i:02d}" for i in range(1, 9)]
    paras = ["Opening.", "Twenty-five years later, a museum."]
    # para 2's panels all sit in block 0 — clamping would empty it.
    out = clamp_to_time_blocks([ordered[0:4], ordered[0:2]], paras, ordered, ["p0001_05"])
    assert out[1], "a clamped paragraph must fall back to its own block, not vanish"
    assert all(p >= "p0001_05" for p in out[1])


def test_clamped_paragraph_falls_back_to_the_end_it_overran():
    """A beat narrating the fight's AFTERMATH, whose panels sat just past the boundary,
    was sent back to the chapter's opening panels and replayed page one mid-scene.
    Falling back to the block's head is only right when the paragraph undershot."""
    from manhwa2vid.script.align import clamp_to_time_blocks

    ordered = [f"p0005_{i:02d}" for i in range(1, 15)] + [f"p0006_{i:02d}" for i in range(1, 5)]
    paras = [
        "The queen stands tall.",
        "The Frost Queen crumbles into nothing.",
        "Seventy-six hours earlier, the team stands at the stairs.",
    ]
    out = clamp_to_time_blocks(
        [ordered[0:12], ordered[14:17], ordered[15:18]], paras, ordered, ["p0005_14"]
    )
    assert out[1][0] in ("p0005_11", "p0005_12", "p0005_13"), out[1][:2]
    assert not out[1][0].startswith("p0005_01"), "must not replay the opening"


def test_jump_paragraph_opens_on_the_caption_panel():
    """The chapter's own "76 HOURS AGO" panel should be the image that announces the
    jump — otherwise it is the one panel nobody ever shows."""
    from manhwa2vid.script.align import clamp_to_time_blocks

    ordered = [f"p0005_{i:02d}" for i in range(1, 15)] + [f"p0006_{i:02d}" for i in range(1, 5)]
    paras = ["The queen stands tall.", "Seventy-six hours earlier, the team stands."]
    out = clamp_to_time_blocks([ordered[0:12], ordered[15:18]], paras, ordered, ["p0005_14"])
    assert out[1][0] == "p0005_14"


def test_paragraphs_get_forward_non_overlapping_runs():
    """Neighbouring page ranges overlap, so taking every panel on a paragraph's pages
    made consecutive beats replay each other — measured on FP, 8 of 16 beats began
    BEFORE the previous beat ended. On screen that is the video rewinding mid-sentence.
    """
    from manhwa2vid.script.align import distribute_within_blocks

    ordered = [f"p{p:04d}_{i:02d}" for p in range(1, 5) for i in range(1, 6)]  # 20 panels
    overlapping = [ordered[0:12], ordered[8:14], ordered[10:20]]
    out = distribute_within_blocks(overlapping, ordered, [0, 0, 0], [(0, len(ordered))])

    assert all(out), "no paragraph may end up empty"
    flat = [pid for run in out for pid in run]
    assert len(flat) == len(set(flat)), "a panel must not be shown by two beats"
    idx = {pid: i for i, pid in enumerate(ordered)}
    for earlier, later in zip(out, out[1:]):
        assert idx[later[0]] > idx[earlier[-1]], "runs must move forward"
    assert out[-1][-1] == ordered[-1], "the block's tail must be covered"


def test_forward_runs_respect_time_blocks():
    """Blocks may jump backward in story time — that is the flashback. Forward progress
    is only required WITHIN a block."""
    from manhwa2vid.script.align import distribute_within_blocks

    ordered = [f"p0001_{i:02d}" for i in range(1, 11)]
    blocks = [(0, 5), (5, 10)]
    out = distribute_within_blocks(
        [ordered[0:3], ordered[3:5], ordered[5:8], ordered[8:10]],
        ordered, [0, 0, 1, 1], blocks,
    )
    assert all(p in ordered[0:5] for p in out[0] + out[1])
    assert all(p in ordered[5:10] for p in out[2] + out[3])


def test_greedy_paragraph_cannot_starve_its_block_neighbours():
    """Reserving one panel per remaining paragraph was not enough: beat 1 swallowed its
    whole time block and left beat 2 a single image held for 22.9 seconds."""
    from manhwa2vid.script.align import distribute_within_blocks

    ordered = [f"p0001_{i:02d}" for i in range(1, 21)]
    # para 1's model range covers almost everything; para 2 needs 4 panels of airtime.
    out = distribute_within_blocks(
        [ordered[0:18], ordered[17:20]], ordered, [0, 0], [(0, 20)], {1: 6, 2: 4}
    )
    assert len(out[1]) >= 4, f"neighbour starved: {out[1]}"
    assert len(out[0]) >= 6


def test_oversubscribed_block_degrades_evenly():
    """When a block cannot satisfy every minimum, scale them together rather than
    letting the last paragraph take whatever is left."""
    from manhwa2vid.script.align import distribute_within_blocks

    ordered = [f"p0001_{i:02d}" for i in range(1, 7)]
    out = distribute_within_blocks(
        [ordered[0:3], ordered[2:5], ordered[4:6]], ordered, [0, 0, 0], [(0, 6)],
        {1: 4, 2: 4, 3: 4},
    )
    assert sum(len(o) for o in out) == 6
    assert max(len(o) for o in out) - min(len(o) for o in out) <= 1


def test_no_paragraph_can_swallow_a_block():
    """Solo Leveling: a 33-word beat was handed 170 panels because it sat last before a
    time boundary, and the panel budget then threw 166 of them away — while a 69-word
    beat two along got two panels and froze for 9.2 seconds."""
    from manhwa2vid.script.align import distribute_within_blocks

    ordered = [f"p{p:04d}_{i:02d}" for p in range(1, 21) for i in range(1, 11)]  # 200
    mins = {1: 6, 2: 5, 3: 8, 4: 3, 5: 7, 6: 4, 7: 6, 8: 2}
    lists = [ordered[i * 10 : (i + 1) * 10] for i in range(8)]
    out = distribute_within_blocks(lists, ordered, [0] * 8, [(0, 200)], mins)

    counts = [len(o) for o in out]
    assert sum(counts) == 200 and len({q for o in out for q in o}) == 200
    assert max(counts) <= 4 * min(counts), f"one paragraph swallowed the block: {counts}"
    # Allocation tracks airtime: the 8-unit paragraph outranks the 3-unit one.
    assert counts[2] > counts[3]
    # Every run stays in reading order after leftovers are handed out.
    idx = {pid: i for i, pid in enumerate(ordered)}
    for run in out:
        assert [idx[q] for q in run] == sorted(idx[q] for q in run)


def test_blocks_are_assigned_by_position_not_by_jump_phrases():
    """Jump PHRASES do not pair one-to-one with printed MARKERS.

    Frozen Player had 2 markers and 2 announcing paragraphs, so counting phrases worked
    by luck. Solo Leveling has 3 phrases and 1 printed marker, and the first phrase was
    incidental narration in paragraph 9 — which put 8 paragraphs on the 271 panels
    before the boundary and 30 on the 69 after, i.e. 2.3 panels each and a 14.9s freeze.
    """
    from manhwa2vid.script.align import clamp_to_time_blocks

    ordered = [f"p{p:04d}_{i:02d}" for p in range(1, 16) for i in range(1, 11)]  # 150
    # Ten paragraphs sit before the boundary; only the last two are past it. Several
    # early ones contain incidental jump language.
    paras = ["He moves on."] * 4 + ["Moments later, he stands."] + ["Then he waits."] * 5 + [
        "Twenty-five years later, a museum.", "The hall is quiet."
    ]
    lists = [ordered[i * 12 : (i + 1) * 12] for i in range(10)] + [
        ordered[120:135], ordered[135:150]
    ]
    clamp_to_time_blocks(lists, paras, ordered, [ordered[120]])
    blocks = clamp_to_time_blocks.last_block_of
    assert blocks.count(0) == 10 and blocks.count(1) == 2, blocks
    assert blocks == sorted(blocks), "narration runs forward through blocks"


def test_block_crossing_uses_text_and_position_together():
    """Neither signal alone works, and each failed on a different real title.

    Text alone (advance at every jump PHRASE) inverted Solo Leveling: 3 phrases, 1
    printed marker, first phrase incidental in paragraph 9 — 8 paragraphs on 271 panels,
    30 on 69. Position alone breaks Frozen Player: the paragraph narrating the fight's
    end was aligned past the boundary, so trusting position puts fight narration over
    flashback art, which is the defect this mechanism exists to prevent.
    """
    from manhwa2vid.script.align import clamp_to_time_blocks

    # Frozen Player shape: para 2 narrates the fight but was aligned past the boundary.
    fp = [f"p0005_{i:02d}" for i in range(1, 15)] + [f"p0006_{i:02d}" for i in range(1, 5)]
    clamp_to_time_blocks(
        [fp[0:12], fp[14:17], fp[15:18]],
        ["The queen stands.", "The Frost Queen crumbles.", "Seventy-six hours earlier, they stand."],
        fp, ["p0005_14"],
    )
    assert clamp_to_time_blocks.last_block_of == [0, 0, 1]

    # Solo Leveling shape: an incidental phrase early, the real skip late.
    sl = [f"p{p:04d}_{i:02d}" for p in range(1, 16) for i in range(1, 11)]
    paras = ["x"] * 4 + ["Moments later, he waits."] + ["y"] * 5 + [
        "Twenty-five years later, a museum.", "The hall is quiet."
    ]
    lists = [sl[i * 12 : (i + 1) * 12] for i in range(10)] + [sl[120:135], sl[135:150]]
    clamp_to_time_blocks(lists, paras, sl, [sl[120]])
    blocks = clamp_to_time_blocks.last_block_of
    assert blocks.count(0) == 10 and blocks.count(1) == 2, blocks
