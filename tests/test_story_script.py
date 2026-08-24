"""Story-first script helpers and lint tests."""

from __future__ import annotations

import re

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
    from manhwa2vid.script import grounding

    # The keyword pre-filter has no built-in list — it is per-series data, supplied here.
    grounding.configure_grounding_keywords(
        {"script": {"grounding_keywords": {"coffee": ["coffee", "barista", "cafe"]}}}
    )
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


def test_beat_budget_scales_with_chapter_count(tmp_path):
    """A fixed 18-beat cap met a 211-panel two-chapter project at 11.7 panels/beat and
    the audit rejected 13/18 beats. Beats derive from chapter count (data, not title)."""
    import json

    from manhwa2vid.models import ProjectMeta
    from manhwa2vid.script.generate import _chapter_count, _target_beat_count

    meta = ProjectMeta(slug="t", title="T", chapters="1-2", source_lang="en")
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "sources.json").write_text(json.dumps(
        [{"page_num": i, "chapter_num": 1 + (i > 11)} for i in range(1, 25)]
    ))
    paths = {"pages": pages}
    assert _chapter_count(meta, paths) == 2
    assert _target_beat_count(meta, paths, {}) == 28  # 14/chapter default

    # no sources.json -> parse the chapters string
    assert _chapter_count(meta, None) == 2
    ten = ProjectMeta(slug="t", title="T", chapters="1-10", source_lang="en")
    assert _target_beat_count(ten, None, {}) == 45    # clamped at max_beats cap
    one = ProjectMeta(slug="t", title="T", chapters="7", source_lang="en")
    assert _target_beat_count(one, None, {}) == 14


def test_inject_closer_evidence_pins_final_panel_content():
    """The synopsis compressed 'YOU ARE ABLE TO REMOVE THE SEAL' into its NEGATIVE and
    every downstream layer told the wrong ending. The final panels' text is quoted into
    the closer deterministically."""
    from manhwa2vid.models import SceneCard, ScriptOutlineBeat
    from manhwa2vid.script.grounding import inject_closer_evidence

    cards = [
        SceneCard(panel_ids=["p0001_01"], source_text='A: "HELLO."', action="a"),
        SceneCard(panel_ids=["p0024_01"], source_text='system: "[YOU ARE ABLE TO REMOVE THE SEAL.]"', action="b"),
        SceneCard(panel_ids=["p0024_03"], source_text='"WHAT?!"', action="c"),
    ]
    beats = [
        ScriptOutlineBeat(beat_id=1, panel_ids=["p0001_01"], plot_beat="opening", character_ids=[]),
        ScriptOutlineBeat(beat_id=2, panel_ids=["p0024_01", "p0024_03"], plot_beat="he fails to break the seal", character_ids=[], is_closer=True),
    ]
    out = inject_closer_evidence(beats, cards)
    assert "ABLE TO REMOVE THE SEAL" in out[1].plot_beat
    assert "WHAT?!" in out[1].plot_beat
    assert out[0].plot_beat == "opening"
    # idempotent — re-injection must not stack
    again = inject_closer_evidence(out, cards)
    assert again[1].plot_beat.count("CLOSER EVIDENCE") == 1


def test_closing_panel_terms_are_positional_not_series_specific():
    from manhwa2vid.models import SceneCard
    from manhwa2vid.script.generate import _closing_panel_terms

    cards = [SceneCard(panel_ids=[f"p{i:04d}_01"], source_text=f'X: "LINE {i}"', action="") for i in range(1, 9)]
    cards[-1] = SceneCard(panel_ids=["p0008_01"], source_text='sys: "[SEAL REMOVAL POSSIBLE.]"', action="")
    terms = _closing_panel_terms(cards)
    assert "seal" in terms and "removal" in terms and "possible" in terms


def test_key_panels_round_trip_through_draft_markdown():
    """The `| key:` extension of the load-bearing panels comment must survive the
    draft -> final -> beats round trip, and stray ids must not import."""
    from manhwa2vid.models import ScriptBeat, ScriptDraft
    from manhwa2vid.script.generate import _beats_to_markdown, _parse_markdown_beats

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


def test_truncation_reason_detects_both_tells():
    """The two independent signals that a narration response is not to be believed."""
    from manhwa2vid.script.generate import truncation_reason

    good = {"beats": [{"beat_id": 1, "narration": "a"}]}
    assert truncation_reason(good, "stop") == ""

    # provider says outright it ran out of budget
    assert "length" in truncation_reason(good, "length")

    # the real failure: salvage rescued ONE inner beat, no envelope. data["beats"] is
    # empty and 28 beats silently fell to per-beat mode for three runs.
    salvaged = {"beat_id": 1, "narration": "text", "key_panels": ["p1"]}
    assert "salvaged" in truncation_reason(salvaged, "stop")

    # a single-beat retry legitimately returns an envelope with one beat
    assert truncation_reason({"beats": [{"beat_id": 3, "narration": "x"}]}, "stop") == ""


def test_split_utterances_separates_monologue_from_speech():
    """The device is data, not a judgement call. Solo Leveling ch1 opens on Jin-Woo
    bleeding out alone while a caption carries his name and rank; every line went to the
    writer under one "SPOKEN" header and the narration had a dying man alone in a chamber
    "introducing himself as an E-rank hunter". A listener arrow decides this."""
    from manhwa2vid.script.grounding import split_utterances

    said, thought, unowned = split_utterances(
        'Sung Jin-Woo: "MY NAME IS SUNG JIN-WOO." / '
        'char_bak -> char_kim: "IT\'S BEEN A WHILE." / '
        '"THE WORLD\'S WEAKEST?"'
    )
    assert thought == ['Sung Jin-Woo: "MY NAME IS SUNG JIN-WOO."']
    assert said == ['char_bak -> char_kim: "IT\'S BEEN A WHILE."']
    assert unowned == ['"THE WORLD\'S WEAKEST?"']


def test_evidence_labels_monologue_distinctly():
    """The three headers must reach the prompt — a regression here is invisible in tests
    that only check that evidence is non-empty."""
    from manhwa2vid.script.grounding import evidence_for_panels

    card = SceneCard(
        panel_ids=["p0002_01"],
        action="The injured man lies on the ground.",
        source_text='Sung Jin-Woo: "MY NAME IS SUNG JIN-WOO."',
    )
    evid = evidence_for_panels(["p0002_01"], [card])
    assert "THINKS" in evid
    assert "SAYS ALOUD" not in evid


def test_lint_plot_coverage_catches_dropped_story():
    """The omission direction. This is Solo Leveling ch1 beat 8 verbatim: the outline
    named the two events that make the scene land, the narration described two men
    chatting instead, and every existing gate passed it because nothing it said was
    false."""
    from manhwa2vid.script.lint import lint_plot_coverage

    plot = {
        8: ("Sung Jin-Woo overhears them calling him the world's weakest hunter, before "
            "he tries to order a coffee only to find the vendor has run out."),
        3: "Sung Jin-Woo heads toward a glowing blue Gate at a construction site.",
    }
    beats = [
        ScriptBeat(beat_id=8, panel_ids=["p1"], narration=(
            "Kim Sangshik chuckles to Bak while walking with his warm drink. He tells Bak "
            "that the dungeon is bound to be weak today.")),
        ScriptBeat(beat_id=3, panel_ids=["p2"], narration=(
            "Sung Jin-Woo heads toward the glowing blue Gate looming over the construction "
            "site.")),
    ]
    flagged = lint_plot_coverage(beats, plot)
    assert 8 in flagged and 3 not in flagged
    assert "coffee" in flagged[8][0]


def test_lint_plot_coverage_ignores_empty_plot_beats():
    """Continuity beats legitimately carry no plot_beat; scoring them would flag every
    one of them forever."""
    from manhwa2vid.script.lint import lint_plot_coverage

    beats = [ScriptBeat(beat_id=1, panel_ids=["p1"], narration="He walks on.")]
    assert lint_plot_coverage(beats, {1: ""}) == {}


def test_lint_dropped_dialogue_catches_a_missed_system_message():
    """Frozen Player's central reveal sat verbatim in the card and the narration
    described the hero's expression instead — narrated, not curated out, just skipped."""
    from manhwa2vid.script.lint import lint_dropped_dialogue

    cards = [
        SceneCard(
            panel_ids=["p0011_02"],
            action="his eyes widen",
            source_text='system: "[YOU HAVE COMPLETELY ABSORBED THE FROST QUEEN\'S NUCLEUS.]"',
        ),
    ]
    beats = [
        ScriptBeat(
            beat_id=1,
            panel_ids=["p0011_02"],
            narration="His expression shifts as something changes within him.",
        ),
    ]
    flagged = lint_dropped_dialogue(beats, cards)
    assert 1 in flagged
    assert "NUCLEUS" in flagged[1][0]


def test_lint_dropped_dialogue_passes_when_the_line_lands():
    from manhwa2vid.script.lint import lint_dropped_dialogue

    cards = [
        SceneCard(
            panel_ids=["p0011_02"],
            action="his eyes widen",
            source_text='system: "[YOU HAVE COMPLETELY ABSORBED THE FROST QUEEN\'S NUCLEUS.]"',
        ),
    ]
    beats = [
        ScriptBeat(
            beat_id=1,
            panel_ids=["p0011_02"],
            narration="A message flashes before him: he has fully absorbed the Frost Queen's nucleus.",
        ),
    ]
    assert lint_dropped_dialogue(beats, cards) == {}


def test_lint_dropped_dialogue_ignores_short_exclamations():
    """A bare "WHAT?!" carries no payoff — flagging it would only add noise."""
    from manhwa2vid.script.lint import lint_dropped_dialogue

    cards = [SceneCard(panel_ids=["p1"], action="he recoils", source_text='"WHAT?!"')]
    beats = [ScriptBeat(beat_id=1, panel_ids=["p1"], narration="He staggers back.")]
    assert lint_dropped_dialogue(beats, cards) == {}


def test_lint_dropped_dialogue_ranks_and_caps_multiple_dropped_lines():
    """A beat with four dropped lines given four co-equal demands lands none of them
    (measured). Capping forces the rewrite to spend its budget on the highest-value
    lines: a bracketed system message first, then a line carrying a concrete number."""
    from manhwa2vid.script.lint import lint_dropped_dialogue

    cards = [
        SceneCard(panel_ids=["p1"], action="", source_text='Rell: "IT IS A NICE DAY OUTSIDE TODAY."'),
        SceneCard(panel_ids=["p2"], action="", source_text='Vesh: "THERE ARE TEN TOTAL FLOORS IN THE TOWER."'),
        SceneCard(panel_ids=["p3"], action="", source_text='system: "[YOU HAVE ABSORBED THE CORE.]"'),
    ]
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1", "p2", "p3"], narration="Nothing here lands any of it."),
    ]
    flagged = lint_dropped_dialogue(beats, cards, max_lines_per_beat=2)
    assert len(flagged[1]) == 2
    # The bracketed system message and the numeric fact outrank the plain color line.
    joined = " ".join(flagged[1])
    assert "ABSORBED THE CORE" in joined
    assert "TEN TOTAL FLOORS" in joined
    assert "NICE DAY" not in joined


def test_refresh_plot_for_span_describes_the_whole_span():
    """enforce_reading_order gives a beat "everything from its own anchor up to the next
    beat's", so a beat can hold panels its plot_beat never described — and once plot_beat
    became the MUST COVER spine, a plot describing the TAIL made the writer narrate the
    end first. ch1 beat 12 shipped its five panels reversed."""
    from manhwa2vid.models import ScriptOutlineBeat
    from manhwa2vid.script.grounding import refresh_plot_for_span

    cards = [
        SceneCard(panel_ids=["p1"], action="Rell smiles weakly while explaining himself",
                  source_text='Rell -> Vesh: "IT IS ONLY BECAUSE I AM WEAK."'),
        SceneCard(panel_ids=["p2"], action="Vesh looks back in silence", source_text=""),
        SceneCard(panel_ids=["p3"], action="Doran addresses the gathered party",
                  source_text='Doran -> the party: "I WILL TAKE THE LEAD TODAY."'),
    ]
    beats = [ScriptOutlineBeat(
        beat_id=1, panel_ids=["p1", "p2", "p3"],
        plot_beat="Doran addresses the gathered party and offers to take the lead today.")]
    out = refresh_plot_for_span(beats, cards)
    assert out[0].plot_beat.startswith("Rell smiles weakly while explaining himself")
    assert "Doran addresses" in out[0].plot_beat      # the seed survives, it is prepended to


def test_refresh_plot_for_span_leaves_a_head_aligned_beat_alone():
    """Only ever prepends, and only for a beat whose plot demonstrably describes its
    tail — a plot already covering the head must be untouched."""
    from manhwa2vid.models import ScriptOutlineBeat
    from manhwa2vid.script.grounding import refresh_plot_for_span

    cards = [
        SceneCard(panel_ids=["p1"], action="Rell boards the ferry",
                  source_text='Rell -> Vesh: "WE LEAVE BEFORE THE TIDE TURNS."'),
        SceneCard(panel_ids=["p2"], action="the harbour shrinks behind them", source_text=""),
    ]
    beats = [ScriptOutlineBeat(
        beat_id=1, panel_ids=["p1", "p2"],
        plot_beat="Rell boards the ferry and tells Vesh they leave before the tide turns.")]
    assert refresh_plot_for_span(beats, cards)[0].plot_beat == beats[0].plot_beat


def _fp_beat11_cards() -> list[SceneCard]:
    """Frozen Player beat 11 verbatim: the chapter's awakening, printed on the panels."""
    return [
        SceneCard(panel_ids=["p0009_08"], action="a boy points", source_text='the boy: "THE ICE STATUE JUST MOVED."'),
        SceneCard(panel_ids=["p0010_04"], action="she dismisses him", source_text='the presenter: "I\'M SORRY, THAT\'S INCORRECT."'),
        SceneCard(panel_ids=["p0011_02"], action="a notification", source_text='"[YOU HAVE COMPLETELY ABSORBED THE FROST QUEEN\'S NUCLEUS.]"'),
        SceneCard(panel_ids=["p0011_03"], action="another notification", source_text='"[YOU HAVE RECEIVED THE NEW SKILL FROST(EX).]"'),
    ]


def test_required_lines_prioritise_system_messages_but_keep_panel_order():
    """Selected by priority, presented in reading order — so this never fights the
    'narrate panels in the order the evidence lists them' rule."""
    from manhwa2vid.script.lint import required_lines_for_beat

    cards = _fp_beat11_cards()
    panels = ["p0009_08", "p0010_04", "p0011_02", "p0011_03"]
    out = required_lines_for_beat(panels, cards, {}, max_words=60)
    assert any("NUCLEUS" in ln for ln in out)
    assert any("FROST(EX)" in ln for ln in out)
    # Panel order, not priority order: the boy's line precedes the system messages.
    assert out == sorted(out, key=lambda ln: [i for i, c in enumerate(cards) if ln in (c.source_text or "")][0])


def test_required_lines_cap_to_what_the_word_budget_can_hold():
    """A beat cannot be asked to land more lines than its cap has words for — that is
    how you get four flat 'he says X, it says Y' sentences and no story."""
    from manhwa2vid.script.lint import required_lines_for_beat

    cards = _fp_beat11_cards()
    panels = ["p0009_08", "p0010_04", "p0011_02", "p0011_03"]
    # 10 words of the cap are reserved for framing, so a 20-word beat carries one line.
    assert len(required_lines_for_beat(panels, cards, {}, max_words=20)) == 1
    assert len(required_lines_for_beat(panels, cards, {}, max_words=40)) == 3
    # The highest-priority line survives the tightest budget, and a narrow beat is never
    # excused from its single most important line.
    assert "[" in required_lines_for_beat(panels, cards, {}, max_words=10)[0]
    assert len(required_lines_for_beat(panels, cards, {}, max_words=10)) == 1
    # Never more than the hard cap even with a huge budget.
    assert len(required_lines_for_beat(panels, cards, {}, max_words=500)) <= 4


def test_beat_block_puts_required_lines_under_must_cover():
    """The fix for the worst observed defect: beat 11 narrated the bystander and omitted
    the hero bursting out of the ice, because the prompt classed a printed system message
    as optional DETAIL while only plot_beat was mandatory."""
    from manhwa2vid.models import ScriptOutlineBeat, SeriesBible
    from manhwa2vid.script.generate import _cast_context_for_beats

    cards = _fp_beat11_cards()
    beat = ScriptOutlineBeat(
        beat_id=11,
        panel_ids=["p0009_08", "p0010_04", "p0011_02", "p0011_03"],
        plot_beat="A boy points at the stage.",
    )
    block = _cast_context_for_beats(
        [beat], [], SeriesBible(series_slug="s", title="S"), cards,
        _cap_config={}, n_beats_total=26, n_chapters=2,
    )
    assert "REQUIRED LINES" in block
    assert "NUCLEUS" in block
    # Promoted ABOVE the evidence block, i.e. onto the MUST COVER side.
    assert block.index("REQUIRED LINES") < block.index("EVIDENCE")
    assert block.index("MUST COVER") < block.index("REQUIRED LINES")


def test_beat_block_omits_required_lines_when_panels_print_nothing():
    from manhwa2vid.models import ScriptOutlineBeat, SeriesBible
    from manhwa2vid.script.generate import _cast_context_for_beats

    cards = [SceneCard(panel_ids=["p1"], action="he walks on", source_text="")]
    beat = ScriptOutlineBeat(beat_id=1, panel_ids=["p1"], plot_beat="He walks on.")
    block = _cast_context_for_beats(
        [beat], [], SeriesBible(series_slug="s", title="S"), cards,
        _cap_config={}, n_beats_total=10, n_chapters=1,
    )
    assert "REQUIRED LINES" not in block


def test_required_lines_are_not_demanded_twice_across_beats():
    """The same line required in two beats would collide with rule 7's ONCE-ONLY."""
    from manhwa2vid.models import ScriptOutlineBeat, SeriesBible
    from manhwa2vid.script.generate import _cast_context_for_beats

    card = SceneCard(panel_ids=["pA", "pB"], action="x", source_text='system: "[YOU HAVE ABSORBED THE CORE.]"')
    beats = [
        ScriptOutlineBeat(beat_id=1, panel_ids=["pA"], plot_beat="first"),
        ScriptOutlineBeat(beat_id=2, panel_ids=["pB"], plot_beat="second"),
    ]
    block = _cast_context_for_beats(
        beats, [], SeriesBible(series_slug="s", title="S"), [card],
        _cap_config={}, n_beats_total=10, n_chapters=1,
    )
    # Required exactly once. It still appears in BOTH beats' EVIDENCE blocks, which is
    # deliberate — the SAYS ALOUD / THINKS header there is what tells the writer how to
    # voice it — so count only the REQUIRED LINES sections.
    required_sections = re.findall(r"REQUIRED LINES.*?(?=  MAX )", block, re.S)
    assert sum(sec.count("[YOU HAVE ABSORBED THE CORE.]") for sec in required_sections) == 1


def test_quoted_lines_survive_a_single_character_utterance():
    """The alternating-quote bug, verbatim from p0023_13. A bare "?" is too short to
    match, so a whole-blob scan paired the quote CLOSING it with the quote OPENING the
    next line: it returned four copies of " / system -> Seo Jun-Ho: " and silently lost
    three real system messages, including the chapter's ending. Those artifacts then
    occupied required-line slots that could never be satisfied, while the genuine lines
    were never asked for at all."""
    from manhwa2vid.script.grounding import quoted_lines_for_panels

    cards = [
        SceneCard(
            panel_ids=["p0023_13"],
            action="he touches the statue",
            source_text=(
                'system -> Seo Jun-Ho: "[CONFIRMED POSSESSION OF THE SKILL FROST(EX).]" / '
                'Seo Jun-Ho: "?" / '
                'system -> Seo Jun-Ho: "[INSUFFICIENT MAGIC STATS.]" / '
                'system -> Seo Jun-Ho: "[YOU HAVE FAILED AT REMOVING THE SEAL.]"'
            ),
        ),
    ]
    lines = quoted_lines_for_panels(["p0023_13"], cards)
    assert any("CONFIRMED POSSESSION" in ln for ln in lines)
    assert any("FAILED AT REMOVING THE SEAL" in ln for ln in lines)
    assert not any("Seo Jun-Ho:" in ln for ln in lines), "speaker prefixes are not lines"
    assert not any(ln.strip().startswith("/") for ln in lines)


def test_required_lines_reserve_room_for_framing():
    """A beat asked for exactly as many lines as its cap has words has nothing left to
    connect them with. FP beat 21 was one panel, cap 30, three lines at 10 words each —
    no subject, no speaker, no consequence — and landed two of the three."""
    from manhwa2vid.script.lint import required_lines_for_beat

    cards = [
        SceneCard(
            panel_ids=["p1"],
            action="he explains",
            source_text=(
                'Deok-gu: "ONLY PLAYERS WHO RESIST THE HEAT CAN EXPLORE THERE." / '
                'Deok-gu: "WE FOUND AN ALTAR IN THE MIDDLE OF THE SEA OF LAVA." / '
                'Deok-gu: "THAT ALTAR REQUIRES [THE FROST QUEEN\'S NUCLEUS] TO COOL IT."'
            ),
        ),
    ]
    # 30-word cap: 10 reserved for framing leaves room for two lines, not three.
    assert len(required_lines_for_beat(["p1"], cards, {}, max_words=30)) == 2
    # A wider beat can still carry all three.
    assert len(required_lines_for_beat(["p1"], cards, {}, max_words=60)) == 3
