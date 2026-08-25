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
