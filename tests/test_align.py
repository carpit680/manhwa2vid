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
