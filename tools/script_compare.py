"""Side-by-side comparison of a generated script against the hand-written gold standard.

The lesson that forced this tool: every recent "fix" improved a measured gate (alignment
majors, panel binding, pronoun ratio) while the video got WORSE — the user's verdict was
"a stringed narration of image descriptions". Nothing measured storytelling. This harness
makes the gap visible two ways: the full text side by side for human reading, and style
metrics computed identically on both scripts so the target is a number the gold already
achieves, not a number that merely improved.

    python tools/script_compare.py --project projects/solo-leveling-ch1
    python tools/script_compare.py --project projects/solo-leveling-ch1 --gold reference/ch1_gold_script.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

# --- captioning markers: the report-register constructions the user called out ----------
# "a plate of food sits on the counter", "with a startled expression", "is visible",
# "in the foreground". Each of these describes an IMAGE; none of them advances a story.
CAPTION_PATTERNS = [
    r"\bis visible\b", r"\bare visible\b", r"\bcan be seen\b",
    r"\bin the (?:foreground|background)\b",
    r"\bwith an? \w+ expression\b",
    r"\bsits? on the\b", r"\bstands? (?:nearby|in the)\b",
    r"\bwearing an? \b",
    r"\bthe (?:scene|image|view|shot|close-up)\b",
    r"\b(?:left|right) side of\b",
    r"\bnext to (?:him|her|them) (?:is|are|sits|stands)\b",
    r"\bappears? to\b", r"\bis shown\b",
]
CAPTION_RE = re.compile("|".join(CAPTION_PATTERNS), re.I)

# The reference channel's signature: reported speech carries the story.
SPEECH_VERBS_RE = re.compile(
    r"\b(?:says|asks|tells|replies|answers|admits|snaps|mutters|shouts|yells|calls|"
    r"warns|adds|explains|wonders|thinks|realizes|notices|remembers|swears|promises|"
    r"jokes|laughs about|brands|declares|insists|begs)\b",
    re.I,
)

# Storytelling glue: causality and stance, which captions lack.
CONNECTIVES_RE = re.compile(
    r"\b(?:but|because|so|then|still|even|instead|already|finally|until|while|"
    r"before|after|once|never|only|again)\b",
    re.I,
)

PRONOUN_START_RE = re.compile(r"^(?:He|She|They|His|Her|Their)\b")


def beats_from_markdown(path: Path) -> list[tuple[str, str]]:
    """[(panel_comment, narration), ...] from a script.draft-style markdown file."""
    text = path.read_text(encoding="utf-8")
    beats: list[tuple[str, str]] = []
    for block in re.split(r"^## Beat \d+\s*$", text, flags=re.M)[1:]:
        panels = ""
        m = re.search(r"<!--\s*panels:\s*(.*?)\s*-->", block)
        if m:
            panels = m.group(1)
        narration = re.sub(r"<!--.*?-->", "", block, flags=re.S).strip()
        narration = narration.split("\n---")[0].strip()
        if narration:
            beats.append((panels, narration))
    return beats


def beats_from_script_json(path: Path) -> list[tuple[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [(", ".join(b.get("panel_ids", [])), b.get("narration", "")) for b in data.get("beats", [])]


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def metrics(beats: list[tuple[str, str]]) -> dict[str, float]:
    full = " ".join(n for _p, n in beats)
    words = max(1, len(full.split()))
    sents = [s for _p, n in beats for s in sentences(n)]

    max_run = 0
    for _p, n in beats:
        run = 0
        for s in sentences(n):
            run = run + 1 if PRONOUN_START_RE.match(s) else 0
            max_run = max(max_run, run)

    return {
        "beats": len(beats),
        "words": words,
        "avg_sentence_words": round(sum(len(s.split()) for s in sents) / max(1, len(sents)), 1),
        "caption_markers_per_100w": round(100 * len(CAPTION_RE.findall(full)) / words, 2),
        "speech_verbs_per_100w": round(100 * len(SPEECH_VERBS_RE.findall(full)) / words, 2),
        "connectives_per_100w": round(100 * len(CONNECTIVES_RE.findall(full)) / words, 2),
        "max_consecutive_pronoun_starts": max_run,
        "pronoun_start_fraction": round(
            sum(1 for s in sents if PRONOUN_START_RE.match(s)) / max(1, len(sents)), 2
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="projects/solo-leveling-ch1")
    ap.add_argument("--gold", default="reference/ch1_gold_script.md")
    ap.add_argument("--out", default="reference/script_compare_ch1.md")
    args = ap.parse_args()

    gold = beats_from_markdown(REPO / args.gold)
    cand_path = REPO / args.project / "script.json"
    cand = beats_from_script_json(cand_path)

    gm, cm = metrics(gold), metrics(cand)

    lines = [
        "# Script comparison — gold (hand-written) vs generated",
        "",
        f"Gold: `{args.gold}` · Candidate: `{cand_path.relative_to(REPO)}`",
        "",
        "## Metrics (the target is the GOLD column, not 'better than last run')",
        "",
        "| metric | gold | candidate |",
        "|---|---|---|",
    ]
    for key in gm:
        flag = ""
        if key == "caption_markers_per_100w" and cm[key] > gm[key] * 2 + 0.5:
            flag = " ⚠"
        if key == "speech_verbs_per_100w" and cm[key] < gm[key] * 0.6:
            flag = " ⚠"
        if key == "max_consecutive_pronoun_starts" and cm[key] > max(2, gm[key]):
            flag = " ⚠"
        lines.append(f"| {key} | {gm[key]} | {cm[key]}{flag} |")

    lines += ["", "## Side by side", ""]
    n = max(len(gold), len(cand))
    for i in range(n):
        gp, gn = gold[i] if i < len(gold) else ("", "(no gold beat)")
        cp, cn = cand[i] if i < len(cand) else ("", "(no candidate beat)")
        lines += [
            f"### Beat {i + 1}",
            "",
            f"**GOLD** ({gp}):",
            f"> {gn}",
            "",
            f"**GEN** ({cp}):",
            f"> {cn}",
            "",
        ]

    out = REPO / args.out
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out.relative_to(REPO)}")
    print("\nMETRICS  (gold | candidate)")
    for key in gm:
        print(f"  {key:34s} {gm[key]!s:>8} | {cm[key]}")


if __name__ == "__main__":
    main()
