#!/usr/bin/env python3
"""Render the pronunciation A/B so a human can LISTEN. (audio-quality-spec §0.3 Script 3)

VERDICT 2026-08-28: BOTH lexicons were REJECTED at the §0.6 listening gate. The 27-entry
v1 lost to espeak (over-articulation, +26% articulation rate), and so did the 8-entry
MIN_LEX from correction-01 — even though it changed only two words on this repo's rosters
and measured -6.2% articulation, i.e. it fixed the defect v1 was rejected for.

Two attempts with opposite designs, both worse to the user's ear. NO LEXICON IS WIRED INTO
THE PIPELINE, and none should be added without a fresh A/B that the user accepts. Keep
this tool: it is the harness for that A/B, and the probes beside it document a separate
failure mode that IS worth guarding (see tts_g2p_probe.py).

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

# MIN_LEX — docs/audio-quality-spec-correction-01.md §4. This REPLACES the 27-entry
# lexicon in audio-quality-spec.md §0.4, which was rejected at the §0.6 listening gate:
# the user judged the espeak baseline to sound BETTER than the corrected phonemes.
#
# The diagnosis was over-articulation — 46 syllable peaks against espeak's 38, in a
# SHORTER take. Two causes, both in the original spec: every per-syllable entry carried
# its own primary stress, so concatenation put two stresses inside one name; and every
# vowel was written full, never reduced, which is phonetically faithful Korean and
# unnatural English.
#
# So the objective changed. It is not phonetic accuracy — it is "recognisably the right
# name, carried on natural English prosody", and espeak already supplies the prosody.
# Override ONLY where espeak breaks the name's identity: a changed consonant, an inserted
# glide, or a split syllable. Leave every vowel approximation alone. "Baek" -> "beek" is
# wrong and stays, because fixing it costs prosody and buys nothing an audience notices.
MIN_LEX: dict[str, str] = {
    "Jung":     "ʤˈʊŋ",      # espeak jˈʊŋ         J -> Y
    "Chi-Yul":  "ʧˈijʌl",    # espeak kˈIjˈʌl      Ch -> K
    "Myung":    "mjˈʌŋ",     # espeak mˈIʌŋ        split into two syllables
    "Si-eun":   "sˈiʌn",     # espeak sˈijˈun      inserted Y glide
    "Jae-hwan": "ʤˈɛhwɑn",   # espeak jˈiˈAʧwˈæn   destroyed
    "Murim":    "mˈuɹɪm",    # espeak mjˈʊɹɹɪm     inserted j glide
    "Mu":       "mˈu",       # espeak mjˌu         inserted j glide
    "Deok-Gu":  "dˈʌkɡu",    # espeak diˈɑkɡˈu     split into three syllables
}

# Only two of the eight apply to this repo's rosters — Deok-Gu (Frozen Player) and
# Chi-Yul (Solo Leveling). The rest are carried verbatim from the correction so the set
# stays one auditable list; they simply never fire on these projects.
#
# Both are WHOLE-NAME keys, not per-syllable. Correction §5: a per-syllable key does not
# fire inside a hyphenated token, because misaki looks up the whole hyphenated string.
# `verify_hyphen_lookup` below re-checks that on this machine rather than trusting it.

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


def envelope(path: Path) -> dict[str, float]:
    """10 ms RMS envelope stats — the measurement that diagnosed the rejected lexicon.

    Correction §6.4: articulation rate must stay near the espeak baseline of ~5.3/s. A
    rise toward 6.7/s means over-articulation has returned and an entry carries too much
    stress. Peaks are syllable-energy maxima; pauses are gaps at least 60 ms long.
    """
    import numpy as np
    import soundfile as sf

    samples, sr = sf.read(str(path), dtype="float64", always_2d=False)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    hop = max(int(0.010 * sr), 1)
    frames = len(samples) // hop
    rms = np.array([
        float(np.sqrt(np.mean(samples[i * hop : (i + 1) * hop] ** 2))) for i in range(frames)
    ])
    duration = len(samples) / sr
    if not frames:
        return {"duration_s": duration}

    # Peaks: local maxima above a fraction of the median voiced level, 60 ms apart minimum.
    voiced = rms[rms > rms.max() * 0.05]
    floor = float(np.median(voiced)) * 0.55 if voiced.size else 0.0
    peaks, last = 0, -99
    for i in range(1, frames - 1):
        if rms[i] > floor and rms[i] >= rms[i - 1] and rms[i] > rms[i + 1] and i - last >= 6:
            peaks += 1
            last = i
    silent = rms < (rms.max() * 0.04)
    pauses, run = 0, 0
    for quiet in silent:
        run = run + 1 if quiet else 0
        if run == 6:  # 60 ms
            pauses += 1
    return {
        "duration_s": round(duration, 2),
        "syllable_peaks": peaks,
        "articulation_rate_per_s": round(peaks / max(duration, 1e-6), 2),
        "pauses_over_60ms": pauses,
    }


def verify_hyphen_lookup(pipeline) -> None:
    """Correction §5 says a per-syllable key does not fire inside a hyphenated token.

    That is a falsifiable claim about misaki's lookup, and it decides whether every entry
    needs a whole-name key. Check it here rather than trusting it.
    """
    probe = {"Chi": "ʧˈi", "Deok": "dˈʌk"}
    saved = {k: pipeline.g2p.lexicon.golds.get(k) for k in probe}
    for k, v in probe.items():
        pipeline.g2p.lexicon.golds[k] = v
    fired = {name: pipeline.g2p(name)[0] for name in ("Chi-Yul", "Deok-Gu", "Chi", "Deok")}
    for k, v in saved.items():
        if v is None:
            pipeline.g2p.lexicon.golds.pop(k, None)
        else:
            pipeline.g2p.lexicon.golds[k] = v
    hyphen_ignored = "ʧˈi" not in fired["Chi-Yul"] and "dˈʌk" not in fired["Deok-Gu"]
    print(f"\n§5 hyphen lookup: per-syllable key {'IGNORED' if hyphen_ignored else 'FIRED'} "
          f"inside a hyphenated token -> whole-name keys "
          f"{'required' if hyphen_ignored else 'NOT required'}")
    for name, ph in fired.items():
        print(f"    {name:10} -> {ph!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("_review"))
    ap.add_argument("--voice", default=None, help="default: config's tts.kokoro_voice")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--sentence", default=SENTENCE)
    args = ap.parse_args()

    problems = validate(MIN_LEX)
    if problems:
        print("LEXICON INVALID — refusing to inject:")
        for p in problems:
            print("  " + p)
        return 1
    print(f"lexicon: {len(MIN_LEX)} entries, all phonemes legal")

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    from manhwa2vid.config import get_nested, load_config

    voice = args.voice or str(get_nested(load_config(), "tts", "kokoro_voice", default="am_adam"))
    args.out.mkdir(parents=True, exist_ok=True)
    pipeline = KPipeline(lang_code="a")
    print(f"voice={voice} speed={args.speed} espeak_fallback={pipeline.g2p.fallback is not None}")

    stats: dict[str, dict[str, float]] = {}

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
        stats[tag] = envelope(path)

    verify_hyphen_lookup(pipeline)

    render("before")
    for word, phonemes in MIN_LEX.items():
        for variant in {word, word.lower(), word.upper(), word.capitalize()}:
            pipeline.g2p.lexicon.golds[variant] = phonemes
    render("after")

    # Correction §6.4: the envelope is how over-articulation is detected. The rejected
    # lexicon produced 46 peaks at 6.7/s against espeak's 38 at 5.3/s, in a SHORTER take.
    print("\nenvelope (correction §6.4 — articulation must stay near the ~5.3/s baseline)")
    keys = ["duration_s", "syllable_peaks", "articulation_rate_per_s", "pauses_over_60ms"]
    print(f"  {'metric':26}{'before':>10}{'after':>10}")
    for k in keys:
        print(f"  {k:26}{stats['before'].get(k, 0):>10}{stats['after'].get(k, 0):>10}")
    # Compare against the BEFORE baseline measured by this same detector, never against
    # the correction's absolute 5.3/6.7 — those came from a different peak-picker, and
    # comparing numbers across detectors is the error this project has already paid for
    # twice. This detector reads the same espeak baseline at ~7.5/s, so only the ratio
    # is meaningful.
    before_rate = stats["before"].get("articulation_rate_per_s", 0.0)
    after_rate = stats["after"].get("articulation_rate_per_s", 0.0)
    if before_rate:
        delta = 100.0 * (after_rate - before_rate) / before_rate
        print(f"\n  articulation {delta:+.1f}% vs the espeak baseline "
              f"({before_rate}/s -> {after_rate}/s, this detector)")
        if delta > 8.0:
            print("  WARNING: over-articulation has returned — an entry carries too much "
                  "stress. The rejected lexicon ran +26% on the correction's detector.")
        else:
            print("  OK: no over-articulation (the rejected lexicon ran +26%).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
