"""Reference-paced panel curation: the density constant is derived from the reference
profile (target_wpm x target_panel_seconds / 60), never tuned per title."""

from __future__ import annotations

from manhwa2vid.models import ChapterSynopsis, CharacterRef, SceneCard
from manhwa2vid.script.curate import select_narrated_panels, words_per_shown_panel


def _card(pid: str, *, dialogue: str = "", people: int = 0, action: str = "something happens"):
    return SceneCard(
        panel_ids=[pid], action=action, source_text=dialogue,
        people=[CharacterRef(ref=f"char_{i}", name_used=f"Person{i}") for i in range(people)],
    )


def _synopsis(facts):
    return ChapterSynopsis(logline="l", acts=[], named_cast=[], plot_facts=facts)


def test_density_constant_is_derived_not_tuned():
    cfg = {"script": {"target_wpm": 237}, "video": {"target_panel_seconds": 2.5}}
    assert abs(words_per_shown_panel(cfg) - 9.875) < 0.01


def test_sparse_chapter_selects_everything():
    """The no-op guard: when the word budget covers the whole inventory, curation must
    not touch the title that already works."""
    cards = [_card(f"p{i:04d}_01", dialogue="X: hi") for i in range(1, 31)]
    cfg = {"script": {"words_per_chapter": 550}, "video": {}}
    narrated, dropped = select_narrated_panels(cards, _synopsis([]), cfg, n_chapters=1)
    assert len(narrated) == 30 and dropped == {}


def test_dense_range_selects_reference_fraction_and_is_deterministic():
    cards = []
    for i in range(1, 201):
        pid = f"p{i:04d}_01"
        cards.append(_card(pid, dialogue=('A -> B: "words here"' if i % 3 else ""), people=i % 4))
    cfg = {"script": {"words_per_chapter": 550, "target_wpm": 237},
           "video": {"target_panel_seconds": 2.5}}
    n1, d1 = select_narrated_panels(cards, _synopsis([]), cfg, n_chapters=2)
    n2, d2 = select_narrated_panels(cards, _synopsis([]), cfg, n_chapters=2)
    assert (n1, d1) == (n2, d2)                       # same input -> same set, always
    assert len(n1) + len(d1) == 200                    # nothing vanishes
    assert 0.4 <= len(n1) / 200 <= 0.75                # the reference's ~half, not a purge
    assert n1 == sorted(n1)                            # reading order preserved


def test_dialogue_and_fact_panels_outrank_silent_scenery():
    cards = [
        _card("p0001_01", dialogue='Rell -> Vesh: "THE GATE OPENS AT DAWN."', people=2),
        _card("p0002_01"),  # silent, nobody
        _card("p0003_01", dialogue='Vesh: "..."', people=1),
        _card("p0004_01", action="the gate opens at dawn over the harbour"),
    ]
    cfg = {"script": {"words_per_chapter": 20, "target_wpm": 237},
           "video": {"target_panel_seconds": 2.5}}  # budget of 2
    narrated, dropped = select_narrated_panels(
        cards, _synopsis(["the gate opens at dawn"]), cfg, n_chapters=1)
    assert "p0001_01" in narrated                      # dialogue + fact + people
    assert "p0002_01" in dropped                       # nothing going for it
    assert dropped["p0002_01"]                         # and a reason is recorded


def test_pinned_panels_always_survive():
    cards = [_card(f"p{i:04d}_01") for i in range(1, 21)]
    cfg = {"script": {"words_per_chapter": 30, "target_wpm": 237},
           "video": {"target_panel_seconds": 2.5}}
    narrated, _ = select_narrated_panels(
        cards, _synopsis([]), cfg, n_chapters=1, pinned={"p0007_01", "p0020_01"})
    assert "p0007_01" in narrated and "p0020_01" in narrated


def test_continuity_floor_breaks_long_dropped_runs():
    """The reference crops and skips; it never jump-cuts a whole scene. No run of
    consecutive dropped panels may exceed the floor."""
    cards = [_card(f"p{i:04d}_01", dialogue=('X: "hi"' if i <= 5 else "")) for i in range(1, 41)]
    cfg = {"script": {"words_per_chapter": 60, "target_wpm": 237},
           "video": {"target_panel_seconds": 2.5}}
    narrated, dropped = select_narrated_panels(cards, _synopsis([]), cfg, n_chapters=1)
    ids = sorted({c.panel_ids[0] for c in cards})
    run = worst = 0
    for pid in ids:
        run = run + 1 if pid in dropped else 0
        worst = max(worst, run)
    assert worst <= 3


def test_unbound_facts_become_required_context_not_silence():
    """A synopsis fact that binds to no single panel used to be dropped, taking the
    chapter's payoffs with it: Frozen Player's "the 3rd floor needs the Frost Queen's
    nucleus" and "Frost (EX) can melt the seals" are what the reference channel builds its
    climax on, and neither reached our narration."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.grounding import preassign_outline_from_facts

    cards = [
        _card("p0001_01", dialogue='Rell -> Vesh: "THE GATE OPENS AT DAWN."', people=1,
              action="Rell and Vesh stand at the gate at dawn"),
        _card("p0002_01", dialogue='Vesh: "WE MOVE OUT."', people=1, action="they move out"),
    ]
    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="mc",
        characters={"mc": CharacterProfile(id="mc", canonical_name="Rell",
                                           tier=CharacterTier.MAIN)},
    )
    synopsis = _synopsis([
        "The gate opens at dawn and Rell is waiting for it.",          # binds to p0001_01
        "Nobody has cleared the seventh vault because the seal needs a drake's heart.",
    ])
    beats = preassign_outline_from_facts(synopsis, cards, bible, max_beats=4)
    carried = [c for b in beats for c in b.required_context]
    assert any("drake" in c for c in carried), "the unbindable fact must survive somewhere"
