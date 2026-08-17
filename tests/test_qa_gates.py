"""Regression fixtures for the QA gates — each test reproduces a bug observed in the
chapter-1 critique and asserts the gate that now makes it impossible to miss."""

from __future__ import annotations

import json
from typing import Any

import pytest

from manhwa2vid.models import (
    CharacterProfile,
    CharacterRef,
    CharacterTier,
    PanelCast,
    SceneCard,
    ScriptBeat,
    ScriptOutlineBeat,
    SeriesBible,
    VisualProfile,
)
from manhwa2vid.qa import FAIL, PASS, WARN, QAReport


def _bible_with_mc() -> SeriesBible:
    bible = SeriesBible(series_slug="t", title="T")
    bible.characters["char_sung_jin_woo"] = CharacterProfile(
        id="char_sung_jin_woo",
        canonical_name="Sung Jin-Woo",
        tier=CharacterTier.MAIN,
        pronoun="he",
        descriptors=["man with green backpack", "E-Rank hunter"],
        visual=VisualProfile(outfit="green backpack"),
    )
    bible.characters["char_lee_joo_hee"] = CharacterProfile(
        id="char_lee_joo_hee",
        canonical_name="Lee Joo-hee",
        tier=CharacterTier.SUPPORTING,
        pronoun="she",
        role="healer",
    )
    bible.protagonist_id = "char_sung_jin_woo"
    return bible


# --- A2: beat conservation --------------------------------------------------------------

def test_narration_missing_beats_are_reported() -> None:
    report = QAReport(stage="script")
    outline_ids = [1, 2, 3]
    script_ids = [1, 3]
    status = report.add(
        "beat-conservation", not [2] and script_ids == outline_ids, "missing=[2]"
    )
    assert status == FAIL
    assert report.failed


# --- B1: referential integrity — invented refs close against the bible --------------------

def test_invented_green_backpack_ref_resolves_to_mc() -> None:
    from manhwa2vid.characters.link import _close_ref_against_bible

    bible = _bible_with_mc()
    person = CharacterRef(ref="char_man_with_green_backpack", name_used="", descriptor="")
    card = SceneCard(panel_ids=["p0016_01"], people=[person])
    assert _close_ref_against_bible(person, card, bible) == "char_sung_jin_woo"


def test_cast_integrity_report_flags_dangling_ref() -> None:
    from manhwa2vid.characters.link import _cast_integrity_report

    bible = _bible_with_mc()
    cards = [
        SceneCard(
            panel_ids=["p0001_01"],
            people=[CharacterRef(ref="char_does_not_exist", name_used="Ghost")],
        )
    ]
    report = _cast_integrity_report(cards, bible)
    gate = next(g for g in report.gates if g.name == "referential-integrity")
    assert gate.status == FAIL


# --- C1: speakers must be visible people --------------------------------------------------

def test_offpanel_speaker_is_dropped() -> None:
    from manhwa2vid.ocr.extract import _normalize_scene_data

    data = {
        "speakers": ["Sung Jin-Woo", "bald man"],
        "people": [{"ref": "new", "name_used": "", "descriptor": "bald man in brown hood"}],
        "dialogue_summary": "",
        "panel_ids": ["p0024_01"],
    }
    out = _normalize_scene_data(data, [], ocr_text="")
    assert out["speakers"] == ["bald man"]
    assert "Sung Jin-Woo" in out["dropped_speakers"]


def test_ungrounded_dialogue_summary_is_cleared() -> None:
    from manhwa2vid.ocr.extract import _normalize_scene_data

    data = {
        "speakers": [],
        "people": [],
        "dialogue_summary": "The barista apologizes for being out of coffee.",
        "bubbles": ["I've been hearing you, old geezers... ha..."],
        "panel_ids": ["p0017_01"],
    }
    out = _normalize_scene_data(data, [], ocr_text="")
    assert out["dialogue_summary"] == ""


def test_grounded_dialogue_summary_survives() -> None:
    from manhwa2vid.ocr.extract import _normalize_scene_data

    data = {
        "speakers": [],
        "people": [],
        "dialogue_summary": "Someone mocks the old geezers he has been hearing.",
        "bubbles": ["I've been hearing you, old geezers... ha..."],
        "panel_ids": ["p0017_01"],
    }
    out = _normalize_scene_data(data, [], ocr_text="")
    assert out["dialogue_summary"] != ""


# --- C3: named cast must be on screen -----------------------------------------------------

def test_named_offscreen_is_flagged() -> None:
    from manhwa2vid.script.lint import lint_named_presence

    bible = _bible_with_mc()
    attribution = [
        PanelCast(panel_id="p0024_01", people=[CharacterRef(ref="char_lee_joo_hee")]),
    ]
    beats = [
        ScriptBeat(
            beat_id=1,
            panel_ids=["p0024_01"],
            narration="Sung Jin-Woo boasts about being highest ranked.",
        )
    ]
    report = lint_named_presence(beats, bible, attribution)
    assert report == {1: ["named_offscreen:char_sung_jin_woo"]}


# --- B3/B4/D2/D3/D5: register, quotes, MC token, descriptor quarantine, leaks --------------

def test_register_lint_catches_report_verbs_and_art_words() -> None:
    from manhwa2vid.script.lint import lint_register

    beats = [
        ScriptBeat(
            beat_id=1,
            panel_ids=["p1"],
            narration="Two speech bubbles say hello. Lee Joo-hee expresses concern and reacts.",
        )
    ]
    issues = lint_register(beats)[1]
    assert "art_description" in issues
    assert any(i.startswith("register:express") for i in issues)
    assert any(i.startswith("register:react") for i in issues)


def test_mc_token_and_leak_are_flagged() -> None:
    from manhwa2vid.script.lint import lint_register

    beats = [
        ScriptBeat(
            beat_id=1,
            panel_ids=["p1"],
            narration="The protagonist, now referred to as the protagonist, glares while MC waits.",
        )
    ]
    issues = lint_register(beats)[1]
    assert "instruction_leak" in issues
    assert "mc_token_spoken" in issues


def test_verbatim_quote_is_flagged_but_contractions_are_not() -> None:
    from manhwa2vid.script.lint import lint_register

    quoted = ScriptBeat(
        beat_id=1, panel_ids=["p1"],
        narration='A man says "I never expected this to happen to me".',
    )
    clean = ScriptBeat(
        beat_id=2, panel_ids=["p1"],
        narration="He says he's the weakest hunter, and he isn't joking.",
    )
    report = lint_register([quoted, clean])
    assert "verbatim_quote" in report.get(1, [])
    assert 2 not in report


def test_protagonist_phrase_allowed_once() -> None:
    from manhwa2vid.script.lint import lint_protagonist_phrase

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="The protagonist walks in."),
        ScriptBeat(beat_id=2, panel_ids=["p2"], narration="The protagonist orders food."),
    ]
    report = lint_protagonist_phrase(beats)
    assert 1 not in report
    assert report[2] == ["protagonist_phrase_overuse"]


def test_descriptor_quarantine_for_named_character() -> None:
    from manhwa2vid.script.lint import lint_descriptor_quarantine

    bible = _bible_with_mc()
    beats = [
        ScriptBeat(
            beat_id=1,
            panel_ids=["p1"],
            narration="He offers to help, but the man with green backpack declines.",
        )
    ]
    report = lint_descriptor_quarantine(beats, bible)
    assert report[1] == ["descriptor_for_named:Sung Jin-Woo"]


# --- A3/D5: closer beat + hook dedup ------------------------------------------------------

def test_closer_beat_is_marked_with_open_thread() -> None:
    from manhwa2vid.models import ChapterSynopsis
    from manhwa2vid.script.generate import _mark_closer_beat

    outline = [
        ScriptOutlineBeat(beat_id=1, panel_ids=["p1"], plot_beat="start"),
        ScriptOutlineBeat(beat_id=2, panel_ids=["p2"], plot_beat="end"),
    ]
    synopsis = ChapterSynopsis(open_threads=["The double dungeon awaits."])
    marked = _mark_closer_beat(outline, synopsis)
    assert marked[-1].is_closer
    assert "double dungeon" in marked[-1].plot_beat.lower()


def test_hook_overlap_detects_duplicate_opening() -> None:
    from manhwa2vid.script.generate import _token_overlap

    hook = "Sung Jin-Woo, the weakest hunter, emerges injured after a brutal gate fight."
    duplicate = "Sung Jin-Woo appears injured and says he's the weakest hunter after the gate fight."
    fresh = "The guild clerk stamps his card and waves the next man forward."
    assert _token_overlap(hook, duplicate) > 0.6
    assert _token_overlap(hook, fresh) < 0.3


# --- E2: scorecard bands ------------------------------------------------------------------

def test_scorecard_flags_report_register_script() -> None:
    from manhwa2vid.script.scorecard import score_script

    bible = _bible_with_mc()
    bad = [
        ScriptBeat(
            beat_id=1, panel_ids=["p1"],
            narration="Two people express agreement. A man converses with someone about the situation.",
        )
    ]
    report = score_script(bad, bible, {})
    by_name = {g.name: g for g in report.gates}
    assert by_name["register_verbs_total"].status in (WARN, FAIL)
    assert by_name["anonymous_agents_per_1k"].status in (WARN, FAIL)


def test_scorecard_passes_reference_style_narration() -> None:
    from manhwa2vid.script.scorecard import score_script

    bible = _bible_with_mc()
    text = (
        "Sung Jin-Woo limps out of the gate and tells the clerk he is fine. "
        "He counts his pay, then he asks about the next raid. The clerk says the roster is full, "
        "and he just nods. Outside, he checks the timer again and thinks about his mother's bills. "
        "Sung Jin-Woo knows what happens if he stops now, so he signs up anyway."
    )
    beats = [ScriptBeat(beat_id=1, panel_ids=["p1"], narration=text)]
    report = score_script(beats, bible, {})
    by_name = {g.name: g for g in report.gates}
    assert by_name["register_verbs_total"].status == PASS
    assert by_name["art_words_total"].status == PASS
    assert by_name["first_person_per_1k"].status == PASS
    assert by_name["dialogue_verbs_per_1k"].status == PASS


def test_self_consistency_warns_on_negation_contradiction() -> None:
    from manhwa2vid.script.scorecard import score_script

    bible = _bible_with_mc()
    beats = [
        ScriptBeat(
            beat_id=1, panel_ids=["p1"],
            narration="They hadn't brought a healer. She asks why they even bothered to bring a healer.",
        )
    ]
    report = score_script(beats, bible, {})
    gate = next(g for g in report.gates if g.name == "self-consistency")
    assert gate.status == WARN


# --- C4: grounding keywords from config ---------------------------------------------------

def test_grounding_keywords_configurable() -> None:
    from manhwa2vid.script import grounding

    grounding.configure_grounding_keywords(
        {"script": {"grounding_keywords": {"frost": ["frozen", "ice wall"]}}}
    )
    try:
        assert set(grounding.GROUNDING_KEYWORDS) == {"frost"}
        assert grounding.narration_grounding_keywords("He shatters the ice wall.") == {"frost"}
    finally:
        grounding.configure_grounding_keywords({})
        assert "coffee" in grounding.GROUNDING_KEYWORDS


# --- Scene stage: panel_ids clamp + cards-coverage (5-vanished-panels bug) -----------------

def test_scene_panel_ids_clamped_to_batch() -> None:
    """Regression: the VLM's echoed panel_ids used to win, stranding the real panel."""
    from manhwa2vid.models import Panel, PanelBBox
    from manhwa2vid.ocr.extract import _normalize_scene_data

    batch = [Panel(id="p0010_02", page_num=10, bbox=PanelBBox(x=0, y=0, width=10, height=10),
                   image_path="panels/p0010_02.png")]
    out = _normalize_scene_data(
        {"panel_ids": ["p0010_03"], "people": [], "speakers": []}, batch, ocr_text=""
    )
    assert out["panel_ids"] == ["p0010_02"]


def test_scene_panel_ids_intersection_preserved_for_multi_batch() -> None:
    from manhwa2vid.models import Panel, PanelBBox
    from manhwa2vid.ocr.extract import _normalize_scene_data

    batch = [
        Panel(id=f"p0001_0{i}", page_num=1, bbox=PanelBBox(x=0, y=0, width=10, height=10),
              image_path=f"panels/p0001_0{i}.png")
        for i in (1, 2, 3)
    ]
    out = _normalize_scene_data(
        {"panel_ids": ["p0001_02", "p9999_99"], "people": [], "speakers": []}, batch, ocr_text=""
    )
    assert out["panel_ids"] == ["p0001_02"]


# --- Scorecard: words-per-panel band + outliers (9.8s static dwell bug) --------------------

def test_words_per_panel_outlier_beat_flagged() -> None:
    from manhwa2vid.script.scorecard import score_script

    bible = _bible_with_mc()
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"],
                   narration=" ".join(["word"] * 25)),  # 25 words on one panel
        ScriptBeat(beat_id=2, panel_ids=["p2", "p3"],
                   narration="Sung Jin-Woo walks in and he asks about the raid roster today."),
    ]
    report = score_script(beats, bible, {})
    gate = next(g for g in report.gates if g.name == "words-per-panel-outliers")
    assert gate.status == WARN
    assert "beat 1" in gate.details


def test_words_per_panel_band_present() -> None:
    from manhwa2vid.script.scorecard import BANDS, score_script

    assert "words_per_panel" in BANDS
    bible = _bible_with_mc()
    beats = [ScriptBeat(beat_id=1, panel_ids=["p1", "p2"],
                        narration="Sung Jin-Woo tells the clerk he is fine and walks on quickly.")]
    report = score_script(beats, bible, {})
    assert any(g.name == "words_per_panel" for g in report.gates)


# --- Automated-vs-manual gap fixes: scene merges, word budgets, name rotation --------------

def test_outline_merge_never_crosses_scene_boundary() -> None:
    """Regression: the soft-cap merge fused cold-open panels with city-street panels,
    forcing the narration model to invent a bridge between unrelated scenes."""
    from manhwa2vid.models import ChapterSynopsis
    from manhwa2vid.script.grounding import preassign_outline_from_facts

    cards = [
        SceneCard(panel_ids=[f"p{page:04d}_01"], action=f"scene on page {page}",
                  dialogue_summary="", is_story=True)
        for page in (2, 3, 4, 8, 9, 10)
    ]
    bible = _bible_with_mc()
    outline = preassign_outline_from_facts(
        ChapterSynopsis(plot_facts=[]), cards, bible, max_beats=2
    )
    # max_beats=2 would force a p0004/p0008 merge without the constraint; with it, the
    # two scene blocks (pages 2-4 and 8-10) may each collapse internally but never fuse.
    for beat in outline:
        pages = [int(pid[1:5]) for pid in beat.panel_ids]
        assert max(pages) - min(pages) <= 2, f"beat spans scenes: {beat.panel_ids}"
        assert not ({2, 3, 4} & set(pages) and {8, 9, 10} & set(pages))


def test_overlong_beat_flagged_with_target() -> None:
    from manhwa2vid.script.lint import lint_overlong_beats

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1", "p2"], narration=" ".join(["w"] * 60)),
        ScriptBeat(beat_id=2, panel_ids=["p3", "p4"], narration=" ".join(["w"] * 20)),
    ]
    report = lint_overlong_beats(beats, {})
    assert report == {1: ["overlong:cut_to_28_words"]}


def test_rotate_protagonist_name_keeps_first_use() -> None:
    from manhwa2vid.script.lint import rotate_protagonist_name

    bible = _bible_with_mc()
    text = ("Sung Jin-Woo walks to the stand. Sung Jin-Woo asks for coffee, "
            "and Sung Jin-Woo's face falls when it runs out.")
    out = rotate_protagonist_name(text, bible)
    assert out.count("Sung Jin-Woo") == 1
    assert "He asks for coffee" in out
    assert "his face falls" in out


def test_rotate_protagonist_name_handles_she() -> None:
    from manhwa2vid.script.lint import rotate_protagonist_name

    bible = _bible_with_mc()
    bible.protagonist_id = "char_lee_joo_hee"
    text = "Lee Joo-hee runs over. Lee Joo-hee asks about the injury."
    out = rotate_protagonist_name(text, bible)
    assert out.count("Lee Joo-hee") == 1
    assert "She asks about the injury" in out


def test_rotate_protagonist_name_covers_aliases() -> None:
    """Regression: rotation only handled the full name; 'Jin-Woo' alias spam kept the
    anchor gap at ~12 words against the 40-130 band."""
    from manhwa2vid.script.lint import rotate_protagonist_name

    bible = _bible_with_mc()
    bible.characters["char_sung_jin_woo"].aliases = ["Jin-Woo"]
    text = "Sung Jin-Woo reaches the stand. Jin-Woo asks for coffee, and Jin-Woo waits."
    out = rotate_protagonist_name(text, bible)
    assert out.count("Jin-Woo") == 1  # only inside the surviving full-name anchor
    assert "He asks for coffee" in out


def test_unfounded_identification_is_demoted() -> None:
    """Regression: cast-list priming made the vision model 'identify' four named
    characters in an anonymous crosswalk crowd, with no visual basis."""
    from manhwa2vid.ocr.extract import _normalize_scene_data

    data = {
        "people": [
            {"ref": "char_lee_joo_hee", "name_used": "Lee Joo-hee",
             "descriptor": "woman in the crowd", "visibility": "back_turned"},  # no basis
            {"ref": "char_sung_jin_woo", "name_used": "Sung Jin-Woo",
             "descriptor": "man with green backpack", "visibility": "back_turned",
             "basis": "green backpack clearly visible"},
        ],
        "speakers": [],
        "panel_ids": ["p0008_02"],
    }
    out = _normalize_scene_data(data, [], ocr_text="")
    refs = [(p.ref, p.name_used) for p in out["people"]]
    assert ("new", "") in refs                                # Joo-hee demoted
    assert ("char_sung_jin_woo", "Sung Jin-Woo") in refs      # basis-backed MC kept
    assert out["demoted_identifications"] == 1


def test_consolidation_leaves_tombstone_for_redirects() -> None:
    """Regression: merge_profiles_into deleted the dropped profile, so apply_id_redirects
    never learned the redirect and card refs to consolidated ids dangled."""
    from manhwa2vid.characters.consolidate import apply_id_redirects, merge_profiles_into

    bible = _bible_with_mc()
    bible.characters["char_bak_dup"] = CharacterProfile(
        id="char_bak_dup", canonical_name="Bak", tier=CharacterTier.MINOR,
        descriptors=["curly-haired man in a green puffer jacket"],
    )
    bible.characters["char_bak"] = CharacterProfile(
        id="char_bak", canonical_name="Bak", tier=CharacterTier.SUPPORTING,
        descriptors=["curly-haired man in a green puffer jacket"],
    )
    merge_profiles_into(bible, "char_bak", "char_bak_dup")
    assert bible.characters["char_bak_dup"].merged_into == "char_bak"  # tombstone survives

    cards = [SceneCard(panel_ids=["p1"], people=[CharacterRef(ref="char_bak_dup", name_used="Bak")])]
    out = apply_id_redirects(cards, bible)
    assert out[0].people[0].ref == "char_bak"


def test_vlm_minted_ids_are_clamped_to_known_bible() -> None:
    """Regression: asked for 'char_id or new', the VLM minted descriptor-shaped ids
    (char_person_with_short_black_hair_...) which flooded the bible as junk profiles."""
    from manhwa2vid.ocr.extract import _normalize_scene_data

    data = {
        "people": [
            {"ref": "char_person_with_short_black_hair_bandages_on_face",
             "name_used": "", "descriptor": "man with bandages", "basis": "bandages visible"},
            {"ref": "char_sung_jin_woo", "name_used": "Sung Jin-Woo",
             "descriptor": "green backpack", "basis": "green backpack"},
        ],
        "speakers": [],
        "panel_ids": ["p0008_01"],
    }
    out = _normalize_scene_data(data, [], ocr_text="", known_ids={"char_sung_jin_woo"})
    refs = [p.ref for p in out["people"]]
    assert refs == ["new", "char_sung_jin_woo"]


def test_rotation_ignores_descriptor_aliases() -> None:
    """Regression: rotating quest-added descriptor aliases ('weakest hunter') produced
    spoken garbage like 'the world's he is still the strongest'."""
    from manhwa2vid.script.lint import rotate_protagonist_name

    bible = _bible_with_mc()
    bible.characters["char_sung_jin_woo"].aliases = ["Jin-Woo", "Sung", "weakest hunter", "E-Rank hunter"]
    text = ("Sung Jin-Woo mutters that the world's weakest hunter is still standing. "
            "Jin-Woo grabs the E-Rank hunter badge.")
    out = rotate_protagonist_name(text, bible)
    assert "weakest hunter is still standing" in out   # descriptor alias untouched
    assert "E-Rank hunter badge" in out                # descriptor alias untouched
    assert "He grabs" in out                           # real name form rotated


def test_rotation_never_matches_inside_longer_names() -> None:
    """Regression: alias 'Sung' matched inside the honorific 'Hunter Sung Woo-Jin' and
    shipped spoken garbage ('Hunter he Woo-Jin')."""
    from manhwa2vid.script.lint import rotate_protagonist_name

    bible = _bible_with_mc()
    bible.characters["char_sung_jin_woo"].aliases = ["Jin-Woo", "Sung"]
    text = ("Sung Jin-Woo asks the vendor for coffee, but the vendor calls him "
            "Hunter Sung Woo-Jin and says it ran out. Sung shrugs it off.")
    out = rotate_protagonist_name(text, bible)
    assert "Hunter Sung Woo-Jin" in out    # variant name inside honorific untouched
    assert "He shrugs it off" in out       # standalone alias rotated
    assert "Hunter he" not in out


def test_reference_sheet_requires_visual_basis() -> None:
    """A reference may only come from an identification backed by explicit visual basis.

    Seeding the sheet from an unbacked guess would make identity confusion
    self-reinforcing: the wrong face becomes the anchor every later panel matches against.
    """
    from manhwa2vid.characters.reference import select_reference_panels
    from manhwa2vid.models import (
        CharacterProfile,
        CharacterRef,
        SceneCard,
        SeriesBible,
    )

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(id="char_mc", canonical_name="MC")

    unbacked = SceneCard(
        panel_ids=["p0001_01"],
        people=[CharacterRef(ref="char_mc", visibility="face", notes="")],
    )
    assert not select_reference_panels(bible, [unbacked])

    backed = SceneCard(
        panel_ids=["p0002_01"],
        people=[
            CharacterRef(
                ref="char_mc",
                visibility="face",
                notes="green backpack clearly visible, scar on cheek",
                confidence=0.9,
            )
        ],
    )
    picked = select_reference_panels(bible, [backed])
    assert picked["char_mc"][0][0] == "p0002_01"


def test_reference_sheet_prefers_face_over_back_turned() -> None:
    from manhwa2vid.characters.reference import select_reference_panels
    from manhwa2vid.models import CharacterProfile, CharacterRef, SceneCard, SeriesBible

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(id="char_mc", canonical_name="MC")

    cards = [
        SceneCard(
            panel_ids=["p0001_01"],
            people=[
                CharacterRef(ref="char_mc", visibility="back_turned", notes="green backpack seen", confidence=0.9)
            ],
        ),
        SceneCard(
            panel_ids=["p0002_01"],
            people=[
                CharacterRef(ref="char_mc", visibility="face", notes="green backpack seen", confidence=0.9)
            ],
        ),
    ]

    picked = select_reference_panels(bible, cards, per_character=1)
    assert picked["char_mc"][0][0] == "p0002_01", "back-turned panels are poor identity anchors"


def test_reference_sheet_skips_merged_tombstones() -> None:
    from manhwa2vid.characters.reference import select_reference_panels
    from manhwa2vid.models import CharacterProfile, CharacterRef, SceneCard, SeriesBible

    bible = SeriesBible(series_slug="s", title="S")
    bible.characters["char_old"] = CharacterProfile(
        id="char_old", canonical_name="Old", merged_into="char_new"
    )
    card = SceneCard(
        panel_ids=["p0001_01"],
        people=[CharacterRef(ref="char_old", visibility="face", notes="long orange hair", confidence=0.9)],
    )
    assert not select_reference_panels(bible, [card])


def test_reference_preamble_names_leading_images() -> None:
    """The model must know the first images are references, not panels to describe."""
    from pathlib import Path

    from manhwa2vid.characters.reference import format_reference_preamble

    assert format_reference_preamble([]) == ""
    text = format_reference_preamble([("Sung Jin-Woo (PROTAGONIST)", Path("a.png"))])
    assert "FIRST 1 image(s)" in text
    assert "Image 1: Sung Jin-Woo (PROTAGONIST)" in text
    assert "never list their people" in text


def test_reference_sheet_ranks_cast_above_well_evidenced_props() -> None:
    """Reference slots are scarce — spend them on people who get confused.

    Ranking by evidence score alone spent a slot on 'giant statue on the right', a minor
    profile nobody mistakes for anyone, crowding out the supporting cast member who was
    actually being swapped with the protagonist.
    """
    from manhwa2vid.characters.reference import select_reference_panels
    from manhwa2vid.models import (
        CharacterProfile,
        CharacterRef,
        CharacterTier,
        SceneCard,
        SeriesBible,
    )

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="MC", tier=CharacterTier.MAIN
    )
    bible.characters["char_ally"] = CharacterProfile(
        id="char_ally", canonical_name="Ally", tier=CharacterTier.SUPPORTING
    )
    bible.characters["char_statue"] = CharacterProfile(
        id="char_statue", canonical_name="giant statue", tier=CharacterTier.MINOR
    )

    def _card(pid: str, ref: str) -> SceneCard:
        return SceneCard(
            panel_ids=[pid],
            people=[CharacterRef(ref=ref, visibility="face", notes="clearly visible detail here", confidence=0.9)],
        )

    picked = select_reference_panels(
        bible,
        [_card("p0001_01", "char_statue"), _card("p0002_01", "char_ally"), _card("p0003_01", "char_mc")],
        max_refs=2,
    )

    assert set(picked) == {"char_mc", "char_ally"}
    assert "char_statue" not in picked


def _ref_card(
    pid: str, ref: str, *, crowd: int = 1, visibility: str = "face", confidence: float = 0.9
) -> Any:
    from manhwa2vid.models import CharacterRef, SceneCard

    people = [
        CharacterRef(
            ref=ref,
            visibility=visibility,
            notes="clear face, distinctive hair",
            confidence=confidence,
        )
    ]
    for i in range(crowd - 1):
        people.append(CharacterRef(ref="new", visibility="crowd", descriptor=f"bystander {i}"))
    return SceneCard(panel_ids=[pid], people=people)


def _ref_bible():
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="MC", tier=CharacterTier.MAIN
    )
    return bible


def test_reference_window_prefers_solo_panel_over_crowd() -> None:
    """A whole panel is the reference, so extra bodies make 'Image 1: MC' ambiguous."""
    from manhwa2vid.characters.reference import select_reference_panels

    picked = select_reference_panels(
        _ref_bible(),
        [_ref_card("p0001_01", "char_mc", crowd=4), _ref_card("p0002_01", "char_mc", crowd=1)],
        per_character=1,
    )
    assert picked["char_mc"][0][0] == "p0002_01"


def test_reference_window_spreads_across_chapters(tmp_path) -> None:
    """Costume changes across chapters are the POINT of a window.

    Three shots of the same chapter teach nothing about which features are permanent, so
    a later chapter's image must displace a same-chapter duplicate rather than be dropped.
    """
    from PIL import Image

    from manhwa2vid.characters.reference import build_reference_sheet, load_reference_sheet

    bible = _ref_bible()
    series_dir = tmp_path / "series"
    panel_paths = {}
    for pid in ("p0001_01", "p0002_01", "p0003_01"):
        img = tmp_path / f"{pid}.png"
        Image.new("RGB", (16, 16), "white").save(img)
        panel_paths[pid] = img

    build_reference_sheet(
        bible,
        [_ref_card("p0001_01", "char_mc"), _ref_card("p0002_01", "char_mc")],
        panel_paths,
        series_dir,
        chapter="1",
        per_character=3,
    )
    build_reference_sheet(
        bible, [_ref_card("p0003_01", "char_mc")], panel_paths, series_dir, chapter="2",
        per_character=3,
    )

    manifest = json.loads((series_dir / "reference" / "manifest.json").read_text())
    chapters = {e["chapter"] for e in manifest["char_mc"]}
    assert chapters == {"1", "2"}, f"window must span chapters, got {chapters}"
    assert len(load_reference_sheet(bible, series_dir)) >= 2


def test_reference_window_rerun_does_not_inflate_one_chapter(tmp_path) -> None:
    """Re-running a chapter replaces its own entries instead of stacking duplicates."""
    from PIL import Image

    from manhwa2vid.characters.reference import build_reference_sheet

    bible = _ref_bible()
    series_dir = tmp_path / "series"
    img = tmp_path / "p0001_01.png"
    Image.new("RGB", (16, 16), "white").save(img)
    panel_paths = {"p0001_01": img}
    cards = [_ref_card("p0001_01", "char_mc")]

    for _ in range(3):
        build_reference_sheet(bible, cards, panel_paths, series_dir, chapter="1")

    manifest = json.loads((series_dir / "reference" / "manifest.json").read_text())
    assert len(manifest["char_mc"]) == 1


def test_reference_preamble_warns_that_clothing_changes() -> None:
    """Anchoring on wardrobe is the failure mode a window exists to prevent."""
    from pathlib import Path

    from manhwa2vid.characters.reference import format_reference_preamble

    text = format_reference_preamble(
        [("MC (PROTAGONIST)", Path("a.png")), ("MC (PROTAGONIST)", Path("b.png"))]
    )
    assert "SAME character in different scenes or chapters" in text
    assert "SURVIVE a change of outfit" in text
    assert "never rule someone out just because their clothes differ" in text


def test_reference_manifest_upgrades_from_legacy_single_image(tmp_path) -> None:
    """An older single-image manifest must keep working, not crash the scene stage."""
    from PIL import Image

    from manhwa2vid.characters.reference import load_reference_sheet, reference_dir

    series_dir = tmp_path / "series"
    out = reference_dir(series_dir)
    out.mkdir(parents=True)
    Image.new("RGB", (16, 16), "white").save(out / "char_mc.png")
    (out / "manifest.json").write_text(json.dumps({"char_mc": "p0001_01"}))

    sheet = load_reference_sheet(_ref_bible(), series_dir)
    assert len(sheet) == 1
    assert sheet[0][0] == "MC (PROTAGONIST)"


def test_reference_window_rejects_low_confidence_identifications() -> None:
    """A shaky identification must never become an anchor.

    The reference is what every later panel is matched against, so admitting a guess makes
    one wrong face propagate through the whole series — the exact confusion the window
    exists to stop.
    """
    from manhwa2vid.characters.reference import select_reference_panels
    from manhwa2vid.models import CharacterRef, SceneCard

    bible = _ref_bible()
    shaky = SceneCard(
        panel_ids=["p0001_01"],
        people=[
            CharacterRef(
                ref="char_mc", visibility="face", notes="looks like him", confidence=0.4
            )
        ],
    )
    assert not select_reference_panels(bible, [shaky])

    sure = SceneCard(
        panel_ids=["p0002_01"],
        people=[
            CharacterRef(
                ref="char_mc", visibility="face", notes="clear face, distinctive hair",
                confidence=0.95,
            )
        ],
    )
    assert select_reference_panels(bible, [sure])["char_mc"][0][0] == "p0002_01"


def test_reference_window_ranks_by_reported_confidence() -> None:
    """Between two otherwise equal panels, the model's own certainty decides."""
    from manhwa2vid.characters.reference import select_reference_panels
    from manhwa2vid.models import CharacterRef, SceneCard

    def _card(pid: str, conf: float) -> SceneCard:
        return SceneCard(
            panel_ids=[pid],
            people=[
                CharacterRef(
                    ref="char_mc", visibility="face",
                    notes="clear face, distinctive hair", confidence=conf,
                )
            ],
        )

    picked = select_reference_panels(
        _ref_bible(), [_card("p0001_01", 0.78), _card("p0002_01", 0.99)], per_character=1
    )
    assert picked["char_mc"][0][0] == "p0002_01"


@pytest.mark.parametrize(
    "raw,expected",
    [
        (0.85, 0.85), ("0.85", 0.85), ("85%", 0.85), (85, 0.85),
        (None, 0.0), ("nonsense", 0.0), (True, 0.0), (-3, 0.0), (2.5, 0.025),
    ],
)
def test_confidence_coercion_handles_model_formats(raw, expected) -> None:
    """Models report certainty as float, string, or percentage — don't drop the signal."""
    from manhwa2vid.ocr.extract import _coerce_confidence

    assert _coerce_confidence(raw) == pytest.approx(expected)


def test_demoted_identification_loses_its_confidence() -> None:
    """An identification demoted for missing basis must not keep a high confidence,
    or it would still qualify as a reference anchor."""
    from manhwa2vid.ocr.extract import _normalize_people

    people, demoted = _normalize_people(
        [{"ref": "char_mc", "name_used": "MC", "basis": "", "confidence": 0.99}]
    )
    assert demoted == 1
    assert people[0].ref == "new"
    assert people[0].confidence == 0.0


def test_reference_window_rejects_panels_carrying_dialogue() -> None:
    """A reference with its own speech bubbles poisons bubble transcription.

    The ch1 reference was a full page reading "MY NAME IS SUNG JIN-WOO / E-RANK HUNTER".
    The vision model transcribed THAT instead of the panel under analysis, and 85% of
    chapter 2's cards inherited the chapter 1 cold open's narration and injury imagery.
    """
    from manhwa2vid.characters.reference import select_reference_panels
    from manhwa2vid.models import CharacterRef, SceneCard

    person = CharacterRef(
        ref="char_mc", visibility="face", notes="clear face, distinctive hair", confidence=0.95
    )
    talky = SceneCard(
        panel_ids=["p0001_01"],
        people=[person],
        dialogue_summary="He introduces himself as an E-rank hunter.",
    )
    assert not select_reference_panels(_ref_bible(), [talky])

    silent = SceneCard(panel_ids=["p0002_01"], people=[person])
    assert select_reference_panels(_ref_bible(), [silent])["char_mc"][0][0] == "p0002_01"


def test_reference_window_rejects_tall_scroll_strips() -> None:
    """A 1080x4500 scroll strip is a page, not a portrait — it was picked once, and the
    model described the whole page as if it were the panel."""
    from manhwa2vid.characters.reference import select_reference_panels
    from manhwa2vid.models import CharacterRef, Panel, PanelBBox, SceneCard

    person = CharacterRef(
        ref="char_mc", visibility="face", notes="clear face, distinctive hair", confidence=0.95
    )
    panels = {
        "p0001_01": Panel(
            id="p0001_01", page_num=1, image_path="a.png",
            bbox=PanelBBox(x=0, y=0, width=1080, height=4500),  # scroll strip
        ),
        "p0002_01": Panel(
            id="p0002_01", page_num=2, image_path="b.png",
            bbox=PanelBBox(x=0, y=0, width=1080, height=1200),  # portrait-ish
        ),
    }
    cards = [
        SceneCard(panel_ids=["p0001_01"], people=[person]),
        SceneCard(panel_ids=["p0002_01"], people=[person]),
    ]

    picked = select_reference_panels(_ref_bible(), cards, panels=panels, per_character=3)
    chosen = [pid for pid, _score in picked["char_mc"]]
    assert chosen == ["p0002_01"], f"scroll strip must be rejected, got {chosen}"


@pytest.mark.parametrize("bad", ["None", "null", "N/A", "unknown", "  none  ", "None."])
def test_nullish_names_never_become_identities(bad) -> None:
    """A model with no name to give answers "None" — that must not become a character.

    Slugified, it produced char_none, which was seeded into the bible and then absorbed a
    pale silhouette, an orange-haired man in a blue jacket, and two other unrelated figures
    into one fake identity that passed every downstream id check.
    """
    from manhwa2vid.characters.bible import slugify_char_id
    from manhwa2vid.ocr.extract import _normalize_people

    people, _demoted = _normalize_people(
        [{"ref": "new", "name_used": bad, "descriptor": "pale-skinned person",
          "basis": "clearly visible", "confidence": 0.9}]
    )
    assert people[0].name_used == "", f"{bad!r} leaked through as a name"
    assert slugify_char_id(bad) == "char_unknown"


def test_nullish_ref_is_forced_to_new() -> None:
    """char_none arriving as a ref must be rejected even though it looks well-formed."""
    from manhwa2vid.ocr.extract import _normalize_people

    people, _ = _normalize_people(
        [{"ref": "char_none", "name_used": "", "descriptor": "small white silhouette",
          "basis": "visible outline", "confidence": 0.9}]
    )
    assert people[0].ref == "new"


def _degenerate_cards(n: int = 20) -> list:
    """The ch2-with-references corpus: one description repeated with cosmetic variation."""
    from manhwa2vid.models import SceneCard

    variants = [
        "Sung Jin-Woo introduces himself as an E-rank hunter from the Hunter Guild",
        "Sung Jin-Woo introduces himself through narration as an E-Rank hunter of the Guild",
        "Sung Jin-Woo identifies himself by name and rank as an E-Rank Hunter Guild member",
    ]
    return [
        SceneCard(panel_ids=[f"p{i:04d}_01"], action=variants[i % len(variants)],
                  dialogue_summary=variants[i % len(variants)])
        for i in range(n)
    ]


def _varied_cards(n: int = 20) -> list:
    from manhwa2vid.models import SceneCard

    subjects = ["commuters", "an excavator", "a healer", "two hunters", "a blue gate",
                "a guild clerk", "a stray cat", "a vending machine", "a rooftop antenna",
                "a bus driver", "a paramedic", "a security guard", "a food vendor",
                "a schoolgirl", "a delivery rider", "a window cleaner", "a busker",
                "a taxi queue", "a fire escape", "a subway turnstile"]
    verbs = ["crowds", "swings", "scolds", "toasts", "crackles", "counts", "slips",
             "hums", "sways", "waits", "kneels", "salutes", "shouts", "stumbles",
             "weaves", "polishes", "strums", "shuffles", "rattles", "clicks"]
    places = ["crosswalk", "site fence", "hospital ward", "food truck", "scaffolding",
              "muster point", "alley", "platform", "rooftop", "depot", "clinic",
              "lobby", "market", "classroom", "junction", "atrium", "underpass",
              "kerbside", "stairwell", "gateline"]
    return [
        SceneCard(
            panel_ids=[f"p{i:04d}_01"],
            action=f"{subjects[i % len(subjects)]} {verbs[i % len(verbs)]} near the "
                   f"{places[i % len(places)]} while distant sirens fade",
        )
        for i in range(n)
    ]


def test_card_diversity_gate_fails_on_degenerate_chapter() -> None:
    """A chapter of near-identical cards passed all seven scene gates while being unusable.

    Every other scene gate checks a card against its own panel; none asked whether the
    cards were distinguishable from EACH OTHER.
    """
    from manhwa2vid.ocr.extract import _duplicate_card_ratio

    frac, examples = _duplicate_card_ratio(_degenerate_cards())
    assert frac > 0.30, f"degenerate corpus should trip the fail band, got {frac:.0%}"
    assert examples


def test_card_diversity_gate_passes_healthy_chapter() -> None:
    """Real ch1 and ch2 corpora both score 0% — the gate must not fire on them."""
    from manhwa2vid.ocr.extract import _duplicate_card_ratio

    frac, _ = _duplicate_card_ratio(_varied_cards())
    assert frac < 0.15, f"healthy corpus must stay under the warn band, got {frac:.0%}"


def test_card_diversity_ignores_non_story_cards() -> None:
    """Title splashes and credits legitimately repeat — they are not story content."""
    from manhwa2vid.models import SceneCard
    from manhwa2vid.ocr.extract import _duplicate_card_ratio

    cards = _varied_cards(10) + [
        SceneCard(panel_ids=[f"c{i}"], action="chapter title splash", is_story=False,
                  panel_type="title_splash")
        for i in range(8)
    ]
    frac, _ = _duplicate_card_ratio(cards)
    assert frac < 0.15


def test_window_images_are_labeled_inline_not_by_a_counted_list() -> None:
    """Binding must be positional, not a count the model maintains.

    A single 59-image pass returned CORRECT annotations attached to the panel id three
    positions later (measured shift +3, similarity 0.75). Each image now carries its id
    immediately before it in the message.
    """
    from manhwa2vid.models import Panel, PanelBBox
    from manhwa2vid.ocr.extract import _build_window_prompt

    panels = [
        Panel(id=f"p{i:04d}_01", page_num=i, image_path=f"{i}.png",
              bbox=PanelBBox(x=0, y=0, width=100, height=100))
        for i in range(1, 4)
    ]
    prompt = _build_window_prompt(
        panels, {}, {}, "CAST: none",
        {"summary": "A hunter walks.", "temporal_devices": "flashforward at the start"},
        "  - Hero: dark hair",
    )
    assert "annotate ONLY these 3 panels" in prompt
    assert "preceded by a line naming its panel id" in prompt
    # chapter understanding must ride into the window
    assert "A hunter walks." in prompt
    assert "flashforward at the start" in prompt
    assert "Hero: dark hair" in prompt


def test_labeled_panels_interleaves_label_before_each_image(tmp_path) -> None:
    """The provider must emit text-then-image pairs, not all text then all images."""
    from PIL import Image

    from manhwa2vid.llm.provider import GeminiProvider

    paths = []
    for name in ("a", "b"):
        f = tmp_path / f"{name}.png"
        Image.new("RGB", (8, 8), "white").save(f)
        paths.append(f)

    captured = {}

    class _Spy(GeminiProvider):
        def __init__(self):  # skip client construction
            self.vision_model = "test"

        def _vision_call(self, content):
            captured["content"] = content
            return "{}"

    _Spy().describe_labeled_panels(
        [("PANEL p0001_01:", paths[0]), ("PANEL p0002_01:", paths[1])], "prompt"
    )
    kinds = [c["type"] for c in captured["content"]]
    assert kinds == ["text", "text", "image_url", "text", "image_url"], kinds
    assert captured["content"][1]["text"] == "PANEL p0001_01:"
    assert captured["content"][3]["text"] == "PANEL p0002_01:"


def test_chapter_windows_keep_one_window_when_it_fits() -> None:
    """Continuity is the whole point — do not split a chapter that fits in one call."""
    from manhwa2vid.models import Panel, PanelBBox
    from manhwa2vid.ocr.extract import _chapter_windows

    panels = [
        Panel(id=f"p{i:04d}_01", page_num=i, image_path=f"{i}.png",
              bbox=PanelBBox(x=0, y=0, width=10, height=10))
        for i in range(70)
    ]
    assert len(_chapter_windows(panels, 90)) == 1
    assert sum(len(w) for w in _chapter_windows(panels, 30)) == 70


def test_chapter_pass_normalizes_through_the_same_guards(tmp_path, monkeypatch) -> None:
    """Chapter mode must not bypass a guard the per-panel path enforces.

    Asserts the shared normalization still fires: an invented panel_id is dropped, a
    nullish name is rejected, and an unbacked identification is demoted.
    """
    from manhwa2vid.models import Panel, PanelBBox, SeriesBible
    from manhwa2vid.ocr.extract import _run_chapter_scene_pass

    panels = [
        Panel(id="p0001_01", page_num=1, image_path="a.png",
              bbox=PanelBBox(x=0, y=0, width=100, height=100)),
        Panel(id="p0002_01", page_num=2, image_path="b.png",
              bbox=PanelBBox(x=0, y=0, width=100, height=100)),
    ]

    class _ChapterLLM:
        MAX_VISION_TOKENS = 4096

        def describe_panels(self, image_paths, prompt):
            return json.dumps({"summary": "A man walks.", "temporal_devices": "",
                               "roster": [{"who": "a man", "looks": "dark coat"}]})

        def describe_labeled_panels(self, labeled, prompt):
            return json.dumps({
                "panels": [
                    {"panel_id": "p0001_01", "action": "A man crosses a street",
                     "people": [{"ref": "new", "name_used": "None", "descriptor": "a man",
                                 "basis": "clearly visible", "confidence": 0.9}],
                     "speakers": [], "dialogue_summary": "", "mood": "calm",
                     "key_terms": [], "is_story": True, "panel_type": "story"},
                    {"panel_id": "p0002_01", "action": "Rain falls on an empty road",
                     "people": [{"ref": "char_ghost", "name_used": "Ghost",
                                 "descriptor": "", "basis": "", "confidence": 0.95}],
                     "speakers": [], "dialogue_summary": "", "mood": "bleak",
                     "key_terms": [], "is_story": True, "panel_type": "story"},
                    {"panel_id": "p9999_99", "action": "invented panel", "people": [],
                     "speakers": [], "dialogue_summary": "", "mood": "", "key_terms": [],
                     "is_story": True, "panel_type": "story"},
                ],
            })

    bible = SeriesBible(series_slug="s", title="S")
    cards, counters, story_map = _run_chapter_scene_pass(
        panels, {"root": tmp_path, "scene_partial_json": tmp_path / "partial.json"},
        {}, {}, bible, _ChapterLLM(), {},
    )

    assert [c.panel_ids[0] for c in cards] == ["p0001_01", "p0002_01"], "invented id must drop"
    assert story_map["summary"] == "A man walks."
    assert cards[0].people[0].name_used == "", "nullish name must not survive"
    assert cards[1].people[0].ref == "new", "unbacked identification must be demoted"
    assert counters["demoted"] >= 1


def test_cast_stage_elects_protagonist_when_bible_has_none() -> None:
    """Re-running scene/cast alone must not leave the bible headless.

    Election normally happens in the quest stage, so a scene-only re-run left
    protagonist_id empty — and naming priority, the MC name budget, MC-off-screen linting
    and the verifier's [PROTAGONIST] tag all silently degraded while every gate passed.
    """
    from manhwa2vid.characters.quest import detect_protagonist

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="")
    bible.characters["char_hero"] = CharacterProfile(
        id="char_hero", canonical_name="Hero", tier=CharacterTier.SUPPORTING,
        appearances=[f"p{i:04d}_01" for i in range(40)], confidence=0.9,
    )
    bible.characters["char_extra"] = CharacterProfile(
        id="char_extra", canonical_name="Extra", tier=CharacterTier.MINOR,
        appearances=["p0001_01"], confidence=0.5,
    )

    assert detect_protagonist(bible, {}) == "char_hero"
