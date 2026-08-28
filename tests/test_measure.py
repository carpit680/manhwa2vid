"""The measurement primitives the QA gates are built on.

These are tested directly, without media, because a gate is only as trustworthy as its
metric — and this project has twice shipped a conclusion drawn from a detector that was
measuring something other than what its name claimed.
"""

from __future__ import annotations

import numpy as np
import pytest


# --- shots: the invisible-cut trap ----------------------------------------------------

def test_merged_runs_fuses_consecutive_entries_on_one_panel():
    """Two entries on the same panel are ONE shot to the viewer, whatever the plan says.

    Counting entries reported 106 planned shots where Frozen Player shows 100, and a
    16.7s longest shot where the screen holds one image for 18.6s.
    """
    from manhwa2vid.measure.shots import merged_runs

    entries = [
        {"panel_id": "a", "duration": 2.0, "beat_id": 1},
        {"panel_id": "b", "duration": 7.4, "beat_id": 1},
        {"panel_id": "b", "duration": 11.2, "beat_id": 2},   # invisible cut
        {"panel_id": "c", "duration": 3.0, "beat_id": 2},
    ]
    runs = merged_runs(entries)
    assert [r["panel_id"] for r in runs] == ["a", "b", "c"]
    assert runs[1]["seconds"] == pytest.approx(18.6)
    assert runs[1]["entries"] == 2
    assert len(entries) - len(runs) == 1, "one cut the viewer cannot see"


def test_merged_runs_accepts_models_as_well_as_dicts():
    """Gates hold TimelineEntry objects; the measurement tool holds parsed JSON."""
    from manhwa2vid.measure.shots import merged_runs

    class E:
        def __init__(self, pid, dur):
            self.panel_id, self.duration, self.beat_id = pid, dur, 1

    assert len(merged_runs([E("a", 1.0), E("a", 1.0), E("b", 1.0)])) == 2


def test_shot_stats_longtail_is_a_share_of_runtime_not_of_count():
    """One 20s hold in a fast edit is a runtime problem, not a counting problem."""
    from manhwa2vid.measure.shots import shot_stats

    s = shot_stats([1.0, 1.0, 1.0, 20.0], 23.0)
    assert s["shot_over_8s_runtime_pct"] == pytest.approx(87.0, abs=0.5)
    assert s["shot_median_s"] == 1.0
    assert s["shot_longest_s"] == 20.0


# --- audio: the pure-numpy seam -------------------------------------------------------

def _voice_over_bed(*, bed_amp: float, sr: int = 16000, seconds: int = 4) -> np.ndarray:
    """Narration bursts over a tonal bed — the shape every recap mix has."""
    t = np.arange(sr * seconds) / sr
    bed = bed_amp * np.sin(2 * np.pi * 220 * t)
    voice = np.zeros_like(t)
    rng = np.random.default_rng(0)
    for start in (0.5, 2.0):
        a, b = int(start * sr), int((start + 1.0) * sr)
        voice[a:b] = 0.3 * rng.normal(size=b - a)
    return bed + voice


def test_duck_depth_is_speech_over_the_quiet_floor():
    from manhwa2vid.measure.audio import audio_metrics

    loud_bed = audio_metrics(_voice_over_bed(bed_amp=0.06), 16000)
    quiet_bed = audio_metrics(_voice_over_bed(bed_amp=0.006), 16000)
    assert quiet_bed["duck_depth_db"] > loud_bed["duck_depth_db"] + 10, (
        "a quieter bed must read as a deeper duck"
    )
    assert loud_bed["quiet_floor_dbfs"] > quiet_bed["quiet_floor_dbfs"]


def test_tonality_separates_music_from_no_music():
    """The bed is chosen by globbing assets/bgm/ and taking the first file. An empty
    directory ships a silent bed, and level alone cannot tell that from a quiet mix."""
    from manhwa2vid.measure.audio import audio_metrics

    with_music = audio_metrics(_voice_over_bed(bed_amp=0.03), 16000)
    rng = np.random.default_rng(1)
    hiss = _voice_over_bed(bed_amp=0.0) + 0.003 * rng.normal(size=16000 * 4)
    without = audio_metrics(hiss, 16000)
    assert with_music["tonality_ratio"] > 5.0
    assert without["tonality_ratio"] < 5.0


def test_audio_metrics_on_silence_does_not_explode():
    from manhwa2vid.measure.audio import audio_metrics

    m = audio_metrics(np.zeros(16000), 16000)
    assert m["quiet_floor_dbfs"] < -100 and m["tonality_ratio"] == 0.0
    assert audio_metrics(np.array([]), 16000)["duck_depth_db"] == 0.0


# --- binding --------------------------------------------------------------------------

def test_match_rate_counts_sentences_with_their_own_panel():
    from manhwa2vid.measure.binding import match_rate

    sl = {"sentences": [{"panels": ["p1"]}, {"panels": []}, {"panels": ["p2", "p3"]}]}
    assert match_rate(sl)["match_rate_pct"] == pytest.approx(66.7, abs=0.1)


def test_panel_utilisation_counts_story_art_the_viewer_never_sees():
    from manhwa2vid.measure.binding import panel_utilisation

    u = panel_utilisation(["a", "b", "c", "d"], [{"panel_id": "a"}, {"panel_id": "c"}])
    assert u["utilisation_pct"] == 50.0
    assert u["unused"] == ["b", "d"]


def test_hold_runs_says_which_basis_it_measured():
    """Without TimelineEntry.sentence_numbers the honest answer is entries-per-run, which
    UNDERSTATES the hold. It must not report that as a sentence count."""
    from manhwa2vid.measure.binding import hold_runs

    plain = hold_runs([{"panel_id": "a", "duration": 4.0, "beat_id": 1}] * 3)
    assert plain["basis"] == "entries"
    assert plain["over_limit"] == [], "no verdict when the basis cannot support one"

    numbered = hold_runs([
        {"panel_id": "a", "duration": 4.0, "beat_id": 1, "sentence_numbers": [1, 2, 3]},
        {"panel_id": "a", "duration": 4.0, "beat_id": 2, "sentence_numbers": [4, 5]},
    ])
    assert numbered["basis"] == "sentences"
    assert numbered["longest_hold"] == 5
    assert numbered["over_limit"][0]["panel_id"] == "a"


def test_timing_measured_catches_a_regression_to_word_proration():
    """Kokoro synthesizes per sentence, so its sidecar seconds are measured. Other
    providers return one clip per beat and timeline._subdivide_segments word-prorates it
    — a plausible estimate that silently decouples the cut from the speech."""
    from manhwa2vid.measure.binding import timing_measured

    sl = {"sentences": [{"beat_id": 1}, {"beat_id": 1}, {"beat_id": 2}]}
    ok = timing_measured(sl, {1: [{"seconds": 1.0}, {"seconds": 2.0}], 2: [{"seconds": 3.0}]})
    assert ok["measured_pct"] == 100.0 and ok["mismatched_beats"] == []

    prorated = timing_measured(sl, {1: [{"seconds": 3.0}], 2: [{"seconds": 3.0}]})
    assert prorated["measured_pct"] == pytest.approx(33.3, abs=0.1)
    assert prorated["mismatched_beats"] == [1]


# --- script text ----------------------------------------------------------------------

def test_dialogue_verb_lexicon_matches_the_reference_profiler():
    """A threshold derived from one counter and enforced by another is the mistake this
    project already made once. These are the exact terms reference/profile_srt.py counts,
    which is why our 31.34/1k reproduces its published 31.3."""
    from manhwa2vid.measure.script_text import DIALOGUE_VERBS

    assert DIALOGUE_VERBS == ("says", "asks", "tells", "replies", "answers", "explains", "admits")


def test_script_text_measures():
    from manhwa2vid.measure.script_text import (
        dialogue_verb_density, quoted_span_rate, sentence_length_stats,
    )

    text = 'He says it is over. She asks why. "Then leave," he tells her. It ends.'
    assert dialogue_verb_density(text)["dialogue_verbs"] == 3
    assert quoted_span_rate(text)["quoted_spans"] == 1
    stats = sentence_length_stats(text)
    assert stats["sentences"] == 4 and stats["under_8_pct"] == 100.0


def test_noun_repetition_finds_the_apothecary_case():
    """The defect a viewer counted by hand and asked a channel to fix: a bare noun
    repeated where a pronoun belonged."""
    from manhwa2vid.measure.script_text import noun_repetition

    text = ("The apothecary walked. " * 6) + "Something else entirely happened later on."
    found = noun_repetition(text, window_words=200, max_count=4)
    assert found["worst_count"] >= 6
    assert found["findings"][0]["word"] == "apothecary"


def test_noun_repetition_exempts_names_and_ignores_stopwords():
    """A recap MUST repeat its protagonist's name; the reference channel does."""
    from manhwa2vid.measure.script_text import noun_repetition

    text = ("Seo Jun-Ho fought. Seo Jun-Ho ran. Seo Jun-Ho waited. Seo Jun-Ho stood. "
            "Seo Jun-Ho turned. Seo Jun-Ho left.")
    assert noun_repetition(text, exempt={"Seo Jun-Ho"})["findings"] == []
    assert noun_repetition("the and of the and of " * 20)["findings"] == []


def test_noun_repetition_flags_any_repeated_content_word_not_only_nouns():
    """Named for the defect viewers complain about, but POS-free by design: a tagger is
    another dependency and another opinion to keep in sync, and a narration that says
    "fought" six times in a paragraph is the same defect wearing a different hat."""
    from manhwa2vid.measure.script_text import noun_repetition

    text = "He fought. She fought. They fought. We fought. You fought. All fought."
    assert noun_repetition(text)["findings"][0]["word"] == "fought"


def test_noun_repetition_folds_plurals():
    from manhwa2vid.measure.script_text import noun_repetition

    # Filler must be genuinely distinct: the word regex drops digits, so "unique0..59"
    # all stem to "unique" and would outrank the fixture's real repeat.
    import string

    filler = " ".join(a + b + "zz" for a in string.ascii_lowercase for b in "aeiou")
    text = "hunter hunters hunter hunters hunter hunters " + filler
    assert noun_repetition(text)["findings"][0]["word"] == "hunter"
