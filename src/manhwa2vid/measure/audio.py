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

    `quiet_floor_dbfs` is the p10 of window RMS and `speech_p75_dbfs` the p75. Their
    difference is reported as `duck_depth_estimate_db` and is NOT the duck depth: on long
    material it overstates by 2-7 dB, because the quietest tenth of a 6-minute mix is
    sidechain-ducked moments right after speech rather than bed-only windows. Use
    `duck_depth_from_stem` for anything that decides. This estimate stays because the bed
    floor and tonality it shares a pass with are sound, and because a number that is only
    ever compared against itself is still useful for spotting drift.

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
                "duck_depth_estimate_db": 0.0, "tonality_ratio": 0.0}

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
        "duck_depth_estimate_db": round(speech_p75 - quiet_floor, 2),
        "tonality_ratio": round(tonality, 2),
    }


def duck_depth_from_stem(narration: Path, mix: Path) -> float | None:
    """True duck depth: bed level in real narration gaps, against speech level.

    This needs the narration STEM, and that is the point. The mix alone cannot tell a
    bed-only window from a quiet moment of speech, and every percentile-of-the-mix
    estimate overstates the duck badly — measured against this on a 6:22 render: p10 of
    all windows +7.5 dB, median of the lowest quarter +6.1, p30 +2.4. Acting on those
    numbers would mean mixing the bed far too loud while a gate reported it was fine.

    So it is computed at MIX time, where the stem still exists, and handed to the render
    QA. When it is unavailable the gate reports nothing rather than a wrong number.
    """
    import tempfile

    import soundfile as sf

    def _read(path: Path) -> tuple[np.ndarray, int] | None:
        """Read any media. soundfile handles WAV; the mix is an mp4, which it cannot
        open at all — that silently returned None and the gate went quiet on a real
        render, which is exactly the failure mode this function exists to avoid."""
        try:
            data, rate = sf.read(str(path), dtype="float64", always_2d=False)
            return np.asarray(data), int(rate)
        except (OSError, RuntimeError):
            pass
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "a.wav"
            subprocess.run(
                ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(path),
                 "-vn", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
                check=False,
            )
            if not wav.exists() or wav.stat().st_size <= 44:
                return None
            data, rate = sf.read(str(wav), dtype="float64", always_2d=False)
            return np.asarray(data), int(rate)

    got_voice, got_mix = _read(narration), _read(mix)
    if got_voice is None or got_mix is None:
        return None
    voice, vr = got_voice
    mixed, mr = got_mix
    if voice.ndim > 1:
        voice = voice.mean(axis=1)
    if mixed.ndim > 1:
        mixed = mixed.mean(axis=1)

    v_db = window_rms_db(np.asarray(voice), int(vr))
    m_db = window_rms_db(np.asarray(mixed), int(mr))
    n = min(len(v_db), len(m_db))
    if n < 40:
        return None
    v_db, m_db = v_db[:n], m_db[:n]
    # A gap is where the NARRATION is essentially silent, 35 dB under its own loud level.
    gaps = v_db < (np.percentile(v_db, 95) - 35.0)
    if gaps.sum() < 20 or (~gaps).sum() < 20:
        return None
    return round(float(np.percentile(m_db[~gaps], 75)) - float(np.median(m_db[gaps])), 2)


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
