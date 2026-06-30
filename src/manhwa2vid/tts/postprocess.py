"""Post-process synthesized narration audio (pace, pitch)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

from manhwa2vid.config import get_nested


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _wav_sample_rate(path: Path) -> int:
    with wave.open(str(path), "rb") as wf:
        return wf.getframerate()


def _atempo_filters(factor: float) -> list[str]:
    """Build atempo chain; ffmpeg only accepts 0.5–2.0 per filter."""
    filters: list[str] = []
    remaining = factor
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    if abs(remaining - 1.0) >= 0.001:
        filters.append(f"atempo={remaining:.6f}")
    return filters


def apply_tts_postprocess(wav_path: Path, config: dict[str, Any]) -> None:
    pace = float(get_nested(config, "tts", "pace_multiplier", default=1.0))
    pitch = float(get_nested(config, "tts", "pitch_shift", default=1.0))

    if abs(pace - 1.0) < 0.001 and abs(pitch - 1.0) < 0.001:
        return
    if not _ffmpeg_available():
        return

    sr = _wav_sample_rate(wav_path)
    filters: list[str] = []

    if abs(pitch - 1.0) >= 0.001:
        # Lower pitch without changing duration (must use the file's real sample rate).
        filters.append(f"asetrate={sr}*{pitch:.6f}")
        filters.extend(_atempo_filters(1.0 / pitch))
        filters.append(f"aresample={sr}")

    if abs(pace - 1.0) >= 0.001:
        filters.extend(_atempo_filters(pace))

    filter_chain = ",".join(filters)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(wav_path),
                "-af",
                filter_chain,
                str(tmp_path),
            ],
            check=True,
        )
        tmp_path.replace(wav_path)
    finally:
        if tmp_path.exists() and tmp_path != wav_path:
            tmp_path.unlink(missing_ok=True)
