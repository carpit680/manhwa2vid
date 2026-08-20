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
