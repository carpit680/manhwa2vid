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
    from manhwa2vid.script import grounding
    from manhwa2vid.script.lint import lint_panel_grounding

    # The keyword pre-filter has no built-in list — it is per-series data.
    grounding.configure_grounding_keywords({"script": {"grounding_keywords": {"healer": ["healer", "healers"]}}})

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
    from manhwa2vid.script import grounding
    from manhwa2vid.script.lint import lint_panel_grounding

    # The keyword pre-filter has no built-in list — it is per-series data.
    grounding.configure_grounding_keywords({"script": {"grounding_keywords": {"healer": ["healer", "healers"]}}})

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


def test_duplicate_temporal_transitions_stripped() -> None:
    """A chapter rewinds from its flashforward ONCE.

    The prompt rule fires per beat, so beats 1, 2 and 3 each announced "but it starts
    hours earlier". Whole-beat repetition linting cannot catch this — those beats differ
    everywhere except the one repeated clause.
    """
    from manhwa2vid.script.lint import strip_duplicate_transitions

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"],
                   narration="Jin-Woo lies in his own blood. Stone sentinels loom over "
                             "him, but this nightmare starts hours earlier."),
        ScriptBeat(beat_id=2, panel_ids=["p2"],
                   narration="The spear swings down. But the path to this nightmare for "
                             "him begins hours earlier over a quiet Seoul."),
        ScriptBeat(beat_id=3, panel_ids=["p3"],
                   narration="That is where this day is headed, but it starts hours "
                             "earlier on a Seoul street. He walks among commuters."),
    ]
    out = strip_duplicate_transitions(beats)
    assert "starts hours earlier" in out[0].narration, "first rewind is kept"
    assert "hours earlier" not in out[1].narration
    assert "hours earlier" not in out[2].narration
    assert "He walks among commuters." in out[2].narration, "story content survives"
    assert all(b.narration.strip() for b in out), "no beat may be emptied"


def test_transition_with_its_own_action_survives() -> None:
    """A sentence that both transitions AND advances the story is not a restatement."""
    from manhwa2vid.script.lint import strip_duplicate_transitions

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="It starts hours earlier."),
        ScriptBeat(beat_id=2, panel_ids=["p2"],
                   narration="Hours earlier, Lee Joo-hee had begged him to stay home "
                             "and rest his broken ribs."),
    ]
    out = strip_duplicate_transitions(beats)
    assert "Joo-hee" in out[1].narration


def test_malformed_opening_detected() -> None:
    """One run opened a beat with "is headed, but it starts hours earlier." — a dangling
    clause from chunked generation. Spoken aloud it is simply broken, and no gate looked
    at how a beat STARTS."""
    from manhwa2vid.script.lint import lint_malformed_opening

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="He lies bleeding on the floor."),
        ScriptBeat(beat_id=2, panel_ids=["p2"],
                   narration="is headed, but it starts hours earlier. He gasps."),
    ]
    report = lint_malformed_opening(beats)
    assert 1 not in report
    assert 2 in report and report[2][0].startswith("malformed_opening:")


def test_malformed_opening_repaired_by_dropping_the_fragment() -> None:
    """The missing subject cannot be invented, but the fragment is disposable — the
    sentences after it are complete prose."""
    from manhwa2vid.script.lint import lint_malformed_opening, repair_malformed_openings

    beats = [
        ScriptBeat(beat_id=2, panel_ids=["p2"],
                   narration="is headed, but it starts hours earlier. He gasps as the "
                             "sentinel raises its spear. He curses his luck."),
        ScriptBeat(beat_id=3, panel_ids=["p3"], narration="He walks the morning streets."),
        # A single broken sentence has nothing to fall back to — leave it for the gate.
        ScriptBeat(beat_id=4, panel_ids=["p4"], narration="is headed, but it starts."),
    ]
    out = repair_malformed_openings(beats)
    assert out[0].narration.startswith("He gasps as the sentinel")
    assert out[1].narration == "He walks the morning streets."
    assert out[2].narration == "is headed, but it starts.", "nothing to salvage"
    assert set(lint_malformed_opening(out)) == {4}, "residue still reaches the gate"


def test_intra_beat_repetition_removed() -> None:
    """Beat 8 had Kim waving in two consecutive sentences; cross-beat linting compares
    whole beats, so within-beat echoes were invisible."""
    from manhwa2vid.script.lint import dedupe_intra_beat_sentences

    beats = [
        ScriptBeat(beat_id=8, panel_ids=["p1"],
                   narration="He spots Kim Sangshik waving enthusiastically from the "
                             "distance. Kim Sangshik waves enthusiastically and asks if "
                             "he has eaten. Bak wonders if he is powerful."),
    ]
    out = dedupe_intra_beat_sentences(beats)
    assert out[0].narration.count("waving") + out[0].narration.count("waves") == 1
    assert "Bak wonders" in out[0].narration, "distinct content survives"


def test_overlong_beat_trimmed_to_its_word_cap() -> None:
    """The cap has been in the prompt and the lint for days; the rewrite ignores it
    (4 flagged -> 3 still flagged). Padding accumulates in trailing sentences."""
    from manhwa2vid.script.lint import trim_overlong_beats

    long_beat = ScriptBeat(
        beat_id=10, panel_ids=["p1", "p2"],   # cap = 2 * 14 = 28 words
        narration=("Jin-Woo walks past the machinery ignoring the gossip. "
                   "Bak asks if he is truly the weakest. "
                   "Kim laughs and replies that he absolutely is. "
                   "Kim adds the dungeon will be weak because of him. "
                   "Bak looks back in surprise at the claim."),
    )
    short_beat = ScriptBeat(beat_id=11, panel_ids=["p3"], narration="He asks for coffee.")
    out = trim_overlong_beats([long_beat, short_beat], {})
    assert len(out[0].narration.split()) <= 38, out[0].narration
    assert out[0].narration.startswith("Jin-Woo walks past"), "the beat's point is kept"
    assert len(out[0].narration.split(".")) >= 3, "never gutted below two sentences"
    assert out[1].narration == "He asks for coffee.", "short beats untouched"


def test_rewind_kept_on_the_beat_that_shows_the_shift() -> None:
    """"Keep the first mention" shipped the very defect it was meant to fix.

    The rewind landed in beat 1 — spoken over dungeon art before anything changed —
    while the beat containing the present-day establishing shot (p0007_04) narrated the
    killing blow and let the transition panel pass in silence. The gold gives that panel
    its own beat: "Then the sky clears, over present-day Seoul."
    """
    from manhwa2vid.script.lint import strip_duplicate_transitions

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p0002_01", "p0003_01"],
                   narration="He lies in his own blood. He never expected this fate, "
                             "though this day actually began hours earlier."),
        ScriptBeat(beat_id=2, panel_ids=["p0006_01", "p0007_04"],
                   narration="The spear plunges down in a spray of blood. That is where "
                             "this day is headed, but it starts hours earlier."),
        ScriptBeat(beat_id=3, panel_ids=["p0008_01"],
                   narration="He walks the morning streets, just another commuter."),
    ]
    out = strip_duplicate_transitions(beats, transition_panel="p0007_04")

    assert "hours earlier" not in out[0].narration, "beat 1 is still inside the flashforward"
    assert "He lies in his own blood." in out[0].narration
    assert "hours earlier" in out[1].narration, "the beat showing the shift keeps it"
    assert "commuter" in out[2].narration


def test_transition_falls_back_to_first_when_panel_unknown() -> None:
    """Chronological chapters and older story maps have no transition panel."""
    from manhwa2vid.script.lint import strip_duplicate_transitions

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="It starts hours earlier."),
        ScriptBeat(beat_id=2, panel_ids=["p2"],
                   narration="The day begins hours earlier again. He walks on."),
    ]
    out = strip_duplicate_transitions(beats, transition_panel="")
    assert "hours earlier" in out[0].narration
    assert "hours earlier" not in out[1].narration


def test_repair_truncated_sentences_drops_dangling_fragment():
    """A bubble captured across a panel border ends mid-clause; the writer reproduces the
    cut and TTS reads it into silence. Observed: 'puts his life on the...' (p0009_01)."""
    from manhwa2vid.script.lint import repair_truncated_sentences

    beats = [
        ScriptBeat(
            beat_id=1,
            panel_ids=["p1"],
            narration="Jin-Woo crosses the street. He thinks how hunting puts his life on the... Nearby, a gate hums.",
        )
    ]
    out = repair_truncated_sentences(beats)
    assert "life on the" not in out[0].narration
    assert "Jin-Woo crosses the street." in out[0].narration
    assert "Nearby, a gate hums." in out[0].narration


def test_repair_truncated_sentences_keeps_deliberate_cliffhanger():
    """'HIS NICKNAME IS...' is the manhwa's own reveal boundary — never a capture bug."""
    from manhwa2vid.script.lint import repair_truncated_sentences

    beats = [ScriptBeat(beat_id=1, panel_ids=["p1"], narration="Kim tells Bak that his nickname is...")]
    assert repair_truncated_sentences(beats)[0].narration == "Kim tells Bak that his nickname is..."


def test_repair_truncated_sentences_never_empties_a_beat():
    """An empty narration fails beat conservation and kills the whole chapter."""
    from manhwa2vid.script.lint import repair_truncated_sentences

    beats = [ScriptBeat(beat_id=1, panel_ids=["p1"], narration="He reaches for the...")]
    assert repair_truncated_sentences(beats)[0].narration.strip()


def test_strip_repeated_appositives_handles_long_intro_clauses():
    """The second intro ran 13 words; the pattern capped at 9 and let it through."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import strip_repeated_appositives

    bible = SeriesBible(
        series_slug="s",
        title="S",
        protagonist_id="char_mc",
        characters={"char_kim": CharacterProfile(id="char_kim", canonical_name="Kim Sangshik", tier=CharacterTier.MAIN)},
    )
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="A vendor tells Kim Sangshik, a veteran hunter in a blue jacket, good luck."),
        ScriptBeat(beat_id=2, panel_ids=["p2"], narration="Kim Sangshik, a veteran hunter with short greyish-blue hair and a goatee in a blue jacket, grabs coffee."),
    ]
    out = strip_repeated_appositives(beats, bible)
    assert out[1].narration == "Kim Sangshik grabs coffee."
    assert "a veteran hunter in a blue jacket" in out[0].narration


def _bible_with_mc(name: str = "Sung Jin-Woo"):
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible

    return SeriesBible(
        series_slug="s",
        title="S",
        protagonist_id="char_mc",
        characters={"char_mc": CharacterProfile(id="char_mc", canonical_name=name, tier=CharacterTier.MAIN)},
    )


def test_strip_internal_labels_removes_appositive():
    """Observed opening line: 'Sung Jin-Woo, the protagonist and E-rank hunter, gasps...'"""
    from manhwa2vid.script.lint import strip_internal_labels

    beats = [ScriptBeat(beat_id=1, panel_ids=["p"], narration="Sung Jin-Woo, the protagonist and E-rank hunter, gasps in a pool of blood.")]
    assert strip_internal_labels(beats, _bible_with_mc())[0].narration == (
        "Sung Jin-Woo, E-rank hunter, gasps in a pool of blood."
    )


def test_strip_internal_labels_keeps_the_sentence_subject():
    """Deleting a subject leaves an unspeakable 'walks away.'"""
    from manhwa2vid.script.lint import strip_internal_labels

    beats = [ScriptBeat(beat_id=1, panel_ids=["p"], narration="The protagonist walks away.")]
    assert strip_internal_labels(beats, _bible_with_mc())[0].narration == "Jin-Woo walks away."


def test_strip_internal_labels_leaves_real_role_clauses_alone():
    from manhwa2vid.script.lint import strip_internal_labels

    text = "Jin-Woo, the guild's weakest member, gasps."
    beats = [ScriptBeat(beat_id=1, panel_ids=["p"], narration=text)]
    assert strip_internal_labels(beats, _bible_with_mc())[0].narration == text


def test_lint_dropped_speakers_catches_an_ignored_named_speaker():
    """ch1 beat 16: evidence held Song Chi-yul asking the party to accept him as leader
    plus an unowned "EVERY-ONE!" shout. The writer gave the unowned line to Kim Sangshik
    and dropped Song Chi-yul, so the next beat's "he accepts the choice" had no
    antecedent — the election never happened anywhere in the script."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SceneCard, SeriesBible
    from manhwa2vid.script.lint import lint_dropped_speakers

    bible = SeriesBible(
        series_slug="s",
        title="S",
        protagonist_id="char_mc",
        characters={
            "char_mc": CharacterProfile(id="char_mc", canonical_name="Sung Jin-Woo", tier=CharacterTier.MAIN),
            "char_song": CharacterProfile(id="char_song", canonical_name="Song Chi-yul", tier=CharacterTier.MAIN),
        },
    )
    cards = [
        SceneCard(
            panel_ids=["p0023_01"],
            source_text='Song Chi-yul -> the raid party: "I\'D LIKE TO LEAD."',
            action="Song Chi-yul addresses the group.",
        )
    ]
    beats = [ScriptBeat(beat_id=16, panel_ids=["p0023_01"], narration="Kim Sangshik calls to the others near the Gate.")]
    assert lint_dropped_speakers(beats, cards, bible) == {16: ["dropped_speaker:Song Chi-yul"]}

    ok = [ScriptBeat(beat_id=16, panel_ids=["p0023_01"], narration="Song Chi-yul asks the party to accept him as leader.")]
    assert lint_dropped_speakers(ok, cards, bible) == {}


def test_lint_dropped_speakers_exempts_the_protagonist():
    """The MC is carried by pronoun for stretches by design; anchoring cadence is
    enforce_mc_name_budget's job, not this lint's."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SceneCard, SeriesBible
    from manhwa2vid.script.lint import lint_dropped_speakers

    bible = SeriesBible(
        series_slug="s",
        title="S",
        protagonist_id="char_mc",
        characters={"char_mc": CharacterProfile(id="char_mc", canonical_name="Sung Jin-Woo", tier=CharacterTier.MAIN)},
    )
    cards = [SceneCard(panel_ids=["p1"], source_text='Sung Jin-Woo: "HAAH"', action="He gasps.")]
    beats = [ScriptBeat(beat_id=2, panel_ids=["p1"], narration="He gasps for air as the spear falls.")]
    assert lint_dropped_speakers(beats, cards, bible) == {}


def test_humanize_issues_explains_dropped_speaker():
    from manhwa2vid.script.lint import _humanize_issues

    text = _humanize_issues(["dropped_speaker:Song Chi-yul"])
    assert "Song Chi-yul" in text and "never appears" in text
    assert _humanize_issues(["aside_overuse"]) == "aside_overuse"


def test_strip_appearance_descriptors_collapses_extras():
    """Observed: 'A hunter with a fur collar and another in a green jacket quickly chime
    in.' The evidence labels extras by clothing and the writer passes it straight through,
    against rules 3 and 5 both."""
    from manhwa2vid.script.lint import strip_appearance_descriptors

    beats = [ScriptBeat(beat_id=1, panel_ids=["p"], narration="A hunter with a fur collar and another in a green jacket quickly chime in.")]
    assert strip_appearance_descriptors(beats)[0].narration == "A hunter and another quickly chime in."


def test_strip_appearance_descriptors_trims_intro_to_role():
    """Rule 4 wants name + role clause, like the gold's 'the party's rookie healer'."""
    from manhwa2vid.script.lint import strip_appearance_descriptors

    beats = [ScriptBeat(beat_id=1, panel_ids=["p"], narration="Kim Sangshik, a veteran hunter in a blue jacket, waits nearby.")]
    assert strip_appearance_descriptors(beats)[0].narration == "Kim Sangshik, a veteran hunter, waits nearby."


def test_strip_appearance_descriptors_leaves_places_alone():
    from manhwa2vid.script.lint import strip_appearance_descriptors

    text = "He walks into a construction site in the city center."
    beats = [ScriptBeat(beat_id=1, panel_ids=["p"], narration=text)]
    assert strip_appearance_descriptors(beats)[0].narration == text


def test_lock_transition_line_replaces_embellished_wording():
    """The return to the present is the most audible line in the recap, and the model
    rewrote the exemplar into 'Away from the trials of him, the sky clears over the
    peaceful bridges of present-day Seoul.'"""
    from manhwa2vid.script.lint import lock_transition_line

    config = {"script": {"transition_line": "Then the sky clears, over present-day Seoul."}}
    beats = [
        ScriptBeat(beat_id=2, panel_ids=["p0007_01"], narration="He grits his teeth. Away from the trials of him, the sky clears over the peaceful bridges of present-day Seoul."),
        ScriptBeat(beat_id=3, panel_ids=["p0008_01"], narration="He walks through the crowd."),
    ]
    out = lock_transition_line(beats, "p0007_01", config)
    assert out[0].narration == "He grits his teeth. Then the sky clears, over present-day Seoul."
    assert out[1].narration == "He walks through the crowd."


def test_lock_transition_line_is_opt_in():
    """Empty config leaves every series that has not approved a line untouched."""
    from manhwa2vid.script.lint import lock_transition_line

    beats = [ScriptBeat(beat_id=2, panel_ids=["p1"], narration="The sky clears over present-day Seoul.")]
    assert lock_transition_line(beats, "p1", {})[0].narration == "The sky clears over present-day Seoul."


def test_dedupe_cross_beat_sentences_drops_near_verbatim_restatement():
    from manhwa2vid.script.lint import dedupe_cross_beat_sentences

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="Jin-Woo asks the vendor for a cup of coffee."),
        ScriptBeat(beat_id=2, panel_ids=["p2"], narration="Jin-Woo asks the vendor for a cup of coffee. Lee Joo-hee spots him from across the lot."),
    ]
    out = dedupe_cross_beat_sentences(beats)
    assert out[1].narration == "Lee Joo-hee spots him from across the lot."


def test_dedupe_cross_beat_sentences_never_empties_a_beat():
    from manhwa2vid.script.lint import dedupe_cross_beat_sentences

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="Jin-Woo asks the vendor for coffee."),
        ScriptBeat(beat_id=2, panel_ids=["p2"], narration="Jin-Woo asks the vendor for coffee."),
    ]
    assert dedupe_cross_beat_sentences(beats)[1].narration.strip()


def test_dedupe_cross_beat_sentences_leaves_paraphrase_alone():
    """Deliberate scope limit. The observed coffee repetition scores 0.29 overlap, so a
    threshold that caught it would delete correct sentences elsewhere. Paraphrased
    repetition stays a warn-only style finding, not a silent deletion."""
    from manhwa2vid.script.lint import dedupe_cross_beat_sentences

    second = "He sighs in disappointment when he learns there is no coffee left for him."
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="He sighs at the old men and asks for coffee."),
        ScriptBeat(beat_id=2, panel_ids=["p2"], narration=second),
    ]
    assert dedupe_cross_beat_sentences(beats)[1].narration == second


def test_lock_transition_line_removes_a_second_rewind_sentence():
    """The model wrote the shift twice: 'Quiet bridges now span the wide river under the
    distant skyline of Seoul.' immediately before the locked line."""
    from manhwa2vid.script.lint import lock_transition_line

    config = {"script": {"transition_line": "Then the sky clears, over present-day Seoul."}}
    beats = [
        ScriptBeat(
            beat_id=2,
            panel_ids=["p1"],
            narration="A blinding flash erupts. Quiet bridges now span the wide river under the distant skyline of Seoul. Then the sky clears, over present-day Seoul.",
        )
    ]
    assert lock_transition_line(beats, "p1", config)[0].narration == (
        "A blinding flash erupts. Then the sky clears, over present-day Seoul."
    )


def test_strip_appearance_descriptors_consumes_chained_descriptors():
    """Stripping only the first garment phrase left a dangling conjunction: "a supporting
    hunter with a goatee and grey hair" -> "a supporting hunter and grey hair"."""
    from manhwa2vid.script.lint import strip_appearance_descriptors

    beats = [ScriptBeat(beat_id=1, panel_ids=["p"], narration="Kim Sangshik, a supporting hunter with a goatee and grey hair, waits.")]
    assert strip_appearance_descriptors(beats)[0].narration == "Kim Sangshik, a supporting hunter, waits."


def test_strip_repeated_appositives_catches_sentence_final_intros():
    """An appositive ending a SENTENCE has no trailing comma, so a second introduction
    survived: "Bak waves to Kim Sangshik, a middle-aged hunter."."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import strip_repeated_appositives

    bible = SeriesBible(
        series_slug="s",
        title="S",
        protagonist_id="char_mc",
        characters={"char_kim": CharacterProfile(id="char_kim", canonical_name="Kim Sangshik", tier=CharacterTier.MAIN)},
    )
    beats = [
        ScriptBeat(beat_id=4, panel_ids=["a"], narration="Kim Sangshik, a supporting hunter, waits near a food truck."),
        ScriptBeat(beat_id=6, panel_ids=["b"], narration="Bak waves enthusiastically to Kim Sangshik, a middle-aged hunter."),
    ]
    out = strip_repeated_appositives(beats, bible)
    assert out[1].narration == "Bak waves enthusiastically to Kim Sangshik."


def test_fix_pronoun_case_repairs_object_pronoun_in_subject_position():
    """Observed: "warns Bak to stop before him hears"."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import fix_pronoun_case

    bible = SeriesBible(
        series_slug="s",
        title="S",
        protagonist_id="char_mc",
        characters={"char_mc": CharacterProfile(id="char_mc", canonical_name="Sung Jin-Woo", tier=CharacterTier.MAIN)},
    )
    assert fix_pronoun_case("Kim warns Bak to stop before him hears.", bible) == (
        "Kim warns Bak to stop before he hears."
    )
    # The same words are prepositions elsewhere, where the object form is correct.
    assert fix_pronoun_case("He walks away after her.", bible) == "He walks away after her."
    assert fix_pronoun_case("Jin-Woo leaves before him.", bible) == "Jin-Woo leaves before him."
    # "her" doubles as a possessive determiner, so it is left alone entirely.
    assert fix_pronoun_case("He grins while her hands shake.", bible) == "He grins while her hands shake."


def test_fix_pronoun_case_handles_base_form_verbs():
    """"the youth joined right after him quit" — a base-form verb has no suffix for
    _looks_like_verb to see, so the subject-position repair missed it."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import fix_pronoun_case

    bible = SeriesBible(
        series_slug="s",
        title="S",
        protagonist_id="char_mc",
        characters={"char_mc": CharacterProfile(id="char_mc", canonical_name="Sung Jin-Woo", tier=CharacterTier.MAIN)},
    )
    assert fix_pronoun_case("He tells Bak the youth joined right after him quit.", bible) == (
        "He tells Bak the youth joined right after he quit."
    )
    assert fix_pronoun_case("Jin-Woo leaves before him.", bible) == "Jin-Woo leaves before him."


def test_strip_appearance_descriptors_covers_definite_phrases():
    """"Song Chi-yul, the veteran party leader with short gray hair" kept its hair: only
    indefinite phrases matched, and "leader" was missing from the person nouns."""
    from manhwa2vid.script.lint import strip_appearance_descriptors

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p"], narration="Song Chi-yul, the veteran party leader with short gray hair, calls for attention."),
        ScriptBeat(beat_id=2, panel_ids=["q"], narration="Jin-Woo asks the coffee vendor in a blue cap for a warm drink."),
    ]
    out = strip_appearance_descriptors(beats)
    assert out[0].narration == "Song Chi-yul, the veteran party leader, calls for attention."
    assert out[1].narration == "Jin-Woo asks the coffee vendor for a warm drink."


def test_strip_appearance_descriptors_keeps_role_clauses():
    """Rule 4's role clause is the target format, not collateral damage."""
    from manhwa2vid.script.lint import strip_appearance_descriptors

    text = "Lee Joo-hee, the party's rookie healer, rushes over."
    beats = [ScriptBeat(beat_id=1, panel_ids=["p"], narration=text)]
    assert strip_appearance_descriptors(beats)[0].narration == text


def test_trim_overlong_trims_the_closer_from_the_front():
    """The closer's final sentences are the chapter's ending; tail-trimming once deleted
    a seal-reveal the writer had correctly landed."""
    from manhwa2vid.script.lint import trim_overlong_beats

    long_tail = (
        "He sits down before the statues. He pours four cups and toasts his friends. "
        "He remembers the years they fought together side by side in the cold. "
        "He brushes the dust from the ice with one hand. "
        "A system message says the seal on his friends can be removed."
    )
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="An opening beat."),
        ScriptBeat(beat_id=2, panel_ids=["p2"], narration=long_tail),
    ]
    config = {"script": {"words_per_panel_target": 14, "max_beat_words": 30}}
    out = trim_overlong_beats(beats, config)
    assert "seal" in out[1].narration  # the ending survives
    assert "sits down" not in out[1].narration  # the lead-in is what got cut


def test_lint_closer_reveal_flags_a_missing_ending():
    from manhwa2vid.models import SceneCard
    from manhwa2vid.script.lint import lint_closer_reveal

    cards = [
        SceneCard(panel_ids=["p0001_01"], source_text='A: "HELLO."', action=""),
        SceneCard(panel_ids=["p0024_01"], source_text='sys: "[SEAL CAN BE REMOVED.]"', action=""),
    ]
    beats = [ScriptBeat(beat_id=1, panel_ids=["p0024_01"], narration="He drinks quietly with his frozen friends.")]
    report = lint_closer_reveal(beats, cards)
    assert 1 in report and report[1][0].startswith("dropped_reveal:")

    ok = [ScriptBeat(beat_id=1, panel_ids=["p0024_01"], narration="A message says the seal can be removed.")]
    assert lint_closer_reveal(ok, cards) == {}


def test_trailing_closer_is_flagged_and_stripped():
    """Observed SL closer: '...remains to be seen.' The closer is the one beat a viewer
    hears to the end, and rule 10's 'no trailing off' keeps being declined."""
    from manhwa2vid.script.lint import lint_trailing_closer, strip_trailing_closer_sentence

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"], narration="He steps into the gate."),
        ScriptBeat(
            beat_id=2, panel_ids=["p2"],
            narration="He takes a deep breath and steps into the swirling light. "
                      "Whether he will clear the raid without injury remains to be seen.",
        ),
    ]
    assert lint_trailing_closer(beats) == {2: ["trailing_closer"]}
    out = strip_trailing_closer_sentence(beats)
    assert out[1].narration == "He takes a deep breath and steps into the swirling light."
    assert lint_trailing_closer(out) == {}


def test_trailing_closer_never_empties_a_one_sentence_beat():
    from manhwa2vid.script.lint import strip_trailing_closer_sentence

    beats = [ScriptBeat(beat_id=1, panel_ids=["p1"], narration="Only time will tell.")]
    assert strip_trailing_closer_sentence(beats)[0].narration == "Only time will tell."


def test_strong_closer_is_untouched():
    from manhwa2vid.script.lint import lint_trailing_closer

    beats = [ScriptBeat(beat_id=1, panel_ids=["p1"], narration="Hunting is a job where your life is on the line, and today is a work day.")]
    assert lint_trailing_closer(beats) == {}


def test_trailing_closer_catches_reworded_question_openers():
    """The first fix moved the defect rather than removing it: the rewritten closer read
    'Whether he will survive the new raid is the only question worth asking.' A final
    sentence that OPENS on 'Whether' poses a question instead of landing an event."""
    from manhwa2vid.script.lint import lint_trailing_closer, strip_trailing_closer_sentence

    beats = [
        ScriptBeat(
            beat_id=1, panel_ids=["p1"],
            narration="Jin-Woo resolves to do his best as he and Lee Joo-hee enter the gate. "
                      "Whether he will survive the new D-rank dungeon raid is the only question worth asking.",
        )
    ]
    assert lint_trailing_closer(beats) == {1: ["trailing_closer"]}
    out = strip_trailing_closer_sentence(beats)
    assert out[0].narration.endswith("enter the gate.")


def test_closer_check_leaves_a_declarative_ending_alone():
    from manhwa2vid.script.lint import lint_trailing_closer

    beats = [ScriptBeat(beat_id=1, panel_ids=["p1"], narration="He enters the gate. Today is a work day.")]
    assert lint_trailing_closer(beats) == {}


def test_lint_and_rewrite_preserves_key_panel_ids(monkeypatch, tmp_path):
    """Every beat passes through lint_and_rewrite_script; its field-by-field beat
    reconstruction silently wiped key_panel_ids on all 28 beats of a live run. Fields
    must survive code that predates them."""
    from manhwa2vid.script.lint import lint_and_rewrite_script

    beats = [
        ScriptBeat(
            beat_id=1, panel_ids=["p0001_01", "p0001_02"],
            narration="A clean sentence with nothing to flag.",
            key_panel_ids=["p0001_02"],
        )
    ]
    from manhwa2vid.models import SeriesBible

    bible = SeriesBible(series_slug="s", title="S")
    out = lint_and_rewrite_script(beats, bible, tmp_path / "missing.json", {"characters": {}})
    assert out[0].key_panel_ids == ["p0001_02"]


def test_derive_key_panels_from_narration_overlap():
    """Self-reported key_panels vanish under long-output pressure; the narration itself
    shows which panels it used, so derivation is deterministic."""
    from manhwa2vid.models import SceneCard
    from manhwa2vid.script.lint import derive_key_panels

    cards = [
        SceneCard(panel_ids=["p1"], source_text='Kim: "THE SEAL CAN BE REMOVED."', action="Kim reads the message"),
        SceneCard(panel_ids=["p2"], source_text="", action="a wide empty hallway"),
        SceneCard(panel_ids=["p3"], source_text='Bak: "LET US DRINK."', action="Bak raises a cup"),
    ]
    beats = [
        ScriptBeat(
            beat_id=1, panel_ids=["p1", "p2", "p3"],
            narration="Kim reads the message that the seal can be removed, and Bak raises a cup to drink.",
        )
    ]
    out = derive_key_panels(beats, cards)
    assert "p1" in out[0].key_panel_ids and "p3" in out[0].key_panel_ids
    assert "p2" not in out[0].key_panel_ids

    # writer-provided keys are never overridden
    manual = [ScriptBeat(beat_id=1, panel_ids=["p1", "p2"], narration="anything", key_panel_ids=["p2"])]
    assert derive_key_panels(manual, cards)[0].key_panel_ids == ["p2"]


def test_dedupe_appositive_clauses_all_observed_forms():
    """The four observed forms of the stamped clause: triple-in-one-sentence, repeat in
    a later beat, comma-welded residue, and article-swapped 'another …'."""
    from manhwa2vid.script.lint import dedupe_appositive_clauses

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p"], narration=(
            "When Skaya, a member of the original five heroes, currently frozen in ice, "
            "spoke, Khali, a member of the original five heroes, currently frozen in ice, nodded."
        )),
        ScriptBeat(beat_id=2, panel_ids=["p"], narration=(
            "The Swordswoman, a member of the original five heroes, currently frozen in ice, agrees."
        )),
        ScriptBeat(beat_id=3, panel_ids=["p"], narration=(
            "The Marksman currently frozen in ice, admits they might."
        )),
        ScriptBeat(beat_id=4, panel_ids=["p"], narration=(
            "He touches the cold statue of The Swordswoman, another member of the original five heroes currently frozen in ice."
        )),
        ScriptBeat(beat_id=5, panel_ids=["p"], narration=(
            "Lee Joo-hee, the party's rookie healer, snaps at him. Kim, a veteran hunter, waves."
        )),
    ]
    out = dedupe_appositive_clauses(beats)
    full = " ".join(b.narration for b in out)
    assert full.count("member of the original five heroes") == 1  # first kept, all others gone
    assert "currently frozen in ice, Khali" not in out[0].narration
    assert out[1].narration == "The Swordswoman agrees."
    assert out[2].narration == "The Marksman admits they might."
    assert out[3].narration == "He touches the cold statue of The Swordswoman."
    assert out[4].narration == beats[4].narration  # distinct legit appositives untouched


def test_appositive_regex_spans_inner_comma():
    """Stripping a comma-embedded clause must consume the WHOLE clause — the old regex
    stopped at the first inner comma and welded 'currently frozen in ice,' to the name."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import strip_repeated_appositives

    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="char_mc",
        characters={"char_m": CharacterProfile(id="char_m", canonical_name="The Marksman", tier=CharacterTier.SUPPORTING)},
    )
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p"], narration="The Marksman, a member of the five heroes, currently frozen in ice, waves."),
        ScriptBeat(beat_id=2, panel_ids=["p"], narration="The Marksman, a member of the five heroes, currently frozen in ice, admits defeat."),
    ]
    # Production order: the text-keyed dedupe runs FIRST and removes the exact repeat,
    # so the per-name strip never faces the multi-comma form (which is syntactically
    # ambiguous with "appositive + verb clause" and cannot be solved by regex alone).
    from manhwa2vid.script.lint import dedupe_appositive_clauses

    out = strip_repeated_appositives(dedupe_appositive_clauses(beats), bible)
    assert out[1].narration == "The Marksman admits defeat."
    assert "frozen in ice, admits" not in out[1].narration


def test_rotation_keeps_name_after_gerund():
    """"the monument containing Seo Jun-Ho is beginning to crack": prior participle +
    next-word finite verb shipped 'containing he'. The uncertain slot keeps the name."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import rotate_protagonist_name

    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="char_mc",
        characters={"char_mc": CharacterProfile(id="char_mc", canonical_name="Seo Jun-Ho", tier=CharacterTier.MAIN, pronoun="he")},
    )
    t = "The presenter is unaware that the monument containing Seo Jun-Ho is beginning to crack."
    out = rotate_protagonist_name(t, bible, keep=0)
    assert "containing he" not in out
    assert "Seo Jun-Ho" in out or "Jun-Ho" in out


def test_beat_word_cap_chapter_budget():
    from manhwa2vid.script.lint import beat_word_cap

    config = {"script": {"words_per_panel_target": 14, "max_beat_words": 60, "words_per_chapter": 550}}
    # panel-rich beat, 28 beats over 2 chapters: chapter share wins over the 60 ceiling
    assert beat_word_cap(12, config, n_beats=28, n_chapters=2) == round(550 * 2 / 28 * 1.2)
    # few panels: panel budget wins
    assert beat_word_cap(1, config, n_beats=28, n_chapters=2) == 16
    # no beat count: old behavior
    assert beat_word_cap(12, config) == 60


def test_grammar_pass_with_fake_tool():
    """Single-replacement grammar findings auto-apply; multi-candidate ones route to the
    rewrite as issues. No Java needed — the tool is injected."""
    from manhwa2vid.script.grammar import grammar_pass

    class Match:
        def __init__(self, offset, length, reps, issue="grammar", msg="agreement"):
            self.offset, self.error_length = offset, length
            self.replacements, self.rule_issue_type = reps, issue
            self.message, self.rule_id = msg, "X"

    class FakeTool:
        def check(self, text):
            out = []
            i = text.find("containing he")
            if i >= 0:
                out.append(Match(i + len("containing "), 2, ["him"]))
            j = text.find("badstyle")
            if j >= 0:
                out.append(Match(j, 8, ["s1", "s2"]))
            k = text.find("stylish")
            if k >= 0:
                out.append(Match(k, 7, ["x"], issue="style"))
            return out

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p"], narration="the monument containing he is cracking"),
        ScriptBeat(beat_id=2, panel_ids=["p"], narration="this is badstyle indeed"),
        ScriptBeat(beat_id=3, panel_ids=["p"], narration="a stylish sentence"),
    ]
    out, issues = grammar_pass(beats, FakeTool())
    assert out[0].narration == "the monument containing him is cracking"
    assert 2 in issues and issues[2][0].startswith("grammar:")
    assert 3 not in issues  # style category ignored wholesale
    assert grammar_pass(beats, None) == (beats, {})


def test_intro_role_truncates_state_dossiers():
    from manhwa2vid.script.synopsis import _intro_role

    assert _intro_role("A member of the original five heroes, currently frozen in ice.") == (
        "A member of the original five heroes"
    )
    assert _intro_role("the party's rookie healer") == "the party's rookie healer"
    assert _intro_role("") == ""


def test_closer_reveal_strict_mode_for_system_message_endings():
    """A closer narrating only the FAILURE half passed on the single word 'seal' while
    the reveal (the seal CAN be removed) was gone. Bracketed system messages demand
    >=2 content terms; plain-dialogue endings keep the lenient check."""
    from manhwa2vid.models import SceneCard
    from manhwa2vid.script.lint import lint_closer_reveal

    cards = [
        SceneCard(panel_ids=["p0024_01"], source_text='sys: "[YOU ARE ABLE TO REMOVE THE SEAL ON THE ICE STATUS.]"', action=""),
        SceneCard(panel_ids=["p0024_03"], source_text='"WHAT?!"', action=""),
    ]
    bad = [ScriptBeat(beat_id=1, panel_ids=["p0024_01"], narration="His stats fail to melt her seal.")]
    assert 1 in lint_closer_reveal(bad, cards)
    good = [ScriptBeat(beat_id=1, panel_ids=["p0024_01"], narration="A message says his skill can remove the seal on their icy status.")]
    assert lint_closer_reveal(good, cards) == {}
    dialogue = [SceneCard(panel_ids=["p1"], source_text='All: "LET US ENTER THE DUNGEON!"', action="")]
    sl = [ScriptBeat(beat_id=1, panel_ids=["p1"], narration="He steps into the dungeon gate.")]
    assert lint_closer_reveal(sl, dialogue) == {}


def test_dual_role_subordinator_keeps_the_name():
    """Shipped: "the presenter dismisses him just before him violently shatters his
    frozen prison." "before" is both a preposition and a subordinating conjunction; when
    a finite verb follows, the slot is a SUBJECT and the object-cue arm is wrong. An
    adverb between the two hid the verb from the next-word test."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import rotate_protagonist_name

    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="char_mc",
        characters={"char_mc": CharacterProfile(
            id="char_mc", canonical_name="Seo Jun-Ho", tier=CharacterTier.MAIN, pronoun="he")},
    )
    out = rotate_protagonist_name(
        "the presenter dismisses him just before Seo Jun-Ho violently shatters his prison.",
        bible, keep=0)
    assert "before him violently" not in out

    # no adverb in the way — same rule
    assert "before him shatters" not in rotate_protagonist_name(
        "he waits before Seo Jun-Ho shatters the ice.", bible, keep=0)

    # genuine prepositional object still rotates
    assert "after him" in rotate_protagonist_name("Skaya walks in after Seo Jun-Ho.", bible, keep=0)
    assert "tells him" in rotate_protagonist_name("Deok-gu tells Seo Jun-Ho the truth.", bible, keep=0)


def test_dedupe_catches_possessive_led_appositives():
    """Shipped three times untouched: "Deok-gu, Jun-Ho's old friend and the current
    Player Association president". The clause is led by a possessive, not an article, so
    the span regex never saw it."""
    from manhwa2vid.script.lint import dedupe_appositive_clauses

    clause = "Jun-Ho's old friend and the current Player Association president"
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p"], narration=f"Deok-gu, {clause} enters."),
        ScriptBeat(beat_id=2, panel_ids=["p"], narration=f"Deok-gu, {clause}, explains ten floors."),
        ScriptBeat(beat_id=3, panel_ids=["p"], narration=f"Deok-gu, {clause}, admits it."),
    ]
    out = dedupe_appositive_clauses(beats)
    assert sum(1 for b in out if "old friend and the current" in b.narration) == 1
    assert out[1].narration == "Deok-gu explains ten floors."
    assert out[2].narration == "Deok-gu admits it."


def test_dedupe_appositive_clauses_spares_correct_prose():
    """Regression: the remover must never delete a clause that is not a repeated
    appositive. Two heuristics did, and one SHIPPED — a shape test reading "first word
    ends in -en means participle" deleted "queen dissipates into light," from beat 4 of
    the frozen-player draft, because QUEEN ends in -en. The trigger is now ledger
    membership only, and these are the forms that must survive it."""
    from manhwa2vid.script.lint import dedupe_appositive_clauses

    safe = [
        "The queen dissipates into light, admitting she enjoyed their final struggle.",
        "The presenter proudly displays the statues, revealing the frozen five heroes.",
        "He grips the hilt tightly, knowing the gate will open at dawn.",
        "Lee Joo-hee, the party's rookie healer, snaps. Kim, a veteran hunter, waves.",
    ]
    beats = [ScriptBeat(beat_id=i + 1, panel_ids=["p"], narration=t) for i, t in enumerate(safe)]
    assert [b.narration for b in dedupe_appositive_clauses(beats)] == safe


def test_dedupe_appositive_keeps_first_occurrence_whole():
    """The FIRST occurrence keeps every segment AND its closing comma. Both later passes
    (bare-variant, weld) once re-matched the second segment of the span pass 1 had just
    kept, yielding "Skaya, a member of the five heroes speaks first." — the appositive
    silently promoted to subject."""
    from manhwa2vid.script.lint import dedupe_appositive_clauses

    out = dedupe_appositive_clauses([
        ScriptBeat(beat_id=1, panel_ids=["p"],
                   narration="Skaya, a member of the five heroes, currently frozen in ice, speaks first."),
        ScriptBeat(beat_id=2, panel_ids=["p"],
                   narration="Khali, a member of the five heroes, currently frozen in ice, nods."),
    ])
    assert out[0].narration == "Skaya, a member of the five heroes, currently frozen in ice, speaks first."
    assert out[1].narration == "Khali nods."


def test_appositive_span_stops_before_resuming_verb():
    """The span may cross ONE inner comma and no more: the third segment is where the
    main sentence resumes, often with an irregular past ("..., spoke, Khali nodded")
    that no suffix test recognises as a verb. Pins _MAX_APPOSITIVE_SEGMENTS."""
    from manhwa2vid.script.lint import _iter_appositive_spans

    text = ("When Skaya, a member of the original five heroes, currently frozen in ice, "
            "spoke, Khali nodded.")
    spans = list(_iter_appositive_spans(text))
    assert len(spans) == 1
    assert spans[0][2] == "a member of the original five heroes, currently frozen in ice"
    assert "spoke" not in spans[0][2]


def test_repair_subject_comma_spares_closing_appositive_comma():
    """Regression, shipped: the match lands on the LAST WORD OF THE APPOSITIVE, not the
    subject, so "Lee Joo-hee, the party's healer, arrives" was rewritten to "...healer
    arrives". The model had punctuated both beats correctly and the polish pass broke
    them. An earlier comma in the sentence means this one closes a clause."""
    from manhwa2vid.script.lint import repair_subject_comma

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p"],
                   narration="Lee Joo-hee, the party's healer, arrives in a panic."),
        ScriptBeat(beat_id=2, panel_ids=["p"],
                   narration="Song Chi-yul, the party leader, steps forward."),
        ScriptBeat(beat_id=3, panel_ids=["p"], narration="Seo Jun-Ho, stands in the hall."),
        ScriptBeat(beat_id=4, panel_ids=["p"], narration="He nods. Rell, walks away."),
    ]
    out = [b.narration for b in repair_subject_comma(beats)]
    assert out[0] == "Lee Joo-hee, the party's healer, arrives in a panic."
    assert out[1] == "Song Chi-yul, the party leader, steps forward."
    assert out[2] == "Seo Jun-Ho stands in the hall."       # real splice still repaired
    assert out[3] == "He nods. Rell walks away."             # splice after a sentence end


def test_lint_time_shift_marker_requires_a_spoken_cue():
    """A viewer HEARS narration. On the page a white flash plus new scenery reads as a
    flashback; spoken over the same panels it is just the next sentence. Solo Leveling
    ch1 shipped the jump home purely visually and a listener could not tell time had
    moved."""
    from manhwa2vid.script.lint import lint_time_shift_marker

    plot = {2: "The scene shifts to the present day in Seoul, where he walks a crosswalk.",
            3: "He heads toward the construction site."}
    beats = [
        ScriptBeat(beat_id=2, panel_ids=["p"], narration=(
            "A blinding flash consumes the dungeon. The river flows peacefully under the "
            "morning sun.")),
        ScriptBeat(beat_id=3, panel_ids=["p"], narration="He heads toward the site."),
    ]
    assert sorted(lint_time_shift_marker(beats, plot)) == [2]

    fixed = [beats[0].model_copy(update={"narration": (
        "A blinding flash consumes the dungeon. Hours earlier, the river flows peacefully "
        "under the morning sun.")}), beats[1]]
    assert lint_time_shift_marker(fixed, plot) == {}


def test_lint_repeated_setting_needs_a_real_modifier_chain():
    """Describe a place once. The article of a DIFFERENT noun must not anchor the match:
    "A shout from the Gate" captured "shout from the" as modifiers and flagged a beat
    that describes nothing."""
    from manhwa2vid.script.lint import lint_repeated_setting

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p"],
                   narration="He nears a swirling blue dungeon Gate behind the scaffolding."),
        ScriptBeat(beat_id=2, panel_ids=["p"],
                   narration="A shout from the Gate draws their attention."),
        ScriptBeat(beat_id=3, panel_ids=["p"],
                   narration="The party gathers at a glowing blue magical Gate."),
    ]
    flagged = lint_repeated_setting(beats, ["Gate"])
    assert sorted(flagged) == [3]          # 1 establishes it, 2 is a bare reference
    assert "beat 1" in flagged[3][0]


def test_lint_hook_grounding_flags_invented_specifics():
    """The hook is the first line a viewer hears and has no panel binding of its own.
    ch1's promised "a D-rank gate" — D-rank appears in no panel of that chapter."""
    from manhwa2vid.script.lint import lint_hook_grounding

    evidence = "E-RANK HUNTER. the hunter guild's lowest rank a blue gate in seoul"
    assert lint_hook_grounding("He steps through a D-rank gate in Seoul.", evidence) == ["d-rank"]
    assert lint_hook_grounding("He steps through an E-rank gate in Seoul.", evidence) == []


def test_lint_contentless_report_flags_reports_with_no_content():
    """"Kim Sangshik tells Bak." — tells him WHAT. Syntactically complete, so
    repair_truncated_sentences passes it and LanguageTool calls it clean, while the point
    of the sentence is simply gone. Two shipped in one ch1 draft."""
    from manhwa2vid.script.lint import lint_contentless_report

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p"], narration="Kim Sangshik tells Bak."),
        ScriptBeat(beat_id=2, panel_ids=["p"],
                   narration="Jin-Woo smiles weakly and tells Lee Joo-hee."),
        ScriptBeat(beat_id=3, panel_ids=["p"],
                   narration="Kim tells Bak that the dungeon will be easy today."),
        ScriptBeat(beat_id=4, panel_ids=["p"], narration="She tells him the truth about the raid."),
    ]
    flagged = lint_contentless_report(beats)
    assert sorted(flagged) == [1, 2]


def test_strip_internal_labels_keeps_the_label_when_it_is_the_subject():
    """A PRECEDING comma does not make a label an appositive. "Now, the protagonist walks
    safely through the crosswalk" opens with a sentence adverbial; deleting the label
    there left "Now, walks safely", which repair_subject_comma then tidied into the
    headless "Now walks safely". Two correct steps, one destroyed sentence."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import repair_subject_comma, strip_internal_labels

    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="char_mc",
        characters={"char_mc": CharacterProfile(
            id="char_mc", canonical_name="Sung Jin-Woo", tier=CharacterTier.MAIN)},
    )
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p"],
                   narration="Now, the protagonist walks safely through a crowded crosswalk."),
        ScriptBeat(beat_id=2, panel_ids=["p"],
                   narration="The protagonist walks away from the stall."),
    ]
    out = [b.narration for b in repair_subject_comma(strip_internal_labels(beats, bible))]
    assert out[0] == "Now, Jin-Woo walks safely through a crowded crosswalk."
    assert out[1] == "Jin-Woo walks away from the stall."


def test_lock_transition_line_placed_where_the_shift_happens():
    """The cue must not arrive after the thing it marks. Appending unconditionally put it
    at the END of a beat whose FIRST panel was the last flashforward frame, so three
    panels of present-day narration played before the line announcing the return."""
    from manhwa2vid.script.lint import lock_transition_line

    line = "The story returns to a sunny day in the city of Seoul."
    front = lock_transition_line(
        [ScriptBeat(beat_id=3, panel_ids=["p0008_01", "p0008_02", "p0009_01", "p0009_02"],
                    narration="He walks a crowded crosswalk. He thinks the job risks his life. Cars pass.")],
        "p0008_01", {}, line)[0].narration
    assert front.startswith(line)

    back = lock_transition_line(
        [ScriptBeat(beat_id=2, panel_ids=["p0005_01", "p0006_01", "p0008_01"],
                    narration="A sentinel strikes. He grits his teeth. The vision vanishes.")],
        "p0008_01", {}, line)[0].narration
    assert back.endswith(line)


def test_lock_transition_line_keeps_itself_when_placed_early():
    """The destination-dedup kept "the last sentence", which was the locked line only
    while it was always appended. Once placement follows the panel, an early-placed line
    names the destination and the filter deleted the sentence it existed to preserve."""
    from manhwa2vid.script.lint import lock_transition_line

    line = "The story returns to a sunny day in the city of Seoul."
    out = lock_transition_line(
        [ScriptBeat(beat_id=3, panel_ids=["p0008_01", "p0009_01"],
                    narration="Quiet bridges span the river under the skyline of Seoul. He walks on.")],
        "p0008_01", {}, line)[0].narration
    assert line in out                      # survived
    assert "Quiet bridges" not in out       # the model's restatement went


def test_lint_malformed_phrases_catches_rewrite_wreckage():
    """Two shapes grammatical enough to survive every other net, both shipped from
    REWRITES: a determiner and its modifier outliving the name they belonged to, and two
    anonymous agents flattened onto one descriptor so the sentence identifies nobody."""
    from manhwa2vid.script.lint import lint_malformed_phrases

    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p"], narration="A dejected he walks away from the stall."),
        ScriptBeat(beat_id=2, panel_ids=["p"], narration="A hunter and a hunter both shout agreement."),
        ScriptBeat(beat_id=3, panel_ids=["p"], narration="A dejected Jin-Woo walks away from the stall."),
        ScriptBeat(beat_id=4, panel_ids=["p"], narration="A hunter and a vendor both shout."),
        # Object pronoun: article, two words, pronoun — matches the shape, is correct.
        ScriptBeat(beat_id=5, panel_ids=["p"], narration="The healer treats him after the raid."),
        # A conjunction between determiner and pronoun starts a new clause, so the pronoun
        # heads THAT one. This shape flagged a correct beat until _CLAUSE_BREAKERS existed.
        ScriptBeat(beat_id=6, panel_ids=["p"],
                   narration="He tells her he is used to the pain because he is weak."),
    ]
    assert sorted(lint_malformed_phrases(beats)) == [1, 2]
