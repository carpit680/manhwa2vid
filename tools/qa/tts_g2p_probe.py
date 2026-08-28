#!/usr/bin/env python3
"""What does the G2P do to THIS repo's real character names? (spec §0.3 Script 2)

Reads the roster from every project's glossary.json rather than a hardcoded list, because
the spec's own list was reconstructed from audit reports and rendered frames.

Prints three columns per name:
  deleted  — what Path A would produce (fallback off): '' means the name vanishes
  espeak   — what Path B produces (fallback on): what this machine actually says
  in-lex   — whether Kokoro's own 178k-entry lexicon knows the word at all
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

FALLBACK_NAMES = ["Jinwoo", "Sung Jin-Woo", "Cha Hae-In", "Baek", "Gong Chi-Yul",
                  "Deok-Gu", "Carthenon", "Jun-Ho", "Murim"]


def roster(projects: Path) -> list[str]:
    names: list[str] = []
    for glossary in sorted(projects.glob("*/glossary.json")):
        try:
            data = json.loads(glossary.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for section in ("characters", "terms"):
            for name, aliases in (data.get(section) or {}).items():
                names.append(name)
                names.extend(a for a in (aliases or []) if isinstance(a, str))
    seen, out = set(), []
    for n in names:
        # Single lowercase words are ordinary English; the risk is proper nouns.
        if n and n not in seen and any(c.isupper() for c in n):
            seen.add(n)
            out.append(n)
    return out or FALLBACK_NAMES


def main() -> int:
    projects = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("projects")
    names = roster(projects)

    from misaki import en

    try:
        from misaki import espeak

        fb = espeak.EspeakFallback(british=False)
    except Exception:
        fb = None

    deleted = en.G2P(trf=False, british=False, fallback=None, unk="")
    marked = en.G2P(trf=False, british=False, fallback=None, unk="?UNK?")
    spoken = en.G2P(trf=False, british=False, fallback=fb, unk="") if fb else None

    print(f"{len(names)} proper nouns from {projects}/*/glossary.json\n")
    print(f"  {'name':22}{'deleted (path A)':26}{'espeak (path B)':30}{'in-lex'}")
    unresolved = 0
    for name in names:
        a = deleted(name)[0]
        unknown = "?UNK?" in marked(name)[0]
        e = spoken(name)[0] if spoken else "<no fallback>"
        unresolved += unknown
        print(f"  {name:22}{a!r:26}{e!r:30}{'' if unknown else 'yes'}")
    print(f"\n  {unresolved}/{len(names)} are NOT in Kokoro's lexicon and depend on espeak")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
