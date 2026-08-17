"""Render one narration line through several Chatterbox voice settings for A/B listening.

Always synthesizes at natural pace with NO ffmpeg post-processing (no atempo time-stretch,
no resample-based pitch shift) — those are what make the output sound artificial.

    python tools/voice_lab.py                       # default grid, built-in sample line
    python tools/voice_lab.py --text "your line"    # your own copy
    python tools/voice_lab.py --out reference/voice_lab

Drop 5-10s reference WAVs into assets/voices/ and each one is added to the grid as a
cloned voice, which is the only way to get a genuinely different timbre out of Chatterbox.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

# A neutral recap-style line: fast, present tense, reported speech — matches the target style.
SAMPLE_TEXT = (
    "The guild clerk tells him the raid is already full, and he just nods and turns away. "
    "Outside, he counts what is left of his money, then checks the gate timer again. "
    "He has one shot at this, and he knows it."
)

# (exaggeration, cfg_weight, label)
DEFAULT_GRID = [
    (0.3, 0.3, "flat-loose"),
    (0.3, 0.6, "flat-steady"),
    (0.5, 0.4, "neutral-loose"),
    (0.5, 0.6, "neutral-steady"),
    (0.7, 0.4, "lively-loose"),
    (0.7, 0.6, "lively-steady"),
]

SLIM_GRID = [
    (0.3, 0.5, "flat"),
    (0.5, 0.5, "neutral"),
    (0.7, 0.5, "lively"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default=SAMPLE_TEXT)
    ap.add_argument("--out", default="reference/voice_lab")
    ap.add_argument("--device", default=None, help="cuda | cpu | mps (default: config/auto)")
    ap.add_argument("--grid", choices=("full", "slim"), default="full")
    ap.add_argument(
        "--voices",
        default="all",
        help="'all' (default voice + every assets/voices WAV), 'default', or comma-separated WAV stems",
    )
    args = ap.parse_args()
    grid = DEFAULT_GRID if args.grid == "full" else SLIM_GRID

    import soundfile as sf
    import numpy as np

    from manhwa2vid.config import load_config
    from manhwa2vid.tts.chatterbox import ChatterboxTTSProvider

    config = load_config()
    base_tts = dict(config.get("tts") or {})
    # Hard-disable post-processing regardless of what config.yaml says.
    base_tts["pace_multiplier"] = 1.0
    base_tts["pitch_shift"] = 1.0
    base_tts["provider"] = "chatterbox"
    base_tts["model"] = "standard"
    if args.device:
        base_tts["device"] = args.device

    out_dir = REPO / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    voices_dir = REPO / "assets" / "voices"
    wanted = [v.strip() for v in args.voices.split(",") if v.strip()]
    prompts: list[tuple[str, str | None]] = []
    if args.voices in ("all", "default") or "default" in wanted:
        prompts.append(("default", None))
    if args.voices != "default" and voices_dir.exists():
        for wav in sorted(voices_dir.glob("*.wav")):
            if args.voices == "all" or wav.stem in wanted:
                prompts.append((wav.stem, str(wav)))
    if not prompts:
        raise SystemExit(f"no voices matched {args.voices!r} in {voices_dir}")

    provider = ChatterboxTTSProvider()
    words = len(args.text.split())
    rows: list[tuple[str, float, float, float]] = []

    print(f"{len(grid) * len(prompts)} samples -> {out_dir}")
    for voice_label, prompt_path in prompts:
        for exaggeration, cfg_weight, label in grid:
            name = f"{voice_label}__{label}_ex{exaggeration}_cfg{cfg_weight}.wav"
            out_path = out_dir / name
            cfg = {
                **config,
                "tts": {
                    **base_tts,
                    "exaggeration": exaggeration,
                    "cfg_weight": cfg_weight,
                    "voice_prompt": prompt_path,
                },
            }
            start = time.time()
            provider.synthesize(args.text, out_path, cfg)
            data, sr = sf.read(str(out_path))
            duration = len(data) / sr
            rows.append((name, duration, words / (duration / 60), float(np.abs(data).max())))
            print(f"  {name:52s} {duration:5.1f}s  {words/(duration/60):5.0f} wpm  "
                  f"peak={float(np.abs(data).max()):.2f}  ({time.time()-start:.0f}s)")

    print(f"\n{'sample':52s} {'dur':>6} {'wpm':>6} {'peak':>6}")
    for name, duration, wpm, peak in sorted(rows, key=lambda r: r[2]):
        print(f"{name:52s} {duration:5.1f}s {wpm:6.0f} {peak:6.2f}")
    print(f"\nReference channel speaks at 237 wpm. These are unprocessed natural pace.")
    print(f"Listen, pick one, then set tts.exaggeration / tts.cfg_weight (and voice_prompt) in config.yaml.")


if __name__ == "__main__":
    main()
