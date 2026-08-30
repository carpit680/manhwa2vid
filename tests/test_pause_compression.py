"""Internal pauses: the comma is longer than the full stop.

`kokoro_trim_ms` cuts each sentence's lead and trail, so tightening the sentence
boundaries left Kokoro's INTERNAL pauses untouched and therefore relatively longer.
Measured on Frozen Player beat_010 (9 sentences, 33.6 s): internal silences ran to
516 ms, 10 of 55 over 150 ms, against a ~210 ms gap between whole sentences. The user
heard it as "the pause the narration takes after a comma is longer than it should be".

These pin the shape of the fix rather than a wpm number: audio must be removed only from
silence, only from the middle of it, and speech samples must survive bit-identical.
"""

from __future__ import annotations

import numpy as np
import pytest

from manhwa2vid.tts.kokoro import SAMPLE_RATE, _compress_pauses


def _ms(n: float) -> int:
    return int(SAMPLE_RATE * n / 1000.0)


def _tone(ms: float, amp: float = 0.5) -> np.ndarray:
    t = np.arange(_ms(ms), dtype="float32") / SAMPLE_RATE
    return (amp * np.sin(2 * np.pi * 220 * t)).astype("float32")


def _silence(ms: float) -> np.ndarray:
    return np.zeros(_ms(ms), dtype="float32")


def _quiet_run_lengths(audio: np.ndarray) -> list[int]:
    """Every run of silence in the signal, in samples — the same framed 2%-of-peak rule.

    Framed, not per-sample: any waveform crosses zero every cycle, so a per-sample
    threshold reports each crossing as its own one-sample silence.
    """
    frame = int(SAMPLE_RATE * 0.005)
    env = np.abs(audio)
    n = (env.size + frame - 1) // frame
    padded = np.zeros(n * frame, dtype="float32")
    padded[: env.size] = env
    per_frame = padded.reshape(n, frame).max(axis=1) <= float(env.max()) * 0.02
    quiet = np.repeat(per_frame, frame)[: env.size]
    runs, count = [], 0
    for q in quiet:
        if q:
            count += 1
        elif count:
            runs.append(count)
            count = 0
    if count:
        runs.append(count)
    return runs


def test_a_long_comma_pause_is_capped():
    audio = np.concatenate([_tone(300), _silence(500), _tone(300)])
    out = _compress_pauses(audio, 120.0)
    assert _quiet_run_lengths(out) == [pytest.approx(_ms(120), abs=2)]


def test_a_pause_already_short_enough_is_untouched():
    audio = np.concatenate([_tone(300), _silence(80), _tone(300)])
    out = _compress_pauses(audio, 120.0)
    assert np.array_equal(out, audio)


def test_speech_survives_bit_identical():
    """Only silence may be removed. A cap that eats into a word would slur it."""
    a, b = _tone(300, 0.5), _tone(300, 0.4)
    out = _compress_pauses(np.concatenate([a, _silence(500), b]), 120.0)
    loud = out[np.abs(out) > 0]
    assert np.array_equal(loud, np.concatenate([a, b])[np.abs(np.concatenate([a, b])) > 0])


def test_the_cut_is_taken_from_the_middle_of_the_pause():
    """Keeping both edges preserves the decay of the word before and the onset ramp of
    the word after; slicing off one end clips one of them."""
    ramp_down = np.linspace(0.4, 0.0, _ms(30), dtype="float32")
    ramp_up = np.linspace(0.0, 0.4, _ms(30), dtype="float32")
    audio = np.concatenate([_tone(200), ramp_down, _silence(400), ramp_up, _tone(200)])
    out = _compress_pauses(audio, 120.0)
    # Both ramps are quiet by the 2% rule for most of their length, so assert on energy:
    # a middle cut leaves the sum of the ramps' samples intact at both edges.
    assert out[_ms(200)] == pytest.approx(0.4, abs=0.02), "the decay edge was clipped"
    assert out[-_ms(200) - 1] == pytest.approx(0.4, abs=0.02), "the onset edge was clipped"


def test_several_pauses_are_each_capped():
    audio = np.concatenate([
        _tone(200), _silence(400), _tone(200), _silence(90), _tone(200), _silence(600),
        _tone(200),
    ])
    out = _compress_pauses(audio, 120.0)
    runs = _quiet_run_lengths(out)
    assert len(runs) == 3
    assert runs[0] == pytest.approx(_ms(120), abs=2)
    assert runs[1] == pytest.approx(_ms(90), abs=2), "a short pause was shortened anyway"
    assert runs[2] == pytest.approx(_ms(120), abs=2)


def test_zero_disables_it():
    audio = np.concatenate([_tone(300), _silence(500), _tone(300)])
    assert np.array_equal(_compress_pauses(audio, 0.0), audio)


def test_silence_is_relative_to_the_segment_not_absolute():
    """A quietly-read sentence must not be mistaken for silence end to end."""
    audio = np.concatenate([_tone(300, 0.02), _silence(500), _tone(300, 0.02)])
    out = _compress_pauses(audio, 120.0)
    assert out.size == pytest.approx(audio.size - _ms(380), abs=4)


@pytest.mark.parametrize("audio", [
    np.zeros(0, dtype="float32"),
    np.zeros(1000, dtype="float32"),
    np.array([0.5], dtype="float32"),
])
def test_degenerate_input_does_not_raise(audio):
    _compress_pauses(audio, 120.0)


def test_it_never_lengthens_audio():
    rng = np.random.default_rng(0)
    audio = (rng.standard_normal(SAMPLE_RATE) * 0.1).astype("float32")
    assert _compress_pauses(audio, 120.0).size <= audio.size
