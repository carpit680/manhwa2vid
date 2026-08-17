"""Script lint tests."""

from __future__ import annotations

import pytest

from manhwa2vid.models import ScriptBeat
from manhwa2vid.script.lint import find_violations, lint_beats


def test_find_violations_flags_character() -> None:
    hits = find_violations("A character walks into the room.", ["character"])
    assert "character" in hits


def test_lint_beats_reports_offending_beats() -> None:
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p001"], narration="Clean narration."),
        ScriptBeat(beat_id=2, panel_ids=["p002"], narration="Two characters fight."),
    ]
    config = {"characters": {"ban_words": ["character", "two characters"]}}
    report = lint_beats(beats, config)
    assert 2 in report
    assert 1 not in report


def test_lint_mc_attribution_flags_off_screen_mc() -> None:
    from manhwa2vid.models import PanelCast, CharacterRef, ScriptBeat, SeriesBible, CharacterProfile, CharacterTier
    from manhwa2vid.script.lint import lint_mc_attribution

    bible = SeriesBible(
        series_slug="t",
        title="T",
        protagonist_id="char_mc",
        characters={"char_mc": CharacterProfile(id="char_mc", canonical_name="MC", tier=CharacterTier.MAIN)},
    )
    attribution = [
        PanelCast(panel_id="p002", people=[CharacterRef(ref="char_other", name_used="Other")]),
    ]
    beats = [ScriptBeat(beat_id=2, panel_ids=["p002"], narration="The MC watches from afar.")]
    report = lint_mc_attribution(beats, bible, attribution, {"characters": {"mc_labels": ["MC"]}})
    assert 2 in report


def test_name_anchors_follow_cadence_not_a_hard_cap() -> None:
    """The hard cap (hook + 2 names per script) made the MC 'he' for fifteen beats.

    Measured on the shipped ch1 video: 62 pronouns to 3 names — 21:1 against the
    reference channel's ~6:1 — which the user immediately flagged as repetitive.
    Cadence semantics: an anchor roughly every N beats, short form after the first.
    """
    from manhwa2vid.models import CharacterProfile, CharacterTier, ScriptBeat, SeriesBible
    from manhwa2vid.script.lint import enforce_mc_name_budget, lint_mc_name_spam

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="Sung Jin-Woo", tier=CharacterTier.MAIN, pronoun="he"
    )
    config = {"script": {"mc_anchor_every_beats": 2}}

    beats = [
        ScriptBeat(beat_id=i, panel_ids=[f"p{i:04d}_01"], narration="Sung Jin-Woo walks on.")
        for i in range(1, 11)
    ]

    out = enforce_mc_name_budget(beats, bible, config)

    names = sum(1 for b in out if "Jin-Woo" in b.narration)
    pronouns = sum(1 for b in out if b.narration.startswith("He "))
    assert 3 <= names <= 6, f"cadence 2 over 10 beats should anchor ~4-5 times, got {names}"
    assert pronouns >= 4, "the beats between anchors must still rotate"
    assert out[0].narration.startswith("Sung Jin-Woo"), "hook keeps the full name"
    assert any(b.narration.startswith("Jin-Woo ") for b in out[1:]), \
        "later anchors use the natural short form"
    assert not lint_mc_name_spam(out, bible, config)


def test_ambiguous_beat_forces_a_name_anchor() -> None:
    """A beat naming another same-pronoun character must anchor the MC by name.

    'Kim Sangshik sips coffee and shouts to him. He says…' — spoken aloud, the listener
    cannot tell which man is 'he'. This ambiguity was most of the 'other inconsistencies'
    in the user's review of the ch1 video.
    """
    from manhwa2vid.models import CharacterProfile, CharacterTier, ScriptBeat, SeriesBible
    from manhwa2vid.script.lint import enforce_mc_name_budget

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="Sung Jin-Woo", tier=CharacterTier.MAIN, pronoun="he"
    )
    bible.characters["char_kim"] = CharacterProfile(
        id="char_kim", canonical_name="Kim Sangshik", tier=CharacterTier.SUPPORTING,
        pronoun="he",
    )
    bible.characters["char_joo"] = CharacterProfile(
        id="char_joo", canonical_name="Lee Joo-hee", tier=CharacterTier.SUPPORTING,
        pronoun="she",
    )

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="Sung Jin-Woo wakes up."),
        # Cadence 99 would rotate this — but Kim shares 'he', so it must anchor.
        ScriptBeat(beat_id=2, panel_ids=["p2"],
                   narration="Kim Sangshik waves. Sung Jin-Woo walks over."),
        # Joo-hee is 'she' — no collision, cadence rotation applies.
        ScriptBeat(beat_id=3, panel_ids=["p3"],
                   narration="Lee Joo-hee scolds Sung Jin-Woo gently."),
    ]

    out = enforce_mc_name_budget(beats, bible, {"script": {"mc_anchor_every_beats": 99}})

    assert "Jin-Woo walks over" in out[1].narration, out[1].narration
    assert "Jin-Woo" not in out[2].narration, "no collision -> rotates on cadence"


def test_name_budget_preserves_beat_one_anchor() -> None:
    """Beat 1 must still name the protagonist — that's the anchor the rest rotates against."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, ScriptBeat, SeriesBible
    from manhwa2vid.script.lint import enforce_mc_name_budget

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="Sung Jin-Woo", tier=CharacterTier.MAIN, pronoun="he"
    )
    beats = [ScriptBeat(beat_id=1, panel_ids=["p0001_01"], narration="Sung Jin-Woo bleeds out.")]

    out = enforce_mc_name_budget(beats, bible, {})

    assert out[0].narration == "Sung Jin-Woo bleeds out."


def test_bible_role_grounds_intro_clause() -> None:
    """The recap prompt REQUIRES an intro clause from the cast list; lint must allow it.

    'Lee Joo-hee, the party's healer' was flagged ungrounded:healer because panel art
    never contains the word 'healer' — punishing the exact clause the prompt mandates.
    """
    from manhwa2vid.models import (
        CharacterProfile,
        CharacterRef,
        PanelCast,
        SceneCard,
        ScriptBeat,
        SeriesBible,
    )
    from manhwa2vid.script.lint import lint_panel_grounding

    bible = SeriesBible(series_slug="s", title="S")
    bible.characters["char_joo"] = CharacterProfile(
        id="char_joo", canonical_name="Lee Joo-hee", role="party healer"
    )
    attribution = [PanelCast(panel_id="p0001_01", people=[CharacterRef(ref="char_joo")])]
    cards = [SceneCard(panel_ids=["p0001_01"], action="a woman scolds a man", dialogue_summary="")]
    beats = [
        ScriptBeat(
            beat_id=1,
            panel_ids=["p0001_01"],
            narration="Lee Joo-hee, the party's healer, snaps at him.",
        )
    ]

    assert lint_panel_grounding(beats, cards), "without the bible it must still flag"
    assert not lint_panel_grounding(beats, cards, bible=bible, attribution=attribution)


def test_invented_healer_still_flagged_when_absent() -> None:
    """The grounding rule must keep catching a healer nobody in the beat actually is."""
    from manhwa2vid.models import (
        CharacterProfile,
        CharacterRef,
        PanelCast,
        SceneCard,
        ScriptBeat,
        SeriesBible,
    )
    from manhwa2vid.script.lint import lint_panel_grounding

    bible = SeriesBible(series_slug="s", title="S")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="Sung Jin-Woo", role="E-Rank hunter"
    )
    attribution = [PanelCast(panel_id="p0001_01", people=[CharacterRef(ref="char_mc")])]
    cards = [SceneCard(panel_ids=["p0001_01"], action="a man walks alone", dialogue_summary="")]
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p0001_01"], narration="A healer patches him up.")
    ]

    flagged = lint_panel_grounding(beats, cards, bible=bible, attribution=attribution)
    assert flagged.get(1) == ["ungrounded:healer"]


@pytest.mark.parametrize(
    "text,expected",
    [
        # Object slot after a transitive verb — the ch1 bug ("tells he to stay").
        ("Sung Jin-Woo waits. Kim tells Sung Jin-Woo to stay back.", "tells him to stay back."),
        # Object slot after a preposition.
        ("Sung Jin-Woo waits. She walks with Sung Jin-Woo.", "walks with him."),
        # Subject slot stays nominative.
        ("Sung Jin-Woo waits. Sung Jin-Woo enters the gate.", "He enters the gate."),
        # Possessive still wins over both.
        ("Sung Jin-Woo waits. Sung Jin-Woo's leg bleeds.", "His leg bleeds."),
    ],
)
def test_rotation_uses_object_case_where_required(text, expected) -> None:
    """Rotated narration is SPOKEN — a case error is audible, not cosmetic."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import rotate_protagonist_name

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="Sung Jin-Woo", tier=CharacterTier.MAIN, pronoun="he"
    )

    out = rotate_protagonist_name(text, bible)

    assert expected in out, out
    assert "tells he " not in out and "with he." not in out


@pytest.mark.parametrize(
    "text,expected",
    [
        # The miss that shipped: 'pats' was not in any verb whitelist.
        ("A hunter pats he on the shoulder.", "pats him on"),
        ("Kim tells he about a nickname.", "tells him about"),
        ("She stands with he near the gate.", "with him near"),
        # Reported speech is the dominant construction — must stay nominative.
        ("They say he is the weakest hunter.", "say he is"),
        ("Kim smiles and he laughs.", "and he laughs"),
        # Clause-initial stays nominative whatever preceded the break.
        ("The gate opens. He steps through.", "He steps"),
        ("Nearby, he waves.", "he waves"),
    ],
)
def test_pronoun_case_decided_by_following_word(text, expected) -> None:
    """Object-vs-subject is decided by what FOLLOWS the pronoun, not a verb whitelist.

    Name rotation emits the subject form, so "Kim pats Jin-Woo" became "pats he" —
    ungrammatical in narration that gets spoken aloud. A whitelist could not keep up.
    """
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import fix_pronoun_case

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="Hero", tier=CharacterTier.MAIN, pronoun="he"
    )
    assert expected in fix_pronoun_case(text, bible)


def test_captioning_lint_flags_image_description_language() -> None:
    """'A plate of food sits on the counter' is alt-text, not narration.

    The user's verdict on the shipped video: "a stringed narration of image
    descriptions". These constructions are its fingerprint — the gold script contains
    zero of them across 677 words.
    """
    from manhwa2vid.script.lint import lint_captioning

    flagged = ScriptBeat(
        beat_id=1, panel_ids=["p1"],
        narration="A plate of food sits on the counter. Kim looks up with a startled "
                  "expression. Bak is visible in the background.",
    )
    clean = ScriptBeat(
        beat_id=2, panel_ids=["p2"],
        narration="Kim looks up, startled, when someone shouts his name across the lot.",
    )
    report = lint_captioning([flagged, clean])
    assert 1 in report and len(report[1]) == 3
    assert 2 not in report


def test_pronoun_monotony_is_local_to_a_beat() -> None:
    """Aggregate ratio can pass while one beat reads He... He... He... He..."""
    from manhwa2vid.script.lint import lint_pronoun_monotony

    monotone = ScriptBeat(
        beat_id=3, panel_ids=["p3"],
        narration="He walks through the streets. He blends into the crowd. "
                  "He thinks about his job. He heads toward the site.",
    )
    varied = ScriptBeat(
        beat_id=4, panel_ids=["p4"],
        narration="He walks through the streets. Nobody looks at him twice. "
                  "He thinks about his job. But the site ahead is already buzzing.",
    )
    report = lint_pronoun_monotony([monotone, varied])
    assert report == {3: ["pronoun_monotony:4_consecutive"]}


@pytest.mark.parametrize(
    "text",
    [
        # Every one of these shipped as gibberish from the previous default-to-object
        # heuristic (adverbs and irregular pasts defeat suffix-based verb detection).
        "He admits he only returned because of his wife.",
        "She asks if he went to the hospital.",
        "Will he manage to survive this dungeon?",
        "Kim says he is the weakest hunter.",
        "He admits he already went.",
    ],
)
def test_pronoun_case_never_corrupts_subject_clauses(text) -> None:
    """A wrong conversion is gibberish out loud; precision beats recall."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import fix_pronoun_case

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="Hero", tier=CharacterTier.MAIN, pronoun="he"
    )
    assert fix_pronoun_case(text, bible) == text, "subject clause must not be converted"


def test_reintroduction_appositives_flagged_after_first() -> None:
    """Kim got 'with short grey hair' seven times; Song Chi-yul then got the SAME
    description — three men indistinguishable to a listener. One intro per character."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import lint_reintroduction

    bible = SeriesBible(series_slug="s", title="S")
    bible.characters["char_kim"] = CharacterProfile(
        id="char_kim", canonical_name="Kim Sangshik", tier=CharacterTier.SUPPORTING
    )

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"],
                   narration="Kim Sangshik, a seasoned hunter with short grey hair, waves."),
        ScriptBeat(beat_id=2, panel_ids=["p2"],
                   narration="Kim Sangshik, the man with short grey hair, drinks his coffee."),
        ScriptBeat(beat_id=3, panel_ids=["p3"],
                   narration="Kim Sangshik laughs at the joke."),
    ]

    report = lint_reintroduction(beats, bible)
    assert 1 not in report, "the first intro is legitimate"
    assert report.get(2) == ["reintro:Kim Sangshik"]
    assert 3 not in report, "bare name is always fine"


def test_strip_repeated_appositives_is_deterministic() -> None:
    """The LLM rewrite complied ZERO times in two iterations (11 flagged -> 11 flagged),
    so appositive removal stops being a request. First intro survives; later ones become
    the bare name."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import strip_repeated_appositives

    bible = SeriesBible(series_slug="s", title="S")
    bible.characters["char_kim"] = CharacterProfile(
        id="char_kim", canonical_name="Kim Sangshik", tier=CharacterTier.SUPPORTING
    )
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"],
                   narration="Kim Sangshik, a veteran hunter with short grey hair, waves."),
        ScriptBeat(beat_id=2, panel_ids=["p2"],
                   narration="Kim Sangshik, the man with short grey hair and a blue jacket, drinks."),
        ScriptBeat(beat_id=3, panel_ids=["p3"], narration="Kim Sangshik laughs."),
    ]
    out = strip_repeated_appositives(beats, bible)
    assert "short grey hair" in out[0].narration, "first intro keeps its clause"
    assert out[1].narration == "Kim Sangshik drinks."
    assert out[2].narration == "Kim Sangshik laughs."


def test_uncertain_rotation_slot_keeps_the_name() -> None:
    """"the gate completely engulfs he" shipped because 'engulfs' was not on any cue
    list. When neither the prior word nor the next word settles the case, the name stays
    — style cost, never gibberish."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import rotate_protagonist_name

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="Sung Jin-Woo", tier=CharacterTier.MAIN, pronoun="he"
    )
    text = "Sung Jin-Woo hesitates. The blue energy completely engulfs Sung Jin-Woo."
    out = rotate_protagonist_name(text, bible)
    assert "engulfs he" not in out and "engulfs He" not in out
    assert "engulfs Sung Jin-Woo" in out or "engulfs him" in out


def test_pure_scenery_caption_sentences_are_deleted() -> None:
    """"An empty plate and chopsticks rest on the counter" survived two LLM rewrites —
    deletion is deterministic. Sentences containing people are never touched."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import strip_caption_sentences

    bible = SeriesBible(series_slug="s", title="S")
    bible.characters["char_kim"] = CharacterProfile(
        id="char_kim", canonical_name="Kim Sangshik", tier=CharacterTier.SUPPORTING
    )
    beats = [
        ScriptBeat(
            beat_id=5, panel_ids=["p1"],
            narration="An empty plate and chopsticks rest on the counter of the food "
                      "stand. Kim Sangshik holds his coffee cup and turns when a voice "
                      "calls his name.",
        ),
        # Person-bearing caption-ish sentence must survive; never empty a beat.
        ScriptBeat(
            beat_id=6, panel_ids=["p2"],
            narration="His hands rest on the cold railing.",
        ),
    ]
    out = strip_caption_sentences(beats, bible)
    assert out[0].narration == (
        "Kim Sangshik holds his coffee cup and turns when a voice calls his name."
    )
    assert out[1].narration == "His hands rest on the cold railing."


def test_descriptor_quarantine_ignores_possessive_mentions() -> None:
    """"He carries his green backpack" is narration; "the man with green backpack" is
    identity-by-descriptor. Bare substring matching flagged 10 of 13 beats with
    unfixable violations, drowning the rewrite loop."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import lint_descriptor_quarantine

    bible = SeriesBible(series_slug="s", title="S")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="Sung Jin-Woo", tier=CharacterTier.MAIN,
        descriptors=["man with green backpack", "green backpack"],
    )
    ok = ScriptBeat(beat_id=1, panel_ids=["p1"],
                    narration="He carries his green backpack through the crowd.")
    bad = ScriptBeat(beat_id=2, panel_ids=["p2"],
                     narration="The man with green backpack declines the offer.")
    report = lint_descriptor_quarantine([ok, bad], bible)
    assert 1 not in report
    assert 2 in report


@pytest.mark.parametrize(
    "text,expected",
    [
        # 'after' as conjunction: the verb after the pronoun marks a subject clause.
        ("After he dismisses the guard's concern, a voice shouts.",
         "After he dismisses the guard's concern, a voice shouts."),
        # 'after' as preposition: genuine object slot still converts.
        ("The guard runs after he into the site.", "The guard runs after him into the site."),
    ],
)
def test_prepositions_that_double_as_conjunctions(text, expected) -> None:
    """"After him dismisses a gate guard's concern" shipped — same word, two roles."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import fix_pronoun_case

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="Hero", tier=CharacterTier.MAIN, pronoun="he"
    )
    assert fix_pronoun_case(text, bible) == expected


def test_cross_beat_repetition_flagged() -> None:
    """Hospital/healer content landed three times across beats 12-14: each beat is
    written from only its own panels, so a conversation spanning cards gets re-narrated."""
    from manhwa2vid.script.lint import lint_cross_beat_repetition

    beats = [
        ScriptBeat(beat_id=12, panel_ids=["p1"],
                   narration="Lee Joo-hee asks why Jin-Woo visited the hospital again "
                             "after another injured raid."),
        ScriptBeat(beat_id=13, panel_ids=["p2"],
                   narration="Lee Joo-hee asks whether Jin-Woo visited the hospital "
                             "again after another injured raid."),
        ScriptBeat(beat_id=14, panel_ids=["p3"],
                   narration="He steps through the swirling gate without looking back."),
    ]
    report = lint_cross_beat_repetition(beats)
    assert 13 in report and report[13][0].startswith("repeats_beat_12")
    assert 14 not in report
