"""Local Kokoro-82M TTS (Apache-2.0, preset voices, ~7x realtime on GPU)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.tts.provider import TTSProvider

console = Console()

_pipeline: Any = None
_pipeline_key: str | None = None

# Kokoro always synthesizes at 24 kHz.
SAMPLE_RATE = 24000


def _load_pipeline(config: dict[str, Any]) -> Any:
    """Kokoro's pipeline is cheap to hold and expensive to build — cache per lang_code."""
    global _pipeline, _pipeline_key

    lang_code = str(get_nested(config, "tts", "kokoro_lang", default="a"))
    if _pipeline is not None and _pipeline_key == lang_code:
        return _pipeline

    from kokoro import KPipeline

    console.print(f"[dim]Loading Kokoro pipeline (lang_code={lang_code})...[/]")
    _pipeline = KPipeline(lang_code=lang_code)
    _pipeline_key = lang_code
    return _pipeline


class KokoroTTSProvider(TTSProvider):
    """
    Preset-voice synthesis. Kokoro cannot clone a reference voice — tts.voice_prompt is
    ignored here. Pick a voice with tts.kokoro_voice (e.g. am_adam, am_michael, bm_george).

    Note that tts.kokoro_speed is a synthesis parameter, not a post-hoc time-stretch: the
    model speaks faster rather than the audio being resampled, so raising it does not
    introduce the atempo artifacts that tts.pace_multiplier would.
    """

    def synthesize(self, text: str, out_path: Path, config: dict[str, Any]) -> None:
        import numpy as np
        import soundfile as sf

        pipeline = _load_pipeline(config)
        voice = str(get_nested(config, "tts", "kokoro_voice", default="am_adam"))
        speed = float(get_nested(config, "tts", "kokoro_speed", default=1.0))

        out_wav = out_path.with_suffix(".wav")
        out_wav.parent.mkdir(parents=True, exist_ok=True)

        # Keep the (sentence text, audio) pairing — Kokoro splits on sentence
        # boundaries internally, so per-sentence durations are produced for free at
        # synthesis time. They were thrown away for the pipeline's whole life, which is
        # why every panel in a beat dwelt for an identical slice of the beat's audio:
        # the timeline had no idea WHEN in the beat each sentence was spoken.
        segments: list[tuple[str, Any]] = [
            (graphemes, audio) for graphemes, _phonemes, audio in pipeline(text, voice=voice, speed=speed)
        ]
        chunks = [audio for _g, audio in segments]
        if not chunks:
            raise RuntimeError(f"Kokoro returned no audio for: {text[:60]!r}")

        if len(chunks) == 1:
            audio = np.asarray(chunks[0], dtype="float32")
        else:
            # Kokoro splits long text on sentence boundaries; pad slightly so the joins
            # do not sound clipped together.
            gap = np.zeros(int(0.06 * SAMPLE_RATE), dtype="float32")
            padded: list[Any] = []
            for i, chunk in enumerate(chunks):
                if i:
                    padded.append(gap)
                padded.append(np.asarray(chunk, dtype="float32"))
            audio = np.concatenate(padded)

        # Sidecar: exact per-sentence timing, join gaps folded into the preceding
        # segment so the seconds sum to the WAV's real duration.
        import json as _json

        sidecar = []
        for i, (graphemes, chunk) in enumerate(segments):
            seconds = len(np.asarray(chunk)) / SAMPLE_RATE
            if i:
                seconds += 0.06
            sidecar.append({"text": str(graphemes).strip(), "seconds": round(seconds, 4)})
        out_wav.with_suffix(".segments.json").write_text(
            _json.dumps(sidecar, ensure_ascii=False, indent=1), encoding="utf-8"
        )

        peak = float(abs(audio).max()) if audio.size else 0.0
        if peak > 0.89:
            audio = audio * (0.89 / peak)

        sf.write(str(out_wav), audio, SAMPLE_RATE)

        from manhwa2vid.tts.postprocess import apply_tts_postprocess

        apply_tts_postprocess(out_wav, config)
