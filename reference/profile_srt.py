"""Style profile v2: sentence structure, dialogue-verb cadence, chapter density."""

from __future__ import annotations

import re
import statistics as stats
import sys
from collections import Counter
from pathlib import Path

TIME_RE = re.compile(r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)")


def parse(path: Path):
    cues = []
    start = end = None
    buf = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = TIME_RE.match(line.strip())
        if m:
            if start is not None and buf:
                cues.append((start, end, " ".join(buf)))
            g = [int(x) for x in m.groups()]
            start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
            end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
            buf = []
        elif line.strip().isdigit() or not line.strip():
            continue
        else:
            buf.append(line.strip())
    if start is not None and buf:
        cues.append((start, end, " ".join(buf)))
    return cues


def main(path: Path) -> None:
    cues = parse(path)
    duration = cues[-1][1]
    text = " ".join(c[2] for c in cues)
    text = re.sub(r"\s+", " ", text)
    words = text.split()
    n = len(words)

    # timestamp of each word (linear within its cue) for windowed stats
    stamped = []
    for s, _e, t in cues:
        for w in t.split():
            stamped.append((s, w))

    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    slens = [len(s.split()) for s in sents]
    print(f"duration={duration/3600:.2f}h words={n} WPM={n/(duration/60):.1f}")
    print(f"sentences={len(sents)}  words/sentence: mean={stats.mean(slens):.1f} "
          f"median={stats.median(slens)} p10={sorted(slens)[len(slens)//10]} "
          f"p90={sorted(slens)[int(len(slens)*0.9)]}")
    print(f"sentences/minute = {len(sents)/(duration/60):.1f}  "
          f"-> avg sentence airtime = {duration/len(sents):.1f}s")

    low = text.lower()

    def count(*terms):
        return sum(len(re.findall(rf"\b{re.escape(t)}\b", low)) for t in terms)

    def rate(*terms):
        c = count(*terms)
        return c, c / n * 1000

    print("\nper-1000-word rates:")
    for label, terms in {
        "dialogue verbs (says/asks/tells)": ("says", "asks", "tells", "replies", "answers", "explains", "admits"),
        "interiority (thinks/realizes)": ("thinks", "realizes", "wonders", "notices", "remembers"),
        "1st person narrator": ("i", "i'm", "me", "my"),
        "2nd person (you)": ("you", "your", "you're"),
        "slang (multiword-safe)": ("ngl", "lowkey", "highkey", "bruh", "bro", "sus", "vibe"),
        "'no cap' phrase": ("no cap",),
        "hype adjectives": ("insane", "crazy", "wild", "brutal", "savage", "absolutely", "literally"),
        "hedging": ("maybe", "probably", "possibly", "seems", "appears", "might"),
        "the protagonist label": ("the protagonist",),
        "MC label": ("mc",),
    }.items():
        c, r = rate(*terms)
        print(f"  {label:34s} count={c:6d} rate={r:6.2f}")

    # tense proxy: present-tense 3rd person verbs vs past
    past = len(re.findall(r"\b\w+ed\b", low))
    print(f"\npast-tense '-ed' tokens: {past} ({past/n*1000:.1f}/1k) — low value = present-tense narration")

    # chapter density
    ch_hits = [(t, m) for (t, w) in stamped for m in [w] if False]
    ch_mentions = len(re.findall(r"\bchapter\b", low))
    print(f"'chapter' mentions: {ch_mentions}")

    # paragraph/beat proxy: gaps between cues > 0.4s
    gaps = []
    for i in range(1, len(cues)):
        g = cues[i][0] - cues[i - 1][1]
        gaps.append(g)
    big = [g for g in gaps if g > 0.3]
    print(f"cue gaps > 0.3s: {len(big)} (avg every {duration/max(len(big),1):.1f}s)")

    # windowed WPM stability (are there silent/music stretches?)
    win = 300
    buckets = Counter()
    for t, _w in stamped:
        buckets[int(t // win)] += 1
    vals = [v / (win / 60) for k, v in sorted(buckets.items())]
    print(f"5-min-window WPM: min={min(vals):.0f} p10={sorted(vals)[len(vals)//10]:.0f} "
          f"median={stats.median(vals):.0f} max={max(vals):.0f}")

    # opening hook shape
    hook_words = [w for t, w in stamped if t <= 20]
    hook_text = " ".join(hook_words)
    hook_sents = [s for s in re.split(r"(?<=[.!?])\s+", hook_text) if s.strip()]
    print(f"\nfirst 20s: {len(hook_words)} words in ~{len(hook_sents)} sentences")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
