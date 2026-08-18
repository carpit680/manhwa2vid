"""Story-first script helpers and lint tests."""

from __future__ import annotations

from pathlib import Path

from manhwa2vid.models import (
    ChapterSynopsis,
    CharacterProfile,
    CharacterRef,
    CharacterTier,
    SceneCard,
    ScriptBeat,
    SeriesBible,
)
from manhwa2vid.script.generate import (
    _attach_missing_panels_to_beats,
    _panel_sort_key,
    _parse_markdown_beats,
)
from manhwa2vid.script.grounding import (
    preassign_outline_from_facts,
    unsupported_grounding_keywords,
)
from manhwa2vid.script.lint import (
    find_hedge_violations,
    lint_aside_overuse,
    lint_hedging,
    lint_mc_name_spam,
    lint_panel_grounding,
    local_sanitize_narration,
)
from manhwa2vid.video.timeline import split_beat_durations


def test_attach_missing_panels_to_nearest_beat() -> None:
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p0002_01"], narration="Hook."),
        ScriptBeat(beat_id=2, panel_ids=["p0005_01"], narration="Fight."),
        ScriptBeat(beat_id=3, panel_ids=["p0010_01"], narration="City."),
    ]
    all_panels = ["p0002_01", "p0003_01", "p0005_01", "p0006_01", "p0010_01"]
    result = _attach_missing_panels_to_beats(all_panels, beats)
    covered = {pid for beat in result for pid in beat.panel_ids}
    assert covered == set(all_panels)
    assert len(result) == 3  # no caption filler beats
    assert "p0003_01" in result[0].panel_ids or "p0003_01" in result[1].panel_ids


def test_panel_sort_key_orders_pages() -> None:
    ids = ["p0010_02", "p0002_01", "p0010_01"]
    assert sorted(ids, key=_panel_sort_key) == ["p0002_01", "p0010_01", "p0010_02"]


def test_hedge_lint_flags_possibly() -> None:
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="He walks, possibly hurt."),
        ScriptBeat(beat_id=2, panel_ids=["p2"], narration="He joins the party."),
    ]
    report = lint_hedging(beats)
    assert 1 in report
    assert "possibly" in report[1]
    assert 2 not in report


def test_local_sanitize_strips_common_hedges() -> None:
    text = local_sanitize_narration("He is seen sitting, possibly recovering, highlighting the risks.")
    assert "possibly" not in text.lower()
    assert "highlighting" not in text.lower()
    assert "is seen" not in text.lower()


def test_mc_name_spam_after_hook() -> None:
    bible = SeriesBible(
        series_slug="solo-leveling",
        title="Solo Leveling",
        protagonist_id="char_sung_jin_woo",
        characters={
            "char_sung_jin_woo": CharacterProfile(
                id="char_sung_jin_woo",
                canonical_name="Sung Jin-Woo",
                tier=CharacterTier.MAIN,
            )
        },
    )
    # Spam is DENSITY, not existence: one anchor per beat is the reference register
    # (the old cumulative cap produced the 'he for fifteen beats' video); two names in
    # ONE beat is the true name-spam-every-12-words failure this lint was born from.
    config: dict = {}
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="Sung Jin-Woo is the weakest hunter."),
        ScriptBeat(beat_id=2, panel_ids=["p2"], narration="Sung Jin-Woo walks home."),
        ScriptBeat(beat_id=3, panel_ids=["p3"], narration="Sung Jin-Woo meets Song."),
        ScriptBeat(
            beat_id=4, panel_ids=["p4"],
            narration="Sung Jin-Woo enters the gate. Sung Jin-Woo draws a breath.",
        ),
    ]
    report = lint_mc_name_spam(beats, bible, config)
    assert 4 in report, "two names in one beat is spam"
    assert 2 not in report and 3 not in report, "one anchor per beat is the register"
    assert "mc_full_name_spam" in report[4]


def test_aside_overuse() -> None:
    config = {"script": {"max_narrator_asides": 1}}
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="He survives. NGL that was rough."),
        ScriptBeat(beat_id=2, panel_ids=["p2"], narration="And look, bro, he is still going."),
    ]
    report = lint_aside_overuse(beats, config)
    assert 2 in report
    assert find_hedge_violations("He may be dying") == ["may be"]


def test_preassign_binds_coffee_fact_to_barista_panel() -> None:
    bible = SeriesBible(series_slug="t", title="T", protagonist_id="char_mc")
    cards = [
        SceneCard(
            panel_ids=["p0008_01"],
            action="walks down the street",
            dialogue_summary="",
            is_story=True,
            people=[CharacterRef(ref="char_mc", name_used="MC")],
        ),
        SceneCard(
            panel_ids=["p0017_02"],
            action="orders coffee",
            dialogue_summary="barista apologizes for being out of coffee",
            key_terms=["coffee"],
            is_story=True,
            people=[CharacterRef(ref="char_barista", name_used="barista")],
        ),
    ]
    synopsis = ChapterSynopsis(
        logline="test",
        plot_facts=["At a coffee shop the barista tells him they are out of coffee."],
    )
    outline = preassign_outline_from_facts(synopsis, cards, bible, max_beats=10)
    coffee_beat = next(b for b in outline if "coffee" in b.plot_beat.lower() or "barista" in b.plot_beat.lower())
    assert "p0017_02" in coffee_beat.panel_ids
    assert "p0008_01" not in coffee_beat.panel_ids


def test_ungrounded_coffee_on_street_panel() -> None:
    cards = [
        SceneCard(
            panel_ids=["p0008_01"],
            action="walks down the street",
            dialogue_summary="",
            is_story=True,
        )
    ]
    bad = unsupported_grounding_keywords(["p0008_01"], cards, "He steps into a coffee shop for coffee.")
    assert "coffee" in bad
    report = lint_panel_grounding(
        [ScriptBeat(beat_id=1, panel_ids=["p0008_01"], narration="He steps into a coffee shop.")],
        cards,
    )
    assert 1 in report


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


def test_collapsed_outline_keeps_seeded_structure() -> None:
    """An outline LLM that merges 12 seeded beats into 3 must not win.

    Reconciling a collapsed outline re-homes every orphaned panel onto the survivors,
    which once produced a single 32-panel beat spanning half of chapter 1. The seed is
    the deterministic panel-grounded structure; the LLM may only smooth wording.
    """
    from manhwa2vid.models import ScriptOutlineBeat
    from manhwa2vid.script.generate import _reconcile_outline_panels

    seeded = [
        ScriptOutlineBeat(beat_id=i, panel_ids=[f"p{i:04d}_01"], plot_beat=f"seed {i}")
        for i in range(1, 13)
    ]
    collapsed = [
        ScriptOutlineBeat(
            beat_id=1,
            panel_ids=[f"p{i:04d}_01" for i in range(1, 13)],
            plot_beat="everything at once",
        ),
        ScriptOutlineBeat(beat_id=2, panel_ids=[], plot_beat="tail"),
        ScriptOutlineBeat(beat_id=3, panel_ids=[], plot_beat="closer"),
    ]

    out = _reconcile_outline_panels(seeded, collapsed)

    assert len(out) == len(seeded), "seeded beat count must survive a collapsed LLM outline"
    assert max(len(b.panel_ids) for b in out) == 1, "no beat may absorb the orphaned panels"
    # LLM wording is still grafted on where the beat_id matched.
    assert out[0].plot_beat == "everything at once"
    assert out[5].plot_beat == "seed 6"


def test_reconcile_accepts_wording_only_rewrite() -> None:
    """The normal case — same beat count, same panels, better wording — still passes."""
    from manhwa2vid.models import ScriptOutlineBeat
    from manhwa2vid.script.generate import _reconcile_outline_panels

    seeded = [
        ScriptOutlineBeat(beat_id=i, panel_ids=[f"p{i:04d}_01"], plot_beat=f"seed {i}")
        for i in range(1, 6)
    ]
    smoothed = [
        ScriptOutlineBeat(beat_id=i, panel_ids=[f"p{i:04d}_01"], plot_beat=f"polished {i}")
        for i in range(1, 6)
    ]

    out = _reconcile_outline_panels(seeded, smoothed)

    assert [b.plot_beat for b in out] == [f"polished {i}" for i in range(1, 6)]
    assert [b.panel_ids for b in out] == [[f"p{i:04d}_01"] for i in range(1, 6)]


def test_verifier_cast_block_lists_visual_marks() -> None:
    """The alignment verifier must receive visual descriptions.

    Without them it cannot tell 'wrong person' from 'panels never caption names', so it
    flagged every named character as unsupported and the grounded-fallback replaced good
    narration with flat outline text on 8 of 18 beats.
    """
    from manhwa2vid.models import VisualProfile
    from manhwa2vid.script.verify import _cast_visuals

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc",
        canonical_name="Sung Jin-Woo",
        tier=CharacterTier.MAIN,
        visual=VisualProfile(hair="short black hair", accessories=["green backpack"]),
    )
    bible.characters["char_gone"] = CharacterProfile(
        id="char_gone",
        canonical_name="Merged Away",
        visual=VisualProfile(hair="red hair"),
        merged_into="char_mc",
    )

    block = _cast_visuals(bible)

    assert "Sung Jin-Woo" in block
    assert "green backpack" in block
    assert "[PROTAGONIST]" in block
    assert "Merged Away" not in block, "tombstoned profiles must not reach the prompt"


def test_verifier_cast_block_without_bible_disarms_name_flagging() -> None:
    from manhwa2vid.script.verify import _cast_visuals

    assert "do not flag any naming claim" in _cast_visuals(None)


def test_alignment_audit_sees_every_panel_of_a_beat(tmp_path: Path, monkeypatch) -> None:
    """The verifier must judge narration against ALL the beat's panels.

    Auditing only panel_ids[:3] made it flag whatever the narration drew from panels 4+
    ('no aerial view of Seoul' — Seoul was on panel 4). Those false majors survived the
    rewrite and forced the grounded fallback onto 4-5 beats of every ch1 run.
    """
    from PIL import Image

    from manhwa2vid.models import Panel, PanelBBox
    from manhwa2vid.script import verify as verify_mod

    panels: dict[str, Panel] = {}
    for i in range(1, 6):
        pid = f"p{i:04d}_01"
        rel = f"panels/{pid}.png"
        (tmp_path / "panels").mkdir(exist_ok=True)
        Image.new("RGB", (32, 32), "white").save(tmp_path / rel)
        panels[pid] = Panel(
            id=pid, page_num=i, bbox=PanelBBox(x=0, y=0, width=32, height=32), image_path=rel
        )

    seen: list[int] = []

    class _Spy:
        def describe_panels(self, image_paths, prompt):
            seen.append(len(image_paths))
            return '{"unsupported": [], "severity": "none"}'

    monkeypatch.setattr(verify_mod, "get_stage_llm", lambda *a, **k: _Spy())
    monkeypatch.setattr(verify_mod, "apply_stage_model", lambda llm, *a, **k: llm)

    beat = ScriptBeat(beat_id=1, panel_ids=list(panels), narration="Everything happens.")
    verify_mod.audit_frame_alignment([beat], panels, tmp_path, {})

    assert seen == [5], f"verifier saw {seen[0] if seen else 0} of 5 panels"


def test_alignment_audit_caps_pathological_beat(tmp_path: Path, monkeypatch) -> None:
    """A collapsed outline can hand over 30+ panels — cap the request, don't send them all."""
    from PIL import Image

    from manhwa2vid.models import Panel, PanelBBox
    from manhwa2vid.script import verify as verify_mod

    (tmp_path / "panels").mkdir()
    panels: dict[str, Panel] = {}
    for i in range(1, 21):
        pid = f"p{i:04d}_01"
        rel = f"panels/{pid}.png"
        Image.new("RGB", (16, 16), "white").save(tmp_path / rel)
        panels[pid] = Panel(
            id=pid, page_num=i, bbox=PanelBBox(x=0, y=0, width=16, height=16), image_path=rel
        )

    seen: list[int] = []

    class _Spy:
        def describe_panels(self, image_paths, prompt):
            seen.append(len(image_paths))
            return '{"unsupported": [], "severity": "none"}'

    monkeypatch.setattr(verify_mod, "get_stage_llm", lambda *a, **k: _Spy())
    monkeypatch.setattr(verify_mod, "apply_stage_model", lambda llm, *a, **k: llm)

    beat = ScriptBeat(beat_id=1, panel_ids=list(panels), narration="Half the chapter.")
    verify_mod.audit_frame_alignment([beat], panels, tmp_path, {})

    assert seen == [verify_mod._MAX_AUDIT_PANELS]


def test_single_beat_retry_path_is_callable(tmp_path) -> None:
    """The per-beat retry only runs when a chunk fails, so tests never reach it.

    A NameError there ('chunk' is not defined) silently lost beats 11-18 of a real run —
    the chunk failed, every retry then failed too, and only the beat-conservation gate
    caught it. Exercise the fallback directly.
    """
    from manhwa2vid.models import ChapterSynopsis, ScriptOutlineBeat
    from manhwa2vid.script.generate import _retry_single_beat

    class _LLM:
        def complete(self, system, user, *, json_mode=False):
            return '{"beats": [{"beat_id": 7, "narration": "He steps through the gate."}]}'

        def describe_panels(self, image_paths, prompt):
            return "{}"

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="Hero", tier=CharacterTier.MAIN
    )
    beat = ScriptOutlineBeat(beat_id=7, panel_ids=["p0007_01"], plot_beat="He enters.")

    out = _retry_single_beat(
        _LLM(), "system", _meta_stub(), beat, "hook", bible, [], ChapterSynopsis(), {}, None,
        introduced=[], running_summary=[], paths=None,
    )
    assert "gate" in out


def _meta_stub():
    from manhwa2vid.models import ProjectMeta, SourceLanguage

    return ProjectMeta(slug="s", title="S", chapters="1", source_lang=SourceLanguage.EN)


def test_enforce_reading_order_splits_interleaved_beats():
    """Observed on ch1: outline seeding produced beats whose panels straddled each other.

        beat 10: p0017_01, p0018_02, p0018_03
        beat 11: p0017_02, p0018_04

    Reading order is p0017_01, p0017_02, p0018_02, p0018_03, p0018_04, so beat 11
    narrated Jin-Woo asking for coffee AFTER beat 10 walked him away from the stall, and
    both beats narrated the refusal.
    """
    from manhwa2vid.models import ScriptOutlineBeat
    from manhwa2vid.script.grounding import enforce_reading_order

    beats = [
        ScriptOutlineBeat(beat_id=10, panel_ids=["p0017_01", "p0018_02", "p0018_03"], plot_beat="a", character_ids=[]),
        ScriptOutlineBeat(beat_id=11, panel_ids=["p0017_02", "p0018_04"], plot_beat="b", character_ids=[]),
    ]
    out = enforce_reading_order(beats)

    assert [b.panel_ids for b in out] == [
        ["p0017_01"],
        ["p0017_02", "p0018_02", "p0018_03", "p0018_04"],
    ]
    # Panel conservation is a hard gate: nothing may be dropped or duplicated.
    before = sorted(p for b in beats for p in b.panel_ids)
    after = sorted(p for b in out for p in b.panel_ids)
    assert before == after


def test_enforce_reading_order_never_empties_a_beat():
    """Emptying a beat fails beat conservation and kills the whole chapter.

    With fewer panels than beats no partition can give each beat a panel, so the repair
    must decline rather than emit an empty run.
    """
    from manhwa2vid.models import ScriptOutlineBeat
    from manhwa2vid.script.grounding import enforce_reading_order

    beats = [
        ScriptOutlineBeat(beat_id=1, panel_ids=["p0001_01", "p0001_02"], plot_beat="a", character_ids=[]),
        ScriptOutlineBeat(beat_id=2, panel_ids=["p0001_01"], plot_beat="b", character_ids=[]),
        ScriptOutlineBeat(beat_id=3, panel_ids=["p0001_02"], plot_beat="c", character_ids=[]),
    ]
    out = enforce_reading_order(beats)
    assert all(b.panel_ids for b in out), [b.panel_ids for b in out]


def test_enforce_reading_order_leaves_well_formed_outlines_alone():
    from manhwa2vid.models import ScriptOutlineBeat
    from manhwa2vid.script.grounding import enforce_reading_order

    beats = [
        ScriptOutlineBeat(beat_id=1, panel_ids=["p0001_01", "p0001_02"], plot_beat="a", character_ids=[]),
        ScriptOutlineBeat(beat_id=2, panel_ids=["p0002_01"], plot_beat="b", character_ids=[]),
    ]
    assert [b.panel_ids for b in enforce_reading_order(beats)] == [
        ["p0001_01", "p0001_02"],
        ["p0002_01"],
    ]
