"""Rebuild the shot list, plan, timeline and gates from cached model output — no spend.

Everything after the matcher collects its claims is deterministic: `filter_monotonic`,
callbacks, the coda, the planner, the timeline, every gate. So a change to any of it can
be verified exactly, for nothing, against a project that has already been paid for.

That was not true before, and it cost dearly: four consecutive fixes to the time-block
machinery were each "validated" by a paid re-run of a pipeline whose matcher alone is
3.3M prompt tokens, and three of the four turned out wrong or incomplete. The runs were
slow and expensive enough that each one only surfaced the next defect.

    python tools/replay.py projects/<name>            # rebuild + report
    python tools/replay.py projects/<name> --verify   # must reproduce the shipped artifact

`--verify` is what makes the harness trustworthy: with a warm cache it must reproduce the
existing shot list exactly. If it cannot, the cache or the seeding is wrong and no
conclusion drawn from a replay means anything.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

os.environ["MANHWA2VID_MATCH_OFFLINE"] = "1"     # before any provider is constructed

from manhwa2vid.config import load_config                        # noqa: E402
from manhwa2vid.measure.binding import coverage_gaps             # noqa: E402
from manhwa2vid.models import project_paths                      # noqa: E402
from manhwa2vid.script import match as M                         # noqa: E402


def _script_text(paths: dict[str, Path]) -> str:
    """The prose the pipeline actually aligns.

    `story_first` writes the post-pass text to script.freeform.md and hands THAT to
    align_script. script.final.md carries "### Beat N" headers, which split into extra
    paragraphs and produce a completely different alignment — 202 paragraphs instead of
    99 on the 20-chapter project, and a 0% cache hit rate.
    """
    p = paths.get("script_freeform")
    if p and p.exists():
        return p.read_text(encoding="utf-8")
    raise SystemExit("no script.freeform.md — nothing to replay")


def report(project: Path, verify: bool) -> int:
    paths = project_paths(project)
    config = load_config()
    before = None
    if paths["script_shotlist_json"].exists():
        before = json.loads(paths["script_shotlist_json"].read_text(encoding="utf-8"))

    M.reset_claim_cache()
    from manhwa2vid.script.align import align_script

    text = _script_text(paths)
    beats, qa = align_script(text, paths, config)

    hits, misses = M.cache_stats()
    print(f"\ncache: {hits} hit(s), {misses} miss(es)"
          + ("  <-- inputs changed; those windows returned nothing" if misses else ""))

    after = json.loads(paths["script_shotlist_json"].read_text(encoding="utf-8"))
    rows = [s for s in after["sentences"] if not s.get("outro")]
    matched = sum(1 for s in rows if s.get("panels"))
    print(f"match rate: {matched}/{len(rows)} = {100 * matched / max(1, len(rows)):.0f}%")
    print(f"blocks: {len(after.get('time_blocks', {}).get('boundaries') or []) + 1}"
          f"  boundaries: {len(after.get('time_blocks', {}).get('boundaries') or [])}")

    order = [p["id"] for p in json.loads(paths["panels_story_json"].read_text())]
    idx = {p: i for i, p in enumerate(order)}
    shown = [{"panel_id": pid}
             for s in after["sentences"] for pid in (s.get("panels") or [])]
    g = coverage_gaps(order, shown)
    print(f"claimed-panel gaps: longest {g['longest_gap']}, median {g['median_gap']}")

    # The defect that four paid runs chased: narration bound to art it never described.
    amap = {}
    ap = paths["script_alignment_json"]
    if ap.exists():
        for e in json.loads(ap.read_text()).get("map") or []:
            amap[e["paragraph"]] = (int(e["first_page"]), int(e["last_page"]))
    by_beat: dict[int, list[int]] = {}
    for s in after["sentences"]:
        for pid in s.get("panels") or []:
            by_beat.setdefault(s["beat_id"], []).append(idx.get(pid, -1))
    def pos(pg: int):
        return next((i for i, p in enumerate(order) if int(p[1:5]) == pg), None)
    outside = 0
    checked = 0
    for beat, ps in by_beat.items():
        if beat not in amap:
            continue
        lo, hi = pos(amap[beat][0]), pos(amap[beat][1])
        if lo is None or hi is None:
            continue
        checked += 1
        if any(not (lo - 20 <= x <= hi + 20) for x in ps):
            outside += 1
    print(f"beats showing art outside their aligned range: {outside}/{checked}")

    failed = [c.name for c in qa.gates if c.status is False]
    warned = [c.name for c in qa.gates if c.status == "warn"]
    print(f"script gates: {len(qa.gates)} checked, {len(failed)} failed, {len(warned)} warned")
    for name in failed:
        print(f"   FAIL {name}")

    if verify:
        if before is None:
            print("\n--verify: no previous shot list to compare against")
            return 1
        same = (
            [(s["number"], tuple(s.get("panels") or [])) for s in before["sentences"]]
            == [(s["number"], tuple(s.get("panels") or [])) for s in after["sentences"]]
        )
        print(f"\n--verify: shot list {'REPRODUCED exactly' if same else 'DIFFERS'}")
        if not same:
            b = {s["number"]: tuple(s.get("panels") or []) for s in before["sentences"]}
            a = {s["number"]: tuple(s.get("panels") or []) for s in after["sentences"]}
            diff = [n for n in sorted(set(b) | set(a)) if b.get(n) != a.get(n)]
            print(f"   {len(diff)} sentence(s) differ; first few: {diff[:10]}")
            return 1
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    return report(Path(args[0]), "--verify" in sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
