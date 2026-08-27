"""Script lint tests."""

from __future__ import annotations

import pytest

from manhwa2vid.models import ScriptBeat
from manhwa2vid.script.lint import (
    find_violations,
    lint_beats,
    lint_broken_sentences,
    repair_broken_sentences,
    sentence_fragments,
    stranded_determiner,
)


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


def test_beat_word_cap_floors_on_the_beats_dialogue_payload():
    """A 1-panel beat gets a 16-word budget from screen time alone — unsatisfiable for a
    panel printing three plot-critical lines, and below the two-sentence floor
    trim_overlong_beats refuses to cut past, so the cap decided nothing and the
    truncation point was arbitrary."""
    from manhwa2vid.script.lint import beat_word_cap

    config = {"script": {"words_per_panel_target": 14, "max_beat_words": 60, "words_per_chapter": 550}}
    assert beat_word_cap(1, config, n_beats=26, n_chapters=2) == 16
    assert beat_word_cap(1, config, n_beats=26, n_chapters=2, payload_lines=3) == 30
    # Never below what screen time already bought, and never above the ceiling.
    assert beat_word_cap(12, config, payload_lines=1) == 60
    assert beat_word_cap(1, config, n_beats=26, n_chapters=2, payload_lines=99) == 60


def test_trim_keeps_a_payoff_line_the_dialogue_gate_demands():
    """The exact Frozen Player loop: split_dense_beats isolated the panel carrying the
    altar/nucleus reveal into its own beat, the 1-panel cap trimmed both payoff sentences
    off the tail, and lint_dropped_dialogue re-flagged the beat it had just fixed — every
    round, forever. Passing the cards is what breaks the loop."""
    from manhwa2vid.models import SceneCard
    from manhwa2vid.script.lint import trim_overlong_beats

    cards = [
        SceneCard(
            panel_ids=["p0019_13"],
            action="he looks down",
            source_text=(
                'Deok-gu: "ONLY A HANDFUL OF PLAYERS THAT CAN RESIST THE HEAT OF THE MAGMA CAN EXPLORE." / '
                'Deok-gu: "WE WERE ABLE TO FIND AN ALTAR IN THE MIDDLE OF THE SEA OF LAVA." / '
                'Deok-gu: "THAT ALTAR REQUIRES THE FROST QUEEN\'S NUCLEUS TO COOL DOWN THE ENVIRONMENT."'
            ),
        ),
    ]
    landed = (
        "Deok-gu explains that only players who can resist the magma are able to explore. "
        "They found an altar in the sea of lava. "
        "It needs the Frost Queen's nucleus to cool the region."
    )
    config = {"script": {"words_per_panel_target": 14, "max_beat_words": 60, "words_per_chapter": 550}}
    beats = [ScriptBeat(beat_id=i, panel_ids=["pX"], narration="Filler one. Filler two.") for i in range(1, 26)]
    beats.insert(20, ScriptBeat(beat_id=21, panel_ids=["p0019_13"], narration=landed))

    kept = [b for b in trim_overlong_beats(beats, config, cards) if b.beat_id == 21][0].narration
    assert "nucleus" in kept, "the highest-priority payoff must survive the word cap"
    assert "altar" in kept

    # Payload-blind (the old behavior) deletes the nucleus line — the regression itself.
    blind = [b for b in trim_overlong_beats(beats, config, None) if b.beat_id == 21][0].narration
    assert "nucleus" not in blind






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
        # Zero-complementizer clause: "explains THAT he needs the money" with "that"
        # dropped. Real reported speech; flagging it sent a good beat to a rewrite.
        ScriptBeat(beat_id=5, panel_ids=["p"], narration="Bak explains he needs the money."),
        # Irregular past defeats any suffix-based verb test, so the rule is tail LENGTH:
        # only a tail short enough to be a bare listener is contentless.
        ScriptBeat(beat_id=6, panel_ids=["p"], narration="He explains Rell stole the ledger."),
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


def test_lint_abstraction_drift_needs_both_halves():
    """The "lifeless description" failure: a category word standing where the beat's own
    panels supplied a specific. Both halves of the conjunction are load-bearing — an
    action beat whose dialogue is grunts legitimately retains nothing, and an abstraction
    with no specific available is sometimes the only thing to say."""
    from manhwa2vid.models import SceneCard
    from manhwa2vid.script.lint import lint_abstraction_drift

    cards = [
        # Specifics available AND an abstraction used -> flag.
        SceneCard(panel_ids=["p1"], action="two men talk",
                  source_text='Rell -> Vesh: "MY SISTER IS SICK AND THE PASSAGE COSTS EVERYTHING."'),
        # Wordless action: nothing to retain, no abstraction -> silent.
        SceneCard(panel_ids=["p2"], action="a spear comes down", source_text='Rell: "Haah"'),
        # Abstraction used but the panel offers nothing more specific -> silent.
        SceneCard(panel_ids=["p3"], action="he waits", source_text='Rell: "..."'),
    ]
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p1"],
                   narration="Rell admits to Vesh that his financial situation got worse."),
        ScriptBeat(beat_id=2, panel_ids=["p2"],
                   narration="A spear descends as the stone giant strikes."),
        ScriptBeat(beat_id=3, panel_ids=["p3"], narration="He considers the situation."),
    ]
    flagged = lint_abstraction_drift(beats, cards)
    assert sorted(flagged) == [1]
    # The hint must name what to restore, not just score the beat.
    assert "sister" in flagged[1][0] or "passage" in flagged[1][0]


def test_lint_missing_introduction_is_the_floor_of_rule_4():
    """lint_reintroduction enforces the CEILING (no appositive after the first) and
    nothing enforced the floor, so named characters kept walking in as bare names — a
    listener meets "He tells Song Chi-yul there are no objections" never having been told
    who that is."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import lint_missing_introduction

    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="char_mc",
        characters={
            "char_mc": CharacterProfile(id="char_mc", canonical_name="Rell",
                                        tier=CharacterTier.MAIN),
            "char_a": CharacterProfile(id="char_a", canonical_name="Vesh",
                                       tier=CharacterTier.SUPPORTING, role="field medic"),
            "char_b": CharacterProfile(id="char_b", canonical_name="Doran",
                                       tier=CharacterTier.SUPPORTING, role="raid leader"),
            "char_c": CharacterProfile(id="char_c", canonical_name="Kade",
                                       tier=CharacterTier.SUPPORTING, role="scout"),
        },
    )
    beats = [
        # Appositive form: introduced.
        ScriptBeat(beat_id=1, panel_ids=["p"], narration="Vesh, the field medic, binds the wound."),
        # Premodifier form: also introduced.
        ScriptBeat(beat_id=2, panel_ids=["p"], narration="Nearby the scout Kade watches the road."),
        # Bare name, never introduced anywhere -> flagged at first mention.
        ScriptBeat(beat_id=3, panel_ids=["p"], narration="Rell tells Doran there are no objections."),
        ScriptBeat(beat_id=4, panel_ids=["p"], narration="Doran leads them through the gate."),
    ]
    flagged = lint_missing_introduction(beats, bible)
    assert sorted(flagged) == [3]                 # first mention, not every mention
    assert "Doran" in flagged[3][0]
    assert "raid leader" in flagged[3][0]         # suggests the role from the bible


def test_lint_abstraction_drift_ignores_compound_nouns():
    """A gerund before the noun makes a COMPOUND, not a category reference: "the gate
    gathering point" is a place, "his financial situation" is a category standing where a
    fact belongs. Without this the check flagged a correct beat."""
    from manhwa2vid.models import SceneCard
    from manhwa2vid.script.lint import lint_abstraction_drift

    cards = [SceneCard(panel_ids=["p1"], action="hunters gather",
                       source_text='Vesh -> Rell: "THE GATE OPENS AT DAWN AND THE PAY IS DOUBLE."')]
    beats = [ScriptBeat(beat_id=1, panel_ids=["p1"],
                        narration="A hunter welcomes Rell to the gate gathering point.")]
    assert lint_abstraction_drift(beats, cards) == {}


def test_lint_narration_order_flags_reversed_beat():
    """enforce_reading_order guarantees the invariant at BEAT level; nothing checked below
    it, so ch1 beat 12 narrated its LAST panel first and its first panel second. Read
    aloud, the words describe one moment while the art shows another."""
    from manhwa2vid.models import SceneCard
    from manhwa2vid.script.lint import lint_narration_order

    cards = [
        SceneCard(panel_ids=["p1"], action="Rell smiles weakly while explaining himself",
                  source_text='Rell -> Vesh: "IT IS ONLY BECAUSE I AM WEAK."'),
        SceneCard(panel_ids=["p2"], action="Vesh looks back in silence", source_text=""),
        SceneCard(panel_ids=["p3"], action="a shout goes up across the yard",
                  source_text='the crew: "EVERYONE!"'),
        SceneCard(panel_ids=["p4"], action="Doran addresses the gathered party",
                  source_text='Doran -> the party: "I WILL TAKE THE LEAD TODAY."'),
    ]
    span = ["p1", "p2", "p3", "p4"]
    reversed_beat = ScriptBeat(beat_id=1, panel_ids=span, narration=(
        "Doran addresses the gathered party and offers to take the lead today. "
        "Rell explains weakly to Vesh that it is only because he is weak."))
    correct_beat = ScriptBeat(beat_id=2, panel_ids=span, narration=(
        "Rell explains weakly to Vesh that it is only because he is weak. "
        "Doran addresses the gathered party and offers to take the lead today."))
    flagged = lint_narration_order([reversed_beat, correct_beat], cards)
    assert sorted(flagged) == [1]
    assert "reading order" in flagged[1][0]


def test_lint_narration_order_ignores_adjacent_swaps():
    """Lexical matching cannot resolve NEIGHBOURING panels — a scene-setting or monologue
    sentence routinely scores higher against the next panel than its own — and two
    consecutive panels sit about 2.5s apart on screen, which no viewer reads as out of
    order. Three such false positives were measured on a real draft."""
    from manhwa2vid.models import SceneCard
    from manhwa2vid.script.lint import lint_narration_order

    cards = [
        SceneCard(panel_ids=["p1"], action="Rell greets Vesh at the gate",
                  source_text='Rell -> Vesh: "IT HAS BEEN A WHILE."'),
        SceneCard(panel_ids=["p2"], action="Rell explains his wife is expecting",
                  source_text='Rell -> Vesh: "MY WIFE IS EXPECTING OUR SECOND."'),
    ]
    beats = [ScriptBeat(beat_id=1, panel_ids=["p1", "p2"], narration=(
        "Rell returns to the trade because his wife is expecting their second child. "
        "He greets Vesh at the gate before they move off."))]
    assert lint_narration_order(beats, cards) == {}


def test_lint_narration_order_ignores_unmatched_sentences():
    """A connective or scene-setting sentence matches no panel. Counting it at index 0
    would manufacture an inversion out of correct prose, so it must be skipped."""
    from manhwa2vid.models import SceneCard
    from manhwa2vid.script.lint import lint_narration_order

    cards = [
        SceneCard(panel_ids=["p1"], action="dawn over the harbour", source_text=""),
        SceneCard(panel_ids=["p2"], action="Rell boards the ferry",
                  source_text='Rell -> Vesh: "WE LEAVE BEFORE THE TIDE TURNS."'),
    ]
    beats = [ScriptBeat(beat_id=1, panel_ids=["p1", "p2"], narration=(
        "Somewhere far to the south, the war has already begun. "
        "Rell boards the ferry and tells Vesh they leave before the tide turns."))]
    assert lint_narration_order(beats, cards) == {}


def test_lint_unanchored_opening_flags_a_beat_that_names_nobody():
    """ch1 beat 14 was "He replies quickly to reassure her" — no proper noun anywhere in
    the beat, both antecedents two beats back. enforce_mc_name_budget cannot catch this
    (it triggers on a rival NAMED in the beat) and could not repair it anyway: it only
    ever removes names."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import lint_unanchored_opening

    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="char_mc",
        characters={
            "char_mc": CharacterProfile(id="char_mc", canonical_name="Rell",
                                        tier=CharacterTier.MAIN, pronoun="he"),
            "char_d": CharacterProfile(id="char_d", canonical_name="Doran",
                                       tier=CharacterTier.SUPPORTING, pronoun="he"),
        },
    )
    beats = [
        # Establishes a same-pronoun RIVAL, which is what makes the next "He" ambiguous.
        ScriptBeat(beat_id=1, panel_ids=["p"],
                   narration="Doran gathers the party and calls for the gate to be opened."),
        ScriptBeat(beat_id=2, panel_ids=["p"],
                   narration="He replies quickly to reassure her, steeling his resolve."),
        # Opens on a pronoun but names its subject in the same sentence: fine.
        ScriptBeat(beat_id=3, panel_ids=["p"],
                   narration="He turns, and Rell tells Doran the gate is already open."),
        # Opens on a name: fine.
        ScriptBeat(beat_id=4, panel_ids=["p"], narration="Rell steps through the gate."),
    ]
    flagged = lint_unanchored_opening(beats, bible)
    assert sorted(flagged) == [2]
    assert "Doran" in flagged[2][0]      # names the rival that makes "He" ambiguous


def test_lint_unanchored_opening_allows_a_bare_pronoun_with_no_rival():
    """A bare pronoun is only AMBIGUOUS when a same-pronoun rival is live. "He checks his
    pack" after a beat naming only the protagonist is ordinary prose — flagging it fought
    enforce_mc_name_budget's cadence, and the beat could satisfy neither."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import lint_unanchored_opening

    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="char_mc",
        characters={
            "char_mc": CharacterProfile(id="char_mc", canonical_name="Rell",
                                        tier=CharacterTier.MAIN, pronoun="he"),
            "char_d": CharacterProfile(id="char_d", canonical_name="Doran",
                                       tier=CharacterTier.SUPPORTING, pronoun="he"),
        },
    )
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p"], narration="Rell shoulders his pack."),
        ScriptBeat(beat_id=2, panel_ids=["p"], narration="He checks the road ahead."),
    ]
    assert lint_unanchored_opening(beats, bible) == {}


def test_accept_rewrite_refuses_a_malformed_rewrite():
    """Every rewrite path hands an LLM a defect and accepted whatever came back. ch1 beat
    12's model text was clean; the alignment rewrite returned "Jin-Woo and Lee Joo-hee. He
    murmurs a quiet greeting, and he simply nods back" — a fragment, two unresolvable
    pronouns, and the raid leader the beat existed to introduce deleted. The pairwise
    judge returned "undecided", whose default keeps the rewrite. Well-formedness is
    decidable for free, so it is settled before the judge is consulted."""
    from manhwa2vid.script.lint import accept_rewrite, narration_defects, sentence_fragments

    good = ("The hunters gather their gear as a call for attention echoes through the site. "
            "Doran, a veteran raid leader, steps forward and asks the group for consensus.")
    bad = "Rell and Vesh. He murmurs a quiet greeting, and he simply nods back."

    assert sentence_fragments(bad) == ["Rell and Vesh."]
    assert not sentence_fragments(good)
    assert len(narration_defects(bad)) > len(narration_defects(good))

    assert accept_rewrite(good, bad) == good      # strictly worse -> keep the original
    assert accept_rewrite(bad, good) == good      # a real fix is taken
    assert accept_rewrite(good, "") == good       # empty rewrite never wins


def test_sentence_fragments_spares_short_deliberate_lines():
    """One- and two-word sentences are deliberate ("Silence."), and the present-tense
    register means a real clause almost always carries a verb _looks_like_verb catches."""
    from manhwa2vid.script.lint import sentence_fragments

    for ok in ["Silence.", "He nods.", "The gate opens at dawn.",
               "Rell walks the market road with her hood up."]:
        assert sentence_fragments(ok) == [], ok


def test_mc_name_budget_keeps_the_anchor_a_bare_opening_needs():
    """The name budget and lint_unanchored_opening contradicted each other: the lint
    demands the beat name someone, the rewrite adds the name, and the budget — seeing no
    same-pronoun rival NAMED in the beat — rotated it straight back out. ch1 beat 14
    survived two rewrite rounds unfixed for exactly that reason."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import enforce_mc_name_budget, lint_unanchored_opening

    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="char_mc",
        characters={
            "char_mc": CharacterProfile(
                id="char_mc", canonical_name="Sung Jin-Woo", tier=CharacterTier.MAIN,
                pronoun="he"),
            "char_k": CharacterProfile(
                id="char_k", canonical_name="Kim Sangshik",
                tier=CharacterTier.SUPPORTING, pronoun="he"),
        },
    )
    cfg = {"script": {"mc_anchor_every_beats": 2}}
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p"], narration="Sung Jin-Woo steps onto the road."),
        # A same-pronoun rival acts here, so the next beat's bare "He" would be ambiguous.
        ScriptBeat(beat_id=2, panel_ids=["p"],
                   narration="Kim Sangshik tells the party to move out."),
        # Inside the cadence window, so the old rule stripped this name anyway.
        ScriptBeat(beat_id=3, panel_ids=["p"],
                   narration="Jin-Woo takes a sharp breath and steps through the gate."),
    ]
    out = enforce_mc_name_budget(beats, bible, cfg)
    assert "Jin-Woo" in out[2].narration
    # And the two mechanisms now agree rather than looping.
    assert lint_unanchored_opening(out, bible) == {}


def test_rewrite_beat_honours_caller_supplied_issues():
    """THE bug that forced hand-editing. rewrite_beat ran lint_beats and returned early
    when it came up clean, silently discarding the caller's `issues` — and lint_beats
    covers only the old suite, so every story-integrity finding (coverage, order,
    unanchored opening, missing introduction, abstraction drift...) never reached the
    model unless the beat coincidentally had an old-style defect too."""
    from manhwa2vid.models import CharacterProfile, CharacterRef, CharacterTier, PanelCast, SeriesBible
    from manhwa2vid.script.lint import lint_beats, rewrite_beat

    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="char_mc",
        characters={
            "char_mc": CharacterProfile(id="char_mc", canonical_name="Rell",
                                        tier=CharacterTier.MAIN, pronoun="he"),
            "char_d": CharacterProfile(id="char_d", canonical_name="Doran",
                                       tier=CharacterTier.SUPPORTING, pronoun="he",
                                       role="raid leader"),
        },
    )
    attribution = [PanelCast(panel_id="p1", people=[
        CharacterRef(ref="char_mc", name_used="Rell"),
        CharacterRef(ref="char_d", name_used="Doran")])]
    beat = ScriptBeat(beat_id=1, panel_ids=["p1"],
                      narration="Rell tells Doran that the gate is open.")
    assert 1 not in lint_beats([beat], {}, bible=bible, attribution=attribution,
                               scene_cards=None), "fixture must be clean by the old suite"

    reached = []

    class _LLM:
        def complete(self, *a, **k):
            reached.append(True)
            return "Rell tells Doran, the raid leader, that the gate is open."

    rewrite_beat(beat, bible, attribution, {},
                 issues=["Doran is named with no introduction"], scene_cards=None, llm=_LLM())
    assert reached, "a caller-supplied issue must reach the model"

    # With no issues AND a clean lint, the short-circuit must still hold (it is what keeps
    # the rewrite loop from calling the model on every good beat).
    reached.clear()
    out = rewrite_beat(beat, bible, attribution, {}, issues=None, scene_cards=None, llm=_LLM())
    assert not reached and out.strip() == beat.narration.strip()


def test_ensure_first_mention_role_inserts_once_and_skips_unsafe_shapes():
    """The inverse of strip_repeated_appositives: mechanical appositive INSERTION at a
    character's first mention, after the prompt declined rule 4's floor across three runs."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import ensure_first_mention_role, lint_missing_introduction

    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="char_mc",
        characters={
            "char_mc": CharacterProfile(id="char_mc", canonical_name="Rell",
                                        tier=CharacterTier.MAIN),
            "char_d": CharacterProfile(id="char_d", canonical_name="Doran",
                                       tier=CharacterTier.SUPPORTING, role="raid leader"),
            "char_v": CharacterProfile(id="char_v", canonical_name="Vesh",
                                       tier=CharacterTier.SUPPORTING, role="field medic"),
        },
    )
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p"], narration="Rell tells Doran that nobody objects."),
        ScriptBeat(beat_id=2, panel_ids=["p"], narration="Doran commands the party to enter."),
        # Already introduced elsewhere -> never given a second clause.
        ScriptBeat(beat_id=3, panel_ids=["p"], narration="Vesh, the field medic, binds it."),
        ScriptBeat(beat_id=4, panel_ids=["p"], narration="Vesh works quickly."),
    ]
    out = ensure_first_mention_role(beats, bible)
    assert out[0].narration == "Rell tells Doran, the raid leader, that nobody objects."
    assert out[1].narration == "Doran commands the party to enter."   # only the FIRST
    assert out[2].narration == beats[2].narration
    assert out[3].narration == beats[3].narration
    assert lint_missing_introduction(out, bible) == {}

    # Sentence-final mention closes with the existing terminator, not ",."
    tail = ensure_first_mention_role(
        [ScriptBeat(beat_id=1, panel_ids=["p"], narration="They trust Doran.")], bible)
    assert tail[0].narration == "They trust Doran, the raid leader."

    # An existing PREMODIFIER introduction counts too, not just an appositive. Missing
    # this shipped "Veteran hunter Kim Sangshik, the hunter, grabs a warm drink" —
    # introduced twice inside four words.
    premod = ensure_first_mention_role(
        [ScriptBeat(beat_id=1, panel_ids=["p"],
                    narration="Veteran raid leader Doran grabs a drink.")], bible)
    assert premod[0].narration == "Veteran raid leader Doran grabs a drink."

    # A possessive is never split; the clause lands on the next plain mention.
    poss = ensure_first_mention_role(
        [ScriptBeat(beat_id=1, panel_ids=["p"],
                    narration="Doran's skills are famous. Doran nods.")], bible)
    assert poss[0].narration.startswith("Doran's skills are famous.")
    assert "Doran, the raid leader, nods." in poss[0].narration


def test_sentence_fragments_allows_bare_present_tense_verbs():
    """_looks_like_verb is a suffix test and misses bare forms a plural or pronoun subject
    takes. Flagging those would make accept_rewrite discard good rewrites."""
    from manhwa2vid.script.lint import sentence_fragments

    assert sentence_fragments("They trust Doran, the raid leader.") == []
    assert sentence_fragments("Hunters gather at the gate.") == []
    assert sentence_fragments("Rell and Vesh.") == ["Rell and Vesh."]


def test_mc_name_budget_restores_an_anchor_the_beat_never_had():
    """Every other path here can only ROTATE a name already present, so a beat the writer
    produced with no proper noun at all stayed unanchored through every rewrite round.
    Substituting the protagonist is the inverse of what this function does —
    rotate_protagonist_name turns the MC's name INTO "he" — so a bare "he" in this
    pipeline's own output is the MC by construction."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import enforce_mc_name_budget, lint_unanchored_opening

    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="char_mc",
        characters={
            "char_mc": CharacterProfile(id="char_mc", canonical_name="Sung Jin-Woo",
                                        tier=CharacterTier.MAIN, pronoun="he"),
            "char_k": CharacterProfile(id="char_k", canonical_name="Kim Sangshik",
                                       tier=CharacterTier.SUPPORTING, pronoun="he"),
        },
    )
    cfg = {"script": {"mc_anchor_every_beats": 2}}
    beats = [
        # Names a same-pronoun rival, so the next beat's bare "He" is ambiguous.
        ScriptBeat(beat_id=1, panel_ids=["p"], narration="Kim Sangshik waves them onward.",
                   character_ids=["char_k"]),
        ScriptBeat(beat_id=2, panel_ids=["p"], narration="He takes a sharp breath and steps through.",
                   character_ids=["char_k", "char_mc"]),
    ]
    out = enforce_mc_name_budget(beats, bible, cfg)
    assert out[1].narration.startswith("Jin-Woo takes a sharp breath")
    assert lint_unanchored_opening(out, bible) == {}

    # Not in the beat's own cast -> never substituted, because that would misattribute.
    other = [beats[0], beats[1].model_copy(update={"character_ids": ["char_k"]})]
    assert enforce_mc_name_budget(other, bible, cfg)[1].narration.startswith("He takes")


def test_ensure_first_mention_role_lowercases_the_inserted_article():
    """Roles are stored however the bible captured them. "The final boss of the Antarctic
    dungeon" arrived title-cased and shipped as "the Frost Queen, The final boss...". An
    inserted appositive always sits mid-sentence."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import ensure_first_mention_role

    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="mc",
        characters={
            "mc": CharacterProfile(id="mc", canonical_name="Rell", tier=CharacterTier.MAIN),
            "q": CharacterProfile(id="q", canonical_name="Frost Queen",
                                  tier=CharacterTier.SUPPORTING,
                                  role="The final boss of the Antarctic dungeon"),
            "n": CharacterProfile(id="n", canonical_name="Vesh",
                                  tier=CharacterTier.SUPPORTING, role="NASA liaison"),
        },
    )
    out = ensure_first_mention_role(
        [ScriptBeat(beat_id=1, panel_ids=["p"], narration="Rell tells Frost Queen to stand down.")],
        bible)
    assert "Frost Queen, the final boss of the Antarctic dungeon," in out[0].narration

    # An acronym keeps its case — lowercasing blindly would give "the nASA liaison".
    acro = ensure_first_mention_role(
        [ScriptBeat(beat_id=1, panel_ids=["p"], narration="Rell greets Vesh.")], bible)
    assert acro[0].narration == "Rell greets Vesh, the NASA liaison."


def test_sanitize_role_trims_a_truncated_relative_clause():
    """The quest pass once stored 'The final boss of the Antarctic dungeon whose' — its
    source sentence continued past the truncation point — and the introduction inserter
    shipped the dangling "whose," verbatim on Frozen Player."""
    from manhwa2vid.characters.bible import sanitize_role

    assert sanitize_role("The final boss of the Antarctic dungeon whose") == \
        "The final boss of the Antarctic dungeon"
    assert sanitize_role("guardian of the") == "guardian"
    assert sanitize_role("whose") == ""
    assert sanitize_role("raid leader") == "raid leader"     # untouched when clean


def test_first_mention_role_respects_a_role_the_writer_already_used():
    """Four teammates can share one bible role. When the WRITER already introduced one of
    them with it, the inserter must treat that role as taken — used_roles previously only
    learned what the inserter itself wrote, so a second character got the same clause and
    a rewrite round stamped it three times into one beat."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import ensure_first_mention_role

    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="mc",
        characters={
            "mc": CharacterProfile(id="mc", canonical_name="Rell", tier=CharacterTier.MAIN),
            "a": CharacterProfile(id="a", canonical_name="Skaya", tier=CharacterTier.SUPPORTING,
                                  role="A member of the original five heroes"),
            "b": CharacterProfile(id="b", canonical_name="Khali", tier=CharacterTier.SUPPORTING,
                                  role="A member of the original five heroes"),
        },
    )
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p"],
                   narration="Skaya, a member of the original five heroes, urges the group on."),
        ScriptBeat(beat_id=2, panel_ids=["p"], narration="Skaya tells Khali that they agree."),
    ]
    out = ensure_first_mention_role(beats, bible)
    assert out[1].narration == "Skaya tells Khali that they agree."   # role already taken


def test_mc_acting_unnamed_is_detected_and_repaired():
    """Shipped on Frozen Player: "The presenter introduces the frozen figures... When a
    schoolboy points out a moving statue, HE shatters his icy prison." The beat's cast
    contains the protagonist, the narration never names him, and the nearest antecedent is
    the schoolboy — nobody watching could tell who broke out of the ice.

    The gate and the deterministic repair share one predicate on purpose: a lint that
    demands a name while the name budget rotates it back out is a loop this project has
    already paid for twice."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import (
        enforce_mc_name_budget,
        lint_ambiguous_pronoun,
        mc_acts_unnamed,
    )

    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="mc",
        characters={"mc": CharacterProfile(id="mc", canonical_name="Sung Jin-Woo",
                                           tier=CharacterTier.MAIN, pronoun="he")},
    )
    acts_unnamed = ScriptBeat(beat_id=1, panel_ids=["p"], character_ids=["mc"], narration=(
        "The presenter introduces the frozen figures. When a schoolboy points at a "
        "statue, he shatters the ice."))
    names_him = ScriptBeat(beat_id=2, panel_ids=["p"], character_ids=["mc"], narration=(
        "Jin-Woo flops onto the bed, and he struggles to take it in."))
    not_in_cast = ScriptBeat(beat_id=3, panel_ids=["p"], character_ids=["other"],
                             narration="He waves the group through the gate.")

    assert mc_acts_unnamed(acts_unnamed, bible)
    assert not mc_acts_unnamed(names_him, bible)      # already anchored
    assert not mc_acts_unnamed(not_in_cast, bible)    # not his beat to anchor
    assert sorted(lint_ambiguous_pronoun([acts_unnamed, names_him, not_in_cast], bible)) == [1]

    # The repair closes it without an LLM round, and the gate then falls silent.
    fixed = enforce_mc_name_budget(
        [names_him, acts_unnamed], bible, {"script": {"mc_anchor_every_beats": 2}})
    assert "Jin-Woo" in fixed[1].narration
    assert lint_ambiguous_pronoun(fixed, bible) == {}


def test_anchor_restore_never_replaces_a_plural_they():
    """Shipped: "proves they all share the same opinion" became "proves Jun-Ho all share
    the same opinion". A plural "they" is not the protagonist, and substituting it is
    ungrammatical as well as wrong. Only the MC's own pronoun may be replaced."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, SeriesBible
    from manhwa2vid.script.lint import enforce_mc_name_budget

    bible = SeriesBible(
        series_slug="s", title="S", protagonist_id="mc",
        characters={
            "mc": CharacterProfile(id="mc", canonical_name="Seo Jun-Ho",
                                   tier=CharacterTier.MAIN, pronoun="he",
                                   descriptors=["man in a black coat"]),
            "k": CharacterProfile(id="k", canonical_name="Khali",
                                  tier=CharacterTier.SUPPORTING, pronoun="he",
                                  descriptors=["man with tattoos"]),
        },
    )
    beats = [
        ScriptBeat(beat_id=1, panel_ids=["p"], character_ids=["k"],
                   narration="Khali shouts at the group."),
        ScriptBeat(beat_id=2, panel_ids=["p"], character_ids=["mc", "k"],
                   narration="Skaya tells Khali his quick acceptance proves they all agree."),
    ]
    out = enforce_mc_name_budget(beats, bible, {"script": {"mc_anchor_every_beats": 2}})
    assert "they all agree" in out[1].narration
    assert "Jun-Ho all agree" not in out[1].narration




def test_visual_inventory_is_caught_on_the_shapes_that_actually_shipped():
    """All five are verbatim from the shipped Frozen Player script, and every one of
    them slipped past both anti-captioning mechanisms. Measured over the same two
    chapters the reference runs ZERO body/appearance inventory phrases and we ran 15, at
    near-identical total word counts — so these are purely words taken from the line the
    panel prints. Appearance appositives are STRIPPED (removable by construction);
    gestures are FLAGGED, because deleting "tilts his head slightly upward" leaves no
    verb and only the panel knows what belonged there."""
    from manhwa2vid.script.lint import lint_captioning, strip_appearance_descriptors

    stripped = [
        ("A young boy in a beige sweater points at the stage.",
         "A young boy points at the stage."),
        ("The presenter, a man in a black suit with black hair, stands there.",
         "The presenter, a man, stands there."),
    ]
    for before, after in stripped:
        beat = ScriptBeat(beat_id=1, panel_ids=["p"], narration=before)
        assert strip_appearance_descriptors([beat])[0].narration == after

    flagged = [
        "Jun-Ho tilts his head slightly upward toward the sky.",
        "Deok-gu clutches his forehead in deep frustration.",
        "Jun-Ho sweats and smiles awkwardly.",
    ]
    for text in flagged:
        beat = ScriptBeat(beat_id=1, panel_ids=["p"], narration=text)
        issues = lint_captioning([beat]).get(1, [])
        assert any(i.startswith("body_inventory:") for i in issues), text


def test_body_inventory_leaves_consequential_action_alone():
    """The line between inventory and story is consequence, not body parts: a gesture
    that changes something is the story."""
    from manhwa2vid.script.lint import lint_captioning

    for text in [
        "Deok-gu tells him humanity cleared exactly one floor.",
        "Jun-Ho draws his sword and steps onto the stairs.",
        "He raises his hand to stop her.",
        "She forms a blade of pure ice and fires it point blank.",
    ]:
        beat = ScriptBeat(beat_id=1, panel_ids=["p"], narration=text)
        assert lint_captioning([beat]) == {}, text


def test_closer_must_point_forward():
    """Every other closer constraint is backward-looking — lint_closer_reveal and the
    reveal-coverage gate both demand the FINAL PANELS' content, and inject_closer_evidence
    pins it into plot_beat. Nothing asked whether the ending gives a listener a reason to
    come back, so Frozen Player's closer ended on "He gasps in disbelief" while the
    reference ends on "he's becoming a player again"."""
    from manhwa2vid.script.lint import lint_closer_forward_hook

    recap_only = [
        ScriptBeat(beat_id=1, panel_ids=["p"], narration="He touches the ice."),
        ScriptBeat(beat_id=2, panel_ids=["q"], narration="A message says the seal can be removed. He gasps in disbelief."),
    ]
    assert 2 in lint_closer_forward_hook(recap_only)

    points_forward = [
        ScriptBeat(beat_id=1, panel_ids=["p"], narration="He touches the ice."),
        ScriptBeat(beat_id=2, panel_ids=["q"], narration="The seal can be removed. So the plan writes itself: climb, get strong, bring them home."),
    ]
    assert lint_closer_forward_hook(points_forward) == {}


def test_hedge_strip_spares_a_sentence_that_supplies_a_next_step():
    """The strip removes a hedge because a hedge ends the chapter on nothing. A
    question-shaped sentence that states an INTENT is not that — deleting it would trade
    a hedge for no ending at all, which is strictly worse."""
    from manhwa2vid.script.lint import (
        _is_trailing_closer_sentence,
        strip_trailing_closer_sentence,
    )

    assert _is_trailing_closer_sentence("Whether he survives remains to be seen.")
    assert not _is_trailing_closer_sentence(
        "Whether he can climb ten floors is beside the point — he already has a plan."
    )

    kept = strip_trailing_closer_sentence([
        ScriptBeat(beat_id=1, panel_ids=["p"], narration="He reads the message."),
        ScriptBeat(
            beat_id=2, panel_ids=["q"],
            narration="The seal can come off. Whether that takes ten floors or twenty, he sets out at dawn.",
        ),
    ])
    assert "sets out" in kept[-1].narration


def test_broken_sentences_are_checked_across_the_whole_beat():
    """Both of these shipped into a rendered Solo Leveling video. sentence_fragments
    already detected the first one perfectly — nothing ever ASKED it about finished
    narration. It is reachable only through narration_defects, used in exactly one place
    (accept_rewrite) and there only as a RELATIVE count, rewrite vs original; a fragment
    the writer produced in a beat no rewrite touched was never examined. The one absolute
    well-formedness gate, lint_malformed_opening, inspects a beat's FIRST sentence only."""
    from manhwa2vid.script.lint import lint_broken_sentences

    beat = ScriptBeat(
        beat_id=11, panel_ids=["p"],
        narration=(
            "Jin-Woo offers a weak smile, telling Lee Joo-hee. Our guy is basically a "
            "professional punching bag at this point. She stares back at him in silent "
            "pity. Nearby, Kim Sangshik, Bak."
        ),
    )
    issues = lint_broken_sentences([beat])[11]
    assert any(i.startswith("fragment:") and "Nearby" in i for i in issues)
    assert any(i.startswith("truncated_speech:") and "Lee Joo-hee" in i for i in issues)


def test_broken_sentences_leaves_well_formed_narration_alone():
    """Precision matters more than recall here: a false positive sends a good beat
    through a rewrite that can only make it worse."""
    from manhwa2vid.script.lint import lint_broken_sentences

    for text in [
        "Bak complains to Kim Sangshik. Kim just sips his coffee.",
        "He tells Bak that the dungeon is bound to be weak today.",
        "Kim Sangshik waves a coffee cup and asks him if he has eaten yet.",
        "She asks how they could skip a healer.",
        "Our guy cannot even get a basic caffeine fix. Truly a brutal start to the day.",
        "Jin-Woo is basically the designated back-row spectator.",
        "He explains.",
        "Silence.",
    ]:
        assert lint_broken_sentences([ScriptBeat(beat_id=1, panel_ids=["p"], narration=text)]) == {}, text


def test_broken_sentence_issues_become_actionable_rewrite_instructions():
    from manhwa2vid.script.lint import _humanize_issues

    out = _humanize_issues(["fragment: Nearby, Kim Sangshik, Bak."])
    assert "no verb" in out
    out2 = _humanize_issues(["truncated_speech: Jin-Woo offers a weak smile, telling Lee Joo-hee."])
    assert "never what was said" in out2


def test_narration_defects_guards_rewrites_against_truncated_speech():
    """The reason the first fix was not enough. lint_broken_sentences checked this shape
    at the END of the run, but narration_defects — which every accept_rewrite in the
    pipeline consults — could not see it, so any rewrite was free to ADD one. A beat the
    story-integrity round had already cleaned came back from a later rewrite as "Jin-Woo
    smiles weakly and tells Lee Joo-hee." and no guard objected."""
    from manhwa2vid.script.lint import accept_rewrite, narration_defects

    clean = "Jin-Woo smiles weakly and tells Lee Joo-hee that he is used to it by now."
    broken = "Jin-Woo smiles weakly and tells Lee Joo-hee."
    assert not narration_defects(clean)
    assert any(d.startswith("truncated_speech:") for d in narration_defects(broken))
    # And the guard now refuses that rewrite rather than shipping it.
    assert accept_rewrite(clean, broken) == clean


def test_trailing_name_list_fragment_survives_an_ordinary_noun():
    """"Near the entrance, Kim Sangshik, Bak." is the same dead stub as "Nearby, Kim
    Sangshik, Bak.", but one ordinary lowercase noun satisfies the possible-verb
    heuristic and the whole sentence was waved through. That heuristic is deliberately
    precision-favouring and stays; this catches the shape it cannot."""
    from manhwa2vid.script.lint import sentence_fragments

    assert sentence_fragments("Near the entrance, Kim Sangshik, Bak.") == [
        "Near the entrance, Kim Sangshik, Bak."
    ]
    # Reported once, not twice — the two detectors overlap on the plainest case, and a
    # doubled defect would make accept_rewrite reject a rewrite that merely left it be.
    assert sentence_fragments("Nearby, Kim Sangshik, Bak.") == ["Nearby, Kim Sangshik, Bak."]
    # A real sentence whose subject happens to be a list of names is untouched.
    assert sentence_fragments("Kim Sangshik, Bak, and Song Chi-yul enter the gate together.") == []


def test_repair_broken_sentences_fixes_what_the_rewrite_declined():
    """Both shapes survived a story-integrity rewrite AND the dedicated dialogue retry
    with the offending sentence quoted back at the model — and beat 11's evidence even
    CONTAINED what Jin-Woo says. Three runs running. That is this codebase's threshold:
    a rule the model declines twice stops being a request."""
    from manhwa2vid.script.lint import lint_broken_sentences, repair_broken_sentences

    beat = ScriptBeat(
        beat_id=11, panel_ids=["p"],
        narration=(
            "Jin-Woo smiles weakly and tells Lee Joo-hee. She looks at him with a sad "
            "gaze. Then, he suggests they head inside. Nearby, Kim Sangshik, Bak. They "
            "look toward a glowing blue Gate."
        ),
    )
    fixed = repair_broken_sentences([beat])[0].narration
    # The stranded names get the verb that was already sitting in the next sentence.
    assert "Kim Sangshik and Bak look toward a glowing blue Gate." in fixed
    # The dangling speech clause goes; nothing is invented in its place.
    assert "Jin-Woo smiles weakly." in fixed
    assert "tells Lee Joo-hee." not in fixed
    assert lint_broken_sentences([ScriptBeat(beat_id=11, panel_ids=["p"], narration=fixed)]) == {}


def test_repair_broken_sentences_leaves_sound_narration_alone():
    from manhwa2vid.script.lint import repair_broken_sentences

    for text in [
        "He tells Bak that the dungeon is bound to be weak today.",
        "Kim Sangshik waves a coffee cup and asks him if he has eaten yet.",
        "Bak nods and tells the raid party that they can trust the veteran leader.",
        "Kim Sangshik, Bak, and Song Chi-yul enter the gate together.",
        "Jin-Woo and Lee Joo-hee turn toward the entrance. They step through the light.",
    ]:
        beat = ScriptBeat(beat_id=1, panel_ids=["p"], narration=text)
        assert repair_broken_sentences([beat])[0].narration == text, text


def test_restore_lost_required_lines_is_the_choke_point():
    """One guard for a bug class that surfaced in FIVE separate passes today, each time
    invisible because every individual step looked locally reasonable: trim_overlong_beats
    popping a landed payoff, rewrite_voice stripping system messages for rhythm, the
    alignment audit dropping one in a rewrite, strip_trailing_closer_sentence deleting a
    forward thesis, and the quote scanner losing lines outright. Guarding pass-by-pass
    lost — three were fixed that way and a fourth appeared immediately."""
    from manhwa2vid.script.lint import restore_lost_required_lines

    req = {4: ["[YOUR BODY WILL GO INTO HIBERNATION UNTIL YOU HAVE FULLY ABSORBED THE NUCLEUS.]"]}
    verified = {
        4: ("The Frost Queen fades into light. A system prompt warns that his body will go "
            "into hibernation until he has fully absorbed the nucleus."),
    }
    # A later pass rewrote it punchier and quietly dropped the system message.
    beats = [ScriptBeat(beat_id=4, panel_ids=["p"], narration=(
        "The Frost Queen fades into light. Our guy is not feeling the sentiment."))]

    out, restored = restore_lost_required_lines(beats, verified, req)
    assert restored == {4: req[4]}, "the loss must be reported, never silent"
    assert out[0].narration == verified[4]


def test_restore_leaves_a_beat_that_kept_its_lines():
    """Polish that improves a beat without costing content is kept — the guard only
    fires on LOSS, so it never undoes legitimate downstream work."""
    from manhwa2vid.script.lint import restore_lost_required_lines

    req = {4: ["[YOU HAVE ABSORBED THE NUCLEUS.]"]}
    verified = {4: "A message says he has absorbed the nucleus."}
    beats = [ScriptBeat(beat_id=4, panel_ids=["p"], narration=(
        "A message says he has absorbed the nucleus. Bro is not okay."))]

    out, restored = restore_lost_required_lines(beats, verified, req)
    assert restored == {}
    assert "Bro is not okay." in out[0].narration


def test_restore_is_inert_without_a_snapshot_or_requirements():
    from manhwa2vid.script.lint import restore_lost_required_lines

    beats = [ScriptBeat(beat_id=1, panel_ids=["p"], narration="He walks on.")]
    assert restore_lost_required_lines(beats, {}, {}) == (beats, {})
    assert restore_lost_required_lines(beats, {1: "Something else."}, {}) == (beats, {})


def test_echoed_agent_catches_the_comma_separated_form():
    """"A man, a man, and a woman in a red blazer look upward" shipped into a Frozen
    Player beat: the pattern required the word "and" between the two, so the
    comma-separated form — the one an LLM actually produces when listing a crowd — went
    straight through. Two anonymous agents flattened onto one descriptor says nothing."""
    from manhwa2vid.script.lint import narration_defects

    assert any("same descriptor" in d for d in narration_defects(
        "A man, a man, and a woman in a red blazer look upward in absolute shock."))
    assert any("same descriptor" in d for d in narration_defects(
        "A hunter and a hunter both shout their agreement."))
    # Distinct agents in a list are fine — this is about the ECHO, not about lists.
    for ok in [
        "A hunter and a healer step through the gate.",
        "A man, a woman, and a child watch the sky.",
        "A man and a woman argue near the stall.",
    ]:
        assert not narration_defects(ok), ok


def test_sentence_splitter_does_not_break_on_honorifics():
    """"Mr. Kim tells Sung Jin-Woo." split into "Mr." + "Kim tells Sung Jin-Woo.", which
    is wrong everywhere _SENTENCE_SPLIT_RE is used: it inflates short_sentence_fraction
    with one-token sentences, misleads trim and the dedupe passes about where a sentence
    starts, and made repair_broken_sentences delete the wrong half and emit "Mr. Jin-Woo
    laughs nervously"."""
    from manhwa2vid.script.lint import _SENTENCE_SPLIT_RE

    assert _SENTENCE_SPLIT_RE.split("Mr. Kim tells Sung Jin-Woo. Jin-Woo laughs.") == [
        "Mr. Kim tells Sung Jin-Woo.", "Jin-Woo laughs."
    ]
    assert _SENTENCE_SPLIT_RE.split("Dr. Song arrives. She checks the wound.") == [
        "Dr. Song arrives.", "She checks the wound."
    ]
    assert len(_SENTENCE_SPLIT_RE.split("He steps through. Nobody follows.")) == 2


def test_stranded_determiner_is_repaired_and_checked_absolutely():
    """"The they explain that the other hunters held higher ranks" shipped in a 5-chapter
    run. _ARTICLE_PRONOUN_RE always detected it, but only via narration_defects — a
    RELATIVE count inside accept_rewrite — so one the writer produced in an untouched beat
    was never examined. A bare article on a bare pronoun is also unambiguously repairable,
    unlike "A dejected he walks away" which needs to know which person."""
    from manhwa2vid.script.lint import lint_broken_sentences, repair_broken_sentences

    beat = ScriptBeat(beat_id=1, panel_ids=["p"], narration=(
        "The demon speaks first. The they explain the ranks were higher. Nobody argues."))
    assert any(i.startswith("stranded_determiner:") for i in lint_broken_sentences([beat])[1])
    fixed = repair_broken_sentences([beat])[0].narration
    assert "They explain the ranks were higher." in fixed
    assert lint_broken_sentences([ScriptBeat(beat_id=1, panel_ids=["p"], narration=fixed)]) == {}


def test_standalone_empty_speech_is_dropped_only_when_safe():
    """Deleting "Mr. Kim tells Sung Jin-Woo." is safe when a named subject follows. It is
    NOT safe before "She asks how that is possible." — that strands the pronoun with no
    antecedent left in the beat, trading one defect for a worse one."""
    from manhwa2vid.script.lint import repair_broken_sentences

    safe = ScriptBeat(beat_id=1, panel_ids=["p"], narration=(
        "Mr. Kim tells Sung Jin-Woo. Jin-Woo laughs nervously and agrees. Ju-Hee tells him to move."))
    out = repair_broken_sentences([safe])[0].narration
    assert out.startswith("Jin-Woo laughs")
    assert "Mr. Jin-Woo" not in out

    unsafe = ScriptBeat(beat_id=1, panel_ids=["p"], narration=(
        "The large orange demon tells Ju-Hee. She asks how that is possible. Nobody answers."))
    assert repair_broken_sentences([unsafe])[0].narration == unsafe.narration


def _beat(bid: int, text: str) -> ScriptBeat:
    return ScriptBeat(beat_id=bid, panel_ids=["p0001_01"], narration=text)


def test_broken_sentence_gate_ignores_object_pronouns_and_honorifics():
    """Both shapes blocked a real 5-chapter Solo Leveling run, and both are correct English.

    "A worker tells him that ..." is article + two words + OBJECT pronoun, which
    `_ARTICLE_PRONOUN_RE` matches by construction; "Bak asks Mr. Kim if ..." matched the
    truncated-speech regex on `asks Mr.` because an honorific's period is not a sentence
    terminator. Neither detector was new — `lint_broken_sentences` was the first caller to
    report them ABSOLUTELY rather than as a rewrite-versus-original count, and a false
    positive that cancels in a comparison fails a gate outright.
    """
    beats = [
        _beat(1, "A worker tells him that the gate has already closed."),
        _beat(2, "Bak asks Mr. Kim if Jin-Woo is coming to the raid."),
        _beat(3, "The healer treats him after the raid."),
        _beat(4, "He is used to the pain because he is weak."),
    ]
    assert lint_broken_sentences(beats) == {}


def test_broken_sentence_gate_still_blocks_the_bare_stranded_determiner():
    """The form the detector exists for, plus the guard bug it exposed.

    "The they explain" has a bare plural verb, which `_looks_like_verb` (written for
    -s/-ed/-ing) rejects — so the verb-follows guard was discarding the exact case it was
    meant to protect. The bare article-on-pronoun form is now tested before the guards.
    """
    flagged = lint_broken_sentences(
        [_beat(1, "The they explain that the other hunters held higher ranks.")]
    )
    assert [i.split(":")[0] for i in flagged[1]] == ["stranded_determiner"]


def test_ambiguous_stranded_determiner_is_advisory_not_blocking():
    """"A dejected he walks away" and "the moment he arrives" are the same token shape.

    One is broken and one is an ordinary reduced relative clause, and the verb-follows
    guard passes both ("arrives" ends in -s). Rather than lower the bar until the gate
    stops firing, the ambiguous form is kept OUT of the blocking tier and left to the
    rewrite path, where a symmetric false positive cancels.
    """
    ambiguous = "A dejected he walks away."
    ordinary = "the moment he arrives at the gate, sirens blare."
    assert stranded_determiner(ambiguous) is not None
    assert stranded_determiner(ordinary) is not None      # cannot tell these apart...
    assert stranded_determiner(ambiguous, strict=True) is None   # ...so neither blocks
    assert stranded_determiner(ordinary, strict=True) is None
    assert lint_broken_sentences([_beat(1, ordinary)]) == {}


def test_bare_name_sentence_is_a_fragment_but_a_one_word_beat_is_not():
    """"Ju-Hee." and "Sung Jin-Woo." both shipped into a 5-chapter Solo Leveling script.

    `sentence_fragments` skips sentences under `min_words` so a deliberate one-word beat
    survives — but those are COMMON nouns. A sentence that is nothing but a proper name is
    a clause whose verb phrase a polish pass deleted, and it gets spoken aloud as a stub.
    """
    assert sentence_fragments("Mr. Kim both vote to fight. Ju-Hee. She looks down.") == ["Ju-Hee."]
    assert sentence_fragments("Sung Jin-Woo. He tells Song Chi-Yul about the raid.") == ["Sung Jin-Woo."]
    for deliberate in ("Silence. The statue raises its spear.", "Not this time. He steps back."):
        assert sentence_fragments(deliberate) == []


def test_bare_name_repair_splices_the_severed_subject_back():
    beats = [
        _beat(22, "Mr. Kim both vote to fight. Ju-Hee. She looks down with a worried expression."),
        _beat(50, "Sung Jin-Woo. He tells Song Chi-Yul that he has done a B-rank raid twice."),
    ]
    out = repair_broken_sentences(beats)
    assert out[0].narration.endswith("Ju-Hee looks down with a worried expression.")
    assert out[1].narration.startswith("Sung Jin-Woo tells Song Chi-Yul")
    assert lint_broken_sentences(out) == {}


def test_bare_name_repair_does_not_swallow_a_name_that_ends_a_real_sentence():
    """The first version of this repair mangled five CORRECT beats in the run it fixed.

    It matched any name-then-period-then-pronoun span, so "Ju-Hee channels her magic into
    Sung Jin-Woo. She asks him why..." collapsed into "...into Sung Jin-Woo asks him
    why...". "Sung Jin-Woo." is a bare name in isolation but the TAIL of a full sentence
    here, and only a sentence-level view tells those apart.
    """
    intact = [
        "Ju-Hee channels her glowing magic directly into Sung Jin-Woo. "
        "She asks him why he is so adamant on working as a hunter.",
        "A trembling hand grips the sleeve of Sung Jin-Woo. "
        "He tries to process the second commandment of the temple.",
        "Glowing green crosses float around Sung Jin-Woo. He turns his head to look back.",
    ]
    for text in intact:
        assert repair_broken_sentences([_beat(1, text)])[0].narration == text


def test_mixed_number_pronoun_blocks_and_does_not_fire_on_real_plurals():
    """"They grit his teeth" reached a rendered 5-chapter script in seven beats.

    Every existing check passed it: grammatical in isolation, carries a verb, and neither
    the fragment nor the stranded-determiner detector models agreement. It is the audible
    symptom of a bible pronoun that never resolved, so it blocks — the fix belongs in the
    profile, not in a narration rewrite that the next chapter would re-break.
    """
    flagged = lint_broken_sentences([_beat(2, "They grit his teeth. He has zero options left.")])
    assert [i.split(":")[0] for i in flagged[2]] == ["mixed_number"]

    for genuine_plural in (
        "They raise their weapons.",
        "They walk among the pedestrians.",
        "Ju-Hee and Bak look at his severed arm.",
        "They and his brother argue about the raid.",
    ):
        assert lint_broken_sentences([_beat(1, genuine_plural)]) == {}
