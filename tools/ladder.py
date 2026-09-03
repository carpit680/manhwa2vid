"""One table of every project's binding metrics — "did this get better or worse?"

Short projects were the only ones ever measured, and the machinery that breaks at length
barely engages below 20 chapters: the shipped short videos have 1-3 time blocks, the
20-chapter probe has 8. Comparing across the whole ladder is what turned four separate
"mysteries" into one number (sentences per story panel: 0.72-0.87 on every approved
video, 0.38 on the probe).

    python tools/ladder.py                 # every project with a shot list
    python tools/ladder.py projects/foo    # just one

Reads artifacts only. No model calls, no render.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from manhwa2vid.measure.binding import coverage_gaps       # noqa: E402


def metrics(project: Path) -> dict | None:
    try:
        order = [p["id"] for p in json.loads((project / "panels.story.json").read_text())]
        sl = json.loads((project / "script.shotlist.json").read_text())
    except (OSError, ValueError):
        return None
    idx = {p: i for i, p in enumerate(order)}
    sents = sl["sentences"]
    rows = [s for s in sents if not s.get("outro")]
    matched = sum(1 for s in rows if s.get("panels"))

    md = project / "script.final.md"
    if not md.exists():
        md = project / "script.draft.md"
    words = 0
    if md.exists():
        text = re.sub(r"<!--.*?-->", "", md.read_text(encoding="utf-8"), flags=re.S)
        words = len(re.sub(r"^#.*$", "", text, flags=re.M).split())

    claimed = [{"panel_id": pid} for s in sents for pid in (s.get("panels") or [])]
    gaps = coverage_gaps(order, claimed)

    tl = project / "timeline.json"
    shown_gaps = None
    duration = None
    if tl.exists():
        t = json.loads(tl.read_text())
        shown_gaps = coverage_gaps(order, t["entries"])
        duration = t.get("total_duration")

    # Narration bound to art it never described — the defect four paid runs chased.
    outside = checked = 0
    ap = project / "script.alignment.json"
    if ap.exists():
        amap = {int(e["paragraph"]): (int(e["first_page"]), int(e["last_page"]))
                for e in json.loads(ap.read_text()).get("map") or []}
        by_beat: dict[int, list[int]] = {}
        for s in sents:
            for pid in s.get("panels") or []:
                by_beat.setdefault(s["beat_id"], []).append(idx.get(pid, -1))
        pos = {}
        for i, pid in enumerate(order):
            pos.setdefault(int(pid[1:5]), i)
        for beat, ps in by_beat.items():
            if beat not in amap:
                continue
            lo, hi = pos.get(amap[beat][0]), pos.get(amap[beat][1])
            if lo is None or hi is None:
                continue
            checked += 1
            if any(not (lo - 20 <= x <= hi + 20) for x in ps):
                outside += 1

    return {
        "name": project.name,
        "panels": len(order),
        "sents": len(sents),
        "words": words,
        "per_panel": len(sents) / max(1, len(order)),
        "match": 100 * matched / max(1, len(rows)),
        "blocks": len((sl.get("time_blocks") or {}).get("boundaries") or []) + 1,
        "gap": gaps["longest_gap"],
        "shown_gap": shown_gaps["longest_gap"] if shown_gaps else None,
        "outside": f"{outside}/{checked}" if checked else "-",
        "minutes": duration / 60 if duration else None,
    }


def main() -> int:
    args = sys.argv[1:]
    projects = [Path(a) for a in args] if args else sorted(Path("projects").glob("*"))
    rows = [m for m in (metrics(p) for p in projects if p.is_dir()) if m]
    if not rows:
        print("no project with a shot list")
        return 1
    rows.sort(key=lambda r: r["panels"])
    head = (f"{'project':34}{'panels':>7}{'sents':>7}{'words':>7}{'/panel':>8}"
            f"{'match':>7}{'blk':>5}{'gap':>6}{'shown':>7}{'outside':>9}{'min':>6}")
    print(head)
    print("-" * len(head))
    for r in rows:
        print(f"{r['name'][:33]:34}{r['panels']:7d}{r['sents']:7d}{r['words']:7d}"
              f"{r['per_panel']:8.2f}{r['match']:6.0f}%{r['blocks']:5d}{r['gap']:6d}"
              f"{(r['shown_gap'] if r['shown_gap'] is not None else -1):7d}"
              f"{r['outside']:>9}"
              f"{(round(r['minutes']) if r['minutes'] else 0):6d}")
    print("\n/panel is sentences per story panel. Every APPROVED video measures 0.72-0.87;")
    print("the first 20-chapter probe measured 0.38 and produced 39% utilisation,")
    print("a 165-panel coverage hole, and paragraphs stretched over 25 pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
