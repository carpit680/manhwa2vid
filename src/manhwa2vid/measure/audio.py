"""Audio measurement on the finished mix.

Split deliberately in two:

* `audio_metrics(samples, sr)` is PURE NUMPY. It is the unit-test seam — tests synthesize
  a voice-over-bed array and assert the gate verdict without going near ffmpeg, which is
  what keeps the offline suite fast.
* `loudness_metrics(video)` shells out to ffmpeg's `loudnorm` because LUFS and true peak
  are EBU R128 and reimplementing them would be a second detector for no gain.

Measured on the MIX, not the narration stems: `_mix_audio` unlinks the narration wav, and
the beat wavs predate the loudnorm gain applied to the mix, so the stems would answer a
question about a file nobody ships.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

WINDOW_S = 0.050   # 50 ms — long enough to be stable, short enough to sit inside a pause
HOP_S = 0.025


def _db(x: np.ndarray | float) -> Any:
    return 20.0 * np.log10(np.asarray(x, dtype=np.float64) + 1e-9)


def window_rms_db(samples: np.ndarray, sr: int) -> np.ndarray:
    """RMS of each 50 ms window, in dBFS."""
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    n = max(int(WINDOW_S * sr), 1)
    hop = max(int(HOP_S * sr), 1)
    if len(samples) < n:
        return np.array([_db(float(np.sqrt(np.mean(samples**2))) if len(samples) else 0.0)])
    starts = np.arange(0, len(samples) - n + 1, hop)
    rms = np.sqrt(np.array([float(np.mean(samples[s : s + n] ** 2)) for s in starts]))
    return _db(rms)


def audio_metrics(samples: np.ndarray, sr: int) -> dict[str, Any]:
    """Bed level, ducking depth and whether the bed is music at all.

    `quiet_floor_dbfs` is the p10 of window RMS: the narration has gaps, and what is
    audible in them is the music bed. `speech_p75_dbfs` is the p75, i.e. a
    narration-dominated window. Their difference is the duck depth a viewer hears.

    `tonality_ratio` separates "there is music under this" from "there is hiss under
    this": averaged spectra of the quiet windows, peak over mean across 80-2000 Hz.
    Music is peaky (measured 7.0 and 6.6 on the two 2026-08-27 previews); broadband
    noise or room tone sits near 1-2. Without it, an empty `assets/bgm/` directory and a
    quiet bed are indistinguishable — and the bed IS chosen by globbing that directory.
    """
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    samples = np.asarray(samples, dtype=np.float64)
    if not samples.size:
        return {"quiet_floor_dbfs": -120.0, "speech_p75_dbfs": -120.0,
                "duck_depth_db": 0.0, "tonality_ratio": 0.0}

    rms_db = window_rms_db(samples, sr)
    quiet_floor = float(np.percentile(rms_db, 10))
    speech_p75 = float(np.percentile(rms_db, 75))

    # Spectrum of the quietest windows only — that is the bed with the voice out of the way.
    n = max(int(WINDOW_S * sr), 1)
    hop = max(int(HOP_S * sr), 1)
    starts = np.arange(0, max(len(samples) - n + 1, 1), hop)
    quiet_idx = np.flatnonzero(rms_db <= quiet_floor + 2.0)[:400]
    tonality = 0.0
    if quiet_idx.size and len(samples) >= n:
        win = np.hanning(n)
        spec = np.zeros(n // 2 + 1)
        used = 0
        for k in quiet_idx:
            s = int(starts[min(k, len(starts) - 1)])
            seg = samples[s : s + n]
            if len(seg) < n:
                continue
            spec += np.abs(np.fft.rfft(seg * win))
            used += 1
        if used:
            spec /= used
            freqs = np.fft.rfftfreq(n, 1.0 / sr)
            band = (freqs >= 80.0) & (freqs <= 2000.0)
            if band.any() and float(spec[band].mean()) > 0:
                tonality = float(spec[band].max() / spec[band].mean())

    return {
        "quiet_floor_dbfs": round(quiet_floor, 2),
        "speech_p75_dbfs": round(speech_p75, 2),
        "duck_depth_db": round(speech_p75 - quiet_floor, 2),
        "tonality_ratio": round(tonality, 2),
    }


def loudness_metrics(video: Path) -> dict[str, Any]:
    """Integrated loudness and true peak, via ffmpeg's loudnorm measurement pass."""
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-i", str(video),
         "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    start = proc.stderr.rfind("{")
    if start == -1:
        return {}
    try:
        data = json.loads(proc.stderr[start:])
        return {
            "true_peak_dbtp": float(data["input_tp"]),
            "loudness_lufs": float(data["input_i"]),
            "loudness_range_lu": float(data["input_lra"]),
        }
    except (ValueError, TypeError, KeyError):
        return {}


def measure_audio(video: Path, *, sr: int = 48000) -> dict[str, Any]:
    """Everything measurable about the finished audio."""
    import tempfile

    metrics = loudness_metrics(video)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "mix.wav"
        subprocess.run(
            ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(video),
             "-vn", "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(wav)],
            check=False,
        )
        if wav.exists() and wav.stat().st_size > 44:
            import soundfile as sf

            samples, rate = sf.read(str(wav), dtype="float64", always_2d=False)
            metrics.update(audio_metrics(np.asarray(samples), int(rate)))
    return metrics
