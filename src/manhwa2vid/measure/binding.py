"""How well the narration is bound to the artwork.

These read the PLANNED artifacts — shot list, timeline, TTS sidecars — not the video, so
they can gate the timeline stage before a render is paid for.

`hold_runs` and every rhythm question about the timeline go through
`shots.merged_runs`: consecutive entries on one panel are one shot to the viewer whatever
the plan says, and reading entries instead of runs is how a 18.6s hold reported itself as
two shots of 7.4s and 11.2s.
"""

from __future__ import annotations

from typing import Any

from manhwa2vid.measure.shots import merged_runs


def match_rate(shotlist: dict[str, Any]) -> dict[str, Any]:
    """Share of narration sentences the matcher bound to at least one panel of its own.

    An unbound sentence is not silent — bounded fill walks it through unclaimed panels,
    or it holds the current shot. So this measures how often the picture is CHOSEN for
    the line rather than inherited, which is the difference between a recap and a
    slideshow with a voice over it.

    Outro sentences are excluded from the denominator: the outro is the narrator
    addressing the VIEWER and is deliberately not panel-grounded (script/outro.py), so
    counting its guaranteed misses would penalise the matcher for a design decision.
    """
    sentences = shotlist.get("sentences") or []
    scored = [s for s in sentences if not s.get("outro")]
    if not scored:
        return {"sentences": 0, "matched": 0, "outro_excluded": len(sentences),
                "match_rate_pct": 0.0}
    matched = sum(1 for s in scored if s.get("panels"))
    return {
        "sentences": len(scored),
        "matched": matched,
        "outro_excluded": len(sentences) - len(scored),
        "match_rate_pct": round(100.0 * matched / len(scored), 1),
    }


def coverage_gaps(story_panel_ids: list[str], entries: list[Any]) -> dict[str, Any]:
    """Runs of consecutive story panels the video never shows — the DISCONNECT measure.

    `panel_utilisation` answers "what share of the art reached the screen", which is the
    wrong question for a long recap: at 20 chapters a 550-word-per-chapter budget yields
    ~640 shots for ~1640 panels, so 39% is arithmetic, not a defect. What a viewer
    actually notices is a HOLE — the narration jumping over a stretch of the story.

    Measured on the first 20-chapter probe: median gap 2 panels (healthy sampling) but a
    single run of 165 consecutive panels — 27 pages — that no paragraph covered at all,
    because the writer skipped the sequence. The two shipped short videos have longest
    gaps of 8 and 10 panels. So the distribution, not the total, is the signal.
    """
    def get(e: Any, key: str) -> Any:
        return e.get(key) if isinstance(e, dict) else getattr(e, key)

    shown = {get(e, "panel_id") for e in entries}
    gaps: list[dict[str, Any]] = []
    run = 0
    for i, pid in enumerate(story_panel_ids):
        if pid in shown:
            if run:
                gaps.append({"panels": run, "from": story_panel_ids[i - run],
                             "to": story_panel_ids[i - 1]})
            run = 0
        else:
            run += 1
    if run:
        gaps.append({"panels": run, "from": story_panel_ids[-run],
                     "to": story_panel_ids[-1]})
    ordered = sorted(gaps, key=lambda g: -g["panels"])
    lengths = [g["panels"] for g in gaps]
    lengths.sort()
    median = lengths[len(lengths) // 2] if lengths else 0
    return {
        "gaps": len(gaps),
        "longest_gap": ordered[0]["panels"] if ordered else 0,
        "median_gap": median,
        "worst": ordered[:5],
    }


def panel_utilisation(story_panel_ids: list[str], entries: list[Any]) -> dict[str, Any]:
    """Share of story panels that actually reach the screen.

    Panels excluded upstream (blank slivers, lettering-only) are not in
    `story_panel_ids`, so this measures art the reader would have seen in the chapter and
    the viewer never does.
    """
    def get(e: Any, key: str) -> Any:
        return e.get(key) if isinstance(e, dict) else getattr(e, key)

    shown = {get(e, "panel_id") for e in entries}
    total = len(story_panel_ids)
    used = sum(1 for pid in story_panel_ids if pid in shown)
    return {
        "story_panels": total,
        "shown": used,
        "utilisation_pct": round(100.0 * used / total, 1) if total else 0.0,
        "unused": sorted(set(story_panel_ids) - shown),
    }


def hold_runs(entries: list[Any], *, max_sentences: int = 3) -> dict[str, Any]:
    """Longest stretch of consecutive narration held on one panel, in SENTENCES.

    Needs `TimelineEntry.sentence_numbers`. Without it the honest answer is "entries per
    run", which UNDERSTATES the hold — one entry can carry several sentences — so the
    result says which basis it used rather than quietly reporting a smaller number as if
    it were sentences. A gate must not read `longest_hold` when `basis` is "entries".
    """
    runs = merged_runs(entries)
    have_numbers = any(
        (e.get("sentence_numbers") if isinstance(e, dict)
         else getattr(e, "sentence_numbers", None))
        for e in entries
    )
    worst: list[dict[str, Any]] = []
    longest = 0
    for run in runs:
        members = entries[run["index"] : run["index"] + run["entries"]]
        counted = 0
        for e in members:
            nums = (e.get("sentence_numbers") if isinstance(e, dict)
                    else getattr(e, "sentence_numbers", None)) or []
            counted += len(nums) or 1
        longest = max(longest, counted)
        if have_numbers and counted > max_sentences:
            worst.append(
                {"panel_id": run["panel_id"], "sentences": counted,
                 "seconds": round(run["seconds"], 2)}
            )
    return {
        "basis": "sentences" if have_numbers else "entries",
        "longest_hold": longest,
        "over_limit": worst,
        "runs": len(runs),
        "planned_entries": len(entries),
        "invisible_cuts": len(entries) - len(runs),
        "longest_run_seconds": round(max((r["seconds"] for r in runs), default=0.0), 2),
    }


def timing_measured(
    shotlist: dict[str, Any], segments_by_beat: dict[int, list[dict[str, Any]]]
) -> dict[str, Any]:
    """Share of narration sentences whose duration came from a MEASURED sidecar entry.

    Kokoro synthesizes one clip per sentence, so its sidecar seconds are measured. Other
    providers return one opaque clip per beat and `timeline._subdivide_segments`
    word-prorates it — a plausible-looking estimate that silently decouples the cut from
    the speech. This gate exists to catch a regression back to that path, so it checks
    IDENTITY (sentence counts line up per beat), not merely that a sidecar exists.
    """
    sentences = shotlist.get("sentences") or []
    by_beat: dict[int, int] = {}
    for s in sentences:
        by_beat[int(s["beat_id"])] = by_beat.get(int(s["beat_id"]), 0) + 1
    total = len(sentences)
    aligned = 0
    mismatched: list[int] = []
    for beat_id, want in by_beat.items():
        got = len(segments_by_beat.get(beat_id) or [])
        if got == want:
            aligned += want
        else:
            mismatched.append(beat_id)
    return {
        "sentences": total,
        "measured": aligned,
        "measured_pct": round(100.0 * aligned / total, 1) if total else 0.0,
        "mismatched_beats": sorted(mismatched),
    }
