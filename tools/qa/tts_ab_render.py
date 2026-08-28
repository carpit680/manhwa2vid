#!/usr/bin/env python3
"""Render the pronunciation A/B so a human can LISTEN. (audio-quality-spec §0.3 Script 3)

This is the step the spec could not run — its container had no egress for the model
weights. It is the gate at §0.6: the phoneme-layer finding is real, but phonemes are only
the model's input, and nobody has heard the output. Until someone does, "correct phonemes
mean correct audio" is inference.

Writes `<out>/tts_before.wav` and `<out>/tts_after.wav` from the same sentence, the only
difference being lexicon entries injected between the two renders.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

# The model's US phoneme inventory. An entry containing anything else is dropped SILENTLY
# downstream: Lexicon.__init__'s own assert runs only at init, so post-hoc injections are
# unvalidated. Hence the check below is mandatory, not defensive.
US_VOCAB = set("AIOWYbdfhijklmnpstuvwzæðŋɑɔəɛɜɡɪɹɾʃʊʌʒʤʧˈˌθᵊᵻʔ")

# Per-syllable so hyphenation and word order generalise. Korean romanisation is a keyboard
# transliteration, not a pronunciation guide: "eo" is /ʌ/ (not Leo), "eu" is /ə/ (not
# Europe), and English TTS gets both wrong by applying its own spelling rules.
LEXICON: dict[str, str] = {
    # Return of the Frozen Player
    "Seo": "sˈʌ",        # 서 /sʌ/ — espeak says "SEE-oh"
    "Jun": "ʤˈʌn",
    "Ho": "hˈO",
    "Deok": "dˈʌk",      # 덕 — espeak says "dee-OCK"
    "gu": "ɡˈu",
    "Skaya": "skˈɑjə",
    "Khali": "kˈɑli",
    "Rahat": "ɹˈɑhɑt",
    "Mio": "mˈiO",
    "Shim": "ʃˈɪm",
    # Solo Leveling
    "Chi": "ʧˈi",        # 치 — espeak says "KAI"
    "Yul": "jˈʌl",
    "Song": "sˈɔŋ",
    "Ju": "ʤˈu",
    "Hee": "hˈi",
    "Bak": "bˈɑk",       # 박 — espeak says "back"
    "Sang": "sˈɑŋ",
    "Shik": "ʃˈɪk",
    "Jin": "ʤˈɪn",
    "Woo": "wˈu",
    # One place, one pronunciation — the shipped video says both kˈɑɹθɛnən and
    # kˈɑɹtɛnən because the glossary carries two spellings of it.
    "Carthenon": "kˈɑɹθənɑn",
    "Cartenon": "kˈɑɹθənɑn",
}

SENTENCE = (
    "Seo Jun-Ho remembers Skaya and Deok-gu. "
    "Song Chi-Yul and Ju-Hee reached the Carthenon Temple, and Bak followed."
)


def validate(lexicon: dict[str, str]) -> list[str]:
    """Every phoneme must be in the model's vocabulary, or it is dropped in silence."""
    bad = []
    for word, phonemes in lexicon.items():
        illegal = sorted({c for c in phonemes if c not in US_VOCAB})
        if illegal:
            bad.append(f"{word}: illegal {illegal}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("_review"))
    ap.add_argument("--voice", default=None, help="default: config's tts.kokoro_voice")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--sentence", default=SENTENCE)
    args = ap.parse_args()

    problems = validate(LEXICON)
    if problems:
        print("LEXICON INVALID — refusing to inject:")
        for p in problems:
            print("  " + p)
        return 1
    print(f"lexicon: {len(LEXICON)} entries, all phonemes legal")

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    from manhwa2vid.config import get_nested, load_config

    voice = args.voice or str(get_nested(load_config(), "tts", "kokoro_voice", default="am_adam"))
    args.out.mkdir(parents=True, exist_ok=True)
    pipeline = KPipeline(lang_code="a")
    print(f"voice={voice} speed={args.speed} espeak_fallback={pipeline.g2p.fallback is not None}")

    def render(tag: str) -> None:
        chunks, phonemes = [], []
        for result in pipeline(args.sentence, voice=voice, speed=args.speed):
            phonemes.append(result.phonemes)
            audio = result.audio
            chunks.append(audio.numpy() if hasattr(audio, "numpy") else np.asarray(audio))
        path = args.out / f"tts_{tag}.wav"
        sf.write(str(path), np.concatenate(chunks), 24000)
        print(f"\n[{tag}] {' '.join(phonemes)}")
        print(f"[{tag}] wrote {path}")

    render("before")
    for word, phonemes in LEXICON.items():
        for variant in {word, word.lower(), word.upper(), word.capitalize()}:
            pipeline.g2p.lexicon.golds[variant] = phonemes
    render("after")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
