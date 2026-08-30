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



def _resolve_voice(pipeline: Any, spec: str) -> Any:
    """A voice name, or a weighted blend of them.

    Kokoro voices are (510, 1, 256) style tensors, so two can be interpolated into a
    voice that exists in neither preset — and the blend changes DELIVERY, not just
    timbre, which is why it is a synthesis-time choice rather than an EQ one. Kokoro's
    own "a,b" syntax averages equally; this accepts weights:

        af_heart                      a preset, unchanged
        af_heart:0.65,af_nicole:0.35  weighted blend, chosen by ear 2026-08-29

    Weights are normalised, so 65/35 and 0.65/0.35 mean the same thing.
    """
    if ":" not in spec:
        return spec
    parts = []
    for token in spec.split(","):
        name, _, weight = token.partition(":")
        parts.append((name.strip(), float(weight or 1.0)))
    total = sum(w for _n, w in parts) or 1.0
    blended = None
    for name, weight in parts:
        vec = pipeline.load_single_voice(name) * (weight / total)
        blended = vec if blended is None else blended + vec
    return blended


def _trim_silence(audio: Any, keep_ms: float) -> Any:
    """Cut Kokoro's own lead/trail silence back to `keep_ms` a side.

    Measured on a six-sentence passage: Kokoro emits ~250 ms of lead and ~500 ms of
    trail PER SENTENCE — 4.6 s of dead air against the 0.36 s of join gap we add
    ourselves. Because we synthesise one sentence per call to keep timings measured,
    that silence lands at every sentence boundary and the read drags without the
    articulation being slow.

    Trimming raises words-per-minute without touching speed: at 1.30 the same passage
    went 155 -> 179 wpm with the voice reading no faster. It is applied per segment
    BEFORE the sidecar is measured, so picture and sound stay joined — the shot planner
    reads those durations.

    0 disables it. Silence is detected at 2% of the segment's own peak, so a quiet
    sentence is not mistaken for silence.
    """
    import numpy as np

    if keep_ms <= 0 or audio.size == 0:
        return audio
    envelope = np.abs(audio)
    peak = float(envelope.max())
    if peak <= 0:
        return audio
    loud = np.nonzero(envelope > peak * 0.02)[0]
    if loud.size == 0:
        return audio
    keep = int(SAMPLE_RATE * keep_ms / 1000.0)
    return audio[max(0, int(loud[0]) - keep) : min(audio.size, int(loud[-1]) + keep)]


def _compress_pauses(audio: Any, max_ms: float) -> Any:
    """Cap the silences INSIDE one sentence — the pauses at commas and dashes.

    `_trim_silence` only touches each sentence's lead and trail, so tightening the
    boundaries left Kokoro's internal pauses untouched and therefore relatively longer.
    Measured on Frozen Player beat_010 (9 sentences, 33.6 s), the prosody came out
    inverted: internal silences ran to 516 ms with 10 of 55 over 150 ms, against a
    ~210 ms gap between whole sentences. Nine comma pauses in one beat were longer than
    the breaks between the sentences around them, which is what "the pause after a comma
    is longer than it should be" sounds like.

    Over the whole FP script (112 sentences, 406.2 s) a 120 ms cap recovers 26.4 s —
    6.5% of runtime — and lifts delivered pace without the voice articulating any faster.

    The cut is taken from the MIDDLE of each pause, keeping `max_ms/2` a side, so the
    decay of the word before and the onset ramp of the word after both survive; slicing
    off one end clips them. Silence is detected at 2% of the segment's own peak, the same
    relative threshold `_trim_silence` uses, so a quietly-read sentence is not mistaken
    for silence.

    The cap is a floor on what may be shortened, which is what keeps it safe: a plosive
    closure (the held /t/ or /k/ inside a word) runs well under 120 ms, so at that
    setting only phrase-boundary pauses are touched. Lowering it far below 100 ms starts
    to risk clipping those closures and slurring the consonant.

    0 disables it. Applied per segment BEFORE the sidecar is measured, so picture and
    sound stay joined — the shot planner reads those durations.
    """
    import numpy as np

    if max_ms <= 0 or audio.size == 0:
        return audio
    envelope = np.abs(audio)
    peak = float(envelope.max())
    if peak <= 0:
        return audio

    limit = int(SAMPLE_RATE * max_ms / 1000.0)
    if limit <= 0:
        return audio

    # Silence is judged on a FRAMED envelope, not on raw samples. Any waveform crosses
    # zero on the way through every cycle, so a per-sample threshold marks each crossing
    # as its own one-sample "silence" and the run lengths it reports are meaningless.
    # 5 ms frames are short against the 120 ms being capped and long enough to span a
    # glottal period at any speaking pitch.
    frame = max(1, int(SAMPLE_RATE * 0.005))
    n_frames = (audio.size + frame - 1) // frame
    padded = np.zeros(n_frames * frame, dtype="float32")
    padded[: audio.size] = envelope
    quiet = padded.reshape(n_frames, frame).max(axis=1) <= peak * 0.02

    # Boundaries of every quiet run, via the transitions of the boolean mask.
    edges = np.flatnonzero(np.diff(quiet.astype(np.int8)))
    starts = np.concatenate(([0], edges + 1))
    ends = np.concatenate((edges + 1, [n_frames]))

    keep: list[Any] = []
    for f0, f1 in zip(starts.tolist(), ends.tolist()):
        start, end = f0 * frame, min(f1 * frame, audio.size)
        if not quiet[f0] or (end - start) <= limit:
            keep.append(audio[start:end])
            continue
        half = limit // 2
        keep.append(audio[start : start + half])
        keep.append(audio[end - (limit - half) : end])
    return np.concatenate(keep) if keep else audio


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
        voice = _resolve_voice(
            pipeline, str(get_nested(config, "tts", "kokoro_voice", default="am_adam"))
        )
        speed = float(get_nested(config, "tts", "kokoro_speed", default=1.0))
        trim_ms = float(get_nested(config, "tts", "kokoro_trim_ms", default=150.0))
        max_pause_ms = float(
            get_nested(config, "tts", "kokoro_max_pause_ms", default=120.0)
        )

        out_wav = out_path.with_suffix(".wav")
        out_wav.parent.mkdir(parents=True, exist_ok=True)

        # ONE pipeline call PER SENTENCE, using the same splitter as the shot planner.
        # Kokoro's own internal chunking groups sentences up to a token budget — the
        # 2026-08-26 audit measured chunks holding up to 9 sentences, leaving 92-94% of
        # per-sentence timings to be ESTIMATED by character count downstream (worth
        # ~1.5s of cut drift inside a 22s chunk, over half a reference shot). Feeding
        # one sentence per call makes every sidecar entry a measured duration, and
        # sentence identity with the shot list holds by construction.
        from manhwa2vid.script.sentences import split_sentences

        sentences = split_sentences(text) or [text]
        segments: list[tuple[str, Any]] = []
        for sentence in sentences:
            pieces = [audio for _g, _p, audio in pipeline(sentence, voice=voice, speed=speed)]
            if not pieces:
                continue
            merged = (
                np.asarray(pieces[0], dtype="float32")
                if len(pieces) == 1
                else np.concatenate([np.asarray(p, dtype="float32") for p in pieces])
            )
            # Trim the edges first, then the interior: the trail silence is not a
            # pause the listener hears as punctuation, and compressing it first would
            # leave _trim_silence a shorter tail to work from.
            trimmed = _trim_silence(merged, trim_ms)
            segments.append((sentence, _compress_pauses(trimmed, max_pause_ms)))
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

        peak = float(abs(audio).max()) if audio.size else 0.0
        if peak > 0.89:
            audio = audio * (0.89 / peak)

        sf.write(str(out_wav), audio, SAMPLE_RATE)

        from manhwa2vid.tts.postprocess import apply_tts_postprocess

        apply_tts_postprocess(out_wav, config)

        # Sidecar: exact per-sentence timing, join gaps folded into the preceding
        # segment. Written AFTER postprocess and rescaled to the final WAV so the
        # seconds still sum to the real duration even when tts.pace_multiplier
        # time-stretches the audio (atempo is a uniform stretch, so proportional
        # rescaling stays exact).
        import json as _json
        import wave as _wave

        sidecar = []
        for i, (graphemes, chunk) in enumerate(segments):
            seconds = len(np.asarray(chunk)) / SAMPLE_RATE
            if i:
                seconds += 0.06
            sidecar.append({"text": str(graphemes).strip(), "seconds": seconds})
        with _wave.open(str(out_wav), "rb") as wf:
            final_duration = wf.getnframes() / wf.getframerate()
        pre_duration = sum(s["seconds"] for s in sidecar) or 1.0
        scale = final_duration / pre_duration
        for s in sidecar:
            s["seconds"] = round(s["seconds"] * scale, 4)
        out_wav.with_suffix(".segments.json").write_text(
            _json.dumps(sidecar, ensure_ascii=False, indent=1), encoding="utf-8"
        )
