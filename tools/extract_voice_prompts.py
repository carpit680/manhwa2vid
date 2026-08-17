"""Cut clean voice-prompt clips out of a reference narration WAV.

Picks the segments with the most continuous speech and the least dead air, which is what
zero-shot cloning wants — a few seconds of steady, unbroken delivery.

    python tools/extract_voice_prompts.py reference/voice_src_10475.wav --out assets/voices
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf


def frame_db(audio: np.ndarray, sr: int, hop: float = 0.02) -> tuple[np.ndarray, int]:
    fl = int(hop * sr)
    n = len(audio) // fl
    rms = np.array([np.sqrt((audio[i * fl : (i + 1) * fl] ** 2).mean()) for i in range(n)])
    return 20 * np.log10(np.maximum(rms, 1e-9)), fl


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--out", default="assets/voices")
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--seconds", type=float, default=9.0)
    ap.add_argument("--prefix", default="mamoru")
    args = ap.parse_args()

    audio, sr = sf.read(args.source)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    db, fl = frame_db(audio, sr)
    speech_floor = np.percentile(db, 45)  # frames above this are speech
    is_speech = db > speech_floor

    win_frames = int(args.seconds / 0.02)
    if win_frames >= len(is_speech):
        raise SystemExit("source shorter than requested clip length")

    # score every window by speech density, then greedily take non-overlapping winners
    density = np.convolve(is_speech.astype(float), np.ones(win_frames) / win_frames, mode="valid")
    order = np.argsort(-density)

    chosen: list[int] = []
    for idx in order:
        if len(chosen) >= args.count:
            break
        if all(abs(int(idx) - c) >= win_frames for c in chosen):
            chosen.append(int(idx))
    chosen.sort()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for n, start_frame in enumerate(chosen, start=1):
        start = start_frame * fl
        clip = audio[start : start + int(args.seconds * sr)]
        # trim to zero crossings so the clip does not start or end mid-waveform
        clip = clip - clip.mean()
        peak = float(np.abs(clip).max())
        if peak > 0:
            clip = clip * (0.89 / peak)
        path = out_dir / f"{args.prefix}_{n:02d}.wav"
        sf.write(str(path), clip, sr)
        t = start / sr
        print(
            f"{path}  from {t:6.1f}s  speech_density={density[start_frame]:.2f}  "
            f"peak={float(np.abs(clip).max()):.2f}"
        )


if __name__ == "__main__":
    main()
