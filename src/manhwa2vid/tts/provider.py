"""Pluggable TTS providers."""

from __future__ import annotations

import os
import struct
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from manhwa2vid.config import find_repo_root, get_nested, load_config


class TTSProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str, out_path: Path, config: dict[str, Any]) -> None:
        ...


def write_silent_wav(path: Path, duration: float = 3.0, rate: int = 24000) -> None:
    """Write a quiet sine tone (not true silence) so ffmpeg loudnorm stays valid."""
    import math

    nframes = max(1, int(duration * rate))
    path.parent.mkdir(parents=True, exist_ok=True)
    # Quiet 440 Hz tone — silent WAVs make loudnorm emit NaN.
    frames = bytearray()
    for i in range(nframes):
        sample = int(800 * math.sin(2 * math.pi * 440 * i / rate))
        frames += struct.pack("<h", sample)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(frames)


class MockTTSProvider(TTSProvider):
    def synthesize(self, text: str, out_path: Path, config: dict[str, Any]) -> None:
        est = max(2.0, len(text.split()) / 2.5)
        write_silent_wav(out_path.with_suffix(".wav") if out_path.suffix != ".wav" else out_path, est)


def _resolve_provider_name(config: dict[str, Any]) -> str:
    return (
        os.getenv("TTS_PROVIDER")
        or get_nested(config, "tts", "provider", default="chatterbox")
    ).lower()


def get_tts_provider(config: dict[str, Any] | None = None) -> TTSProvider:
    from rich.console import Console

    console = Console()
    config = config or load_config()
    name = _resolve_provider_name(config)

    if name == "mock":
        return MockTTSProvider()

    if name == "kokoro":
        try:
            from manhwa2vid.tts.kokoro import KokoroTTSProvider

            return KokoroTTSProvider()
        except ImportError as exc:
            console.print(
                "[yellow]kokoro not installed.[/] "
                'Install with: pip install -e ".[tts-kokoro]"'
            )
            raise exc

    if name == "chatterbox":
        try:
            from manhwa2vid.tts.chatterbox import ChatterboxTTSProvider

            return ChatterboxTTSProvider()
        except ImportError as exc:
            console.print(
                "[yellow]chatterbox-tts not installed.[/] "
                'Install with: pip install -e ".[tts-chatterbox]"'
            )
            raise exc

    if name == "openai":
        from manhwa2vid.tts.openai import OpenAITTSProvider

        if not os.getenv("OPENAI_API_KEY"):
            console.print("[yellow]OPENAI_API_KEY missing — using silent TTS fallback.[/]")
            return MockTTSProvider()
        return OpenAITTSProvider()

    console.print(f"[yellow]Unknown TTS provider '{name}', using mock.[/]")
    return MockTTSProvider()


def resolve_voice_prompt(config: dict[str, Any]) -> Path | None:
    raw = get_nested(config, "tts", "voice_prompt") or os.getenv("TTS_VOICE_PROMPT")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = find_repo_root() / path
    return path if path.exists() else None
