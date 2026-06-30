"""OpenAI cloud TTS."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from manhwa2vid.config import get_nested
from manhwa2vid.tts.provider import TTSProvider, write_silent_wav


class OpenAITTSProvider(TTSProvider):
    def synthesize(self, text: str, out_path: Path, config: dict[str, Any]) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        out_wav = out_path.with_suffix(".wav")
        if not api_key:
            est = max(2.0, len(text.split()) / 2.5)
            write_silent_wav(out_wav, est)
            return

        model = get_nested(config, "tts", "openai_model") or get_nested(config, "tts", "model", default="tts-1")
        voice = get_nested(config, "tts", "voice", default="onyx")
        speed = float(get_nested(config, "tts", "speed", default=1.0))

        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        mp3_path = out_path.with_suffix(".mp3")
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        with client.audio.speech.with_streaming_response.create(
            model=model,
            voice=voice,
            input=text,
            speed=speed,
            response_format="mp3",
        ) as response:
            response.stream_to_file(mp3_path)

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(mp3_path),
                "-ar",
                "24000",
                "-ac",
                "1",
                str(out_wav),
            ],
            check=True,
        )
        mp3_path.unlink(missing_ok=True)

        from manhwa2vid.tts.postprocess import apply_tts_postprocess

        apply_tts_postprocess(out_wav, config)
