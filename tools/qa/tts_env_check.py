#!/usr/bin/env python3
"""Which pronunciation failure mode is this machine on? (audio-quality-spec §0.3 Script 1)

Kokoro builds an espeak fallback for words its lexicon does not know, and only lands on
`fallback=None` if espeak-ng is missing. The two modes fail very differently:

  PATH A — no espeak: an unresolved token contributes an EMPTY string, so the name is
           silently DELETED from the audio.
  PATH B — espeak present: the name survives but is pronounced by English letter rules,
           which is worse in one way — fluent, confident and unstable across spellings,
           so one character can acquire several names across a video.

`pyproject.toml` pins only `kokoro>=0.9`, so record what actually resolved here.
"""

from __future__ import annotations

import importlib.metadata as md
import shutil
import warnings

warnings.filterwarnings("ignore")

PACKAGES = ["kokoro", "misaki", "torch", "spacy", "phonemizer-fork",
            "espeakng-loader", "en_core_web_sm", "soundfile"]


def main() -> int:
    print("environment")
    for pkg in PACKAGES:
        try:
            print(f"  {pkg}=={md.version(pkg)}")
        except Exception:
            print(f"  {pkg}: NOT INSTALLED")
    print(f"  espeak-ng binary on PATH: {shutil.which('espeak-ng') or 'NO'}")

    try:
        from misaki import espeak

        espeak.EspeakFallback(british=False)
        print("\nPATH B — espeak fallback AVAILABLE: names are MISPRONOUNCED")
        print("  (espeakng-loader can supply a bundled binary even with none on PATH)")
        return 0
    except Exception as exc:  # noqa: BLE001 — any failure means no fallback
        print(f"\nPATH A — espeak fallback UNAVAILABLE: names are DELETED\n  {exc!r}"[:400])
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
