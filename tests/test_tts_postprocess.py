"""TTS postprocess tests."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest

from manhwa2vid.tts.postprocess import apply_tts_postprocess


def _write_tone(path: Path, *, sr: int = 24000, seconds: float = 2.0) -> None:
    nframes = int(sr * seconds)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(struct.pack("<h", 0) * nframes)


@pytest.mark.skipif(
    __import__("shutil").which("ffmpeg") is None,
    reason="ffmpeg not available",
)
def test_pace_multiplier_slows_24khz_audio(tmp_path: Path) -> None:
    wav = tmp_path / "beat.wav"
    _write_tone(wav, sr=24000, seconds=2.0)
    apply_tts_postprocess(wav, {"tts": {"pace_multiplier": 0.75, "pitch_shift": 1.0}})

    with wave.open(str(wav), "rb") as wf:
        out_seconds = wf.getnframes() / wf.getframerate()
    assert out_seconds == pytest.approx(2.0 / 0.75, rel=0.05)
