"""Reference-paced panel curation: choose which story panels the SCRIPT narrates.

The reference channel this pipeline imitates shows roughly HALF of a dense chapter's
panels and speaks ~10 words over each one it shows (measured on the same chapters:
979 words over ~100 shown panels in 251s). Binding every story panel into the script —
the invariant this module relaxes — contradicted that format arithmetically: 199 panels
at minimum dwell is 8+ minutes of video for a 4-minute chapter span, and 28 beats over
199 panels forces each beat to compress ~7 panels into ~32 words, which is a physically
impossible beat, not a writer failure. Solo Leveling ch1 worked all along only because
it is sparse (54 panels — under the budget, so curation there selects everything).

The density constant is DERIVED, not tuned:

    words_per_shown_panel = script.target_wpm x video.target_panel_seconds / 60  (~9.9)

Both inputs already exist in config and both were measured from the reference profile
(237 WPM; sentence cadence 18.6/min ~ 3.2s, which is also the visual beat). Nothing in
this module knows any series' vocabulary.

Nothing is dropped silently: every excluded panel is written to panels.curated.json with
its reason, and the panel-conservation gate audits narrated + dropped == all story.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from manhwa2vid.config import get_nested
from manhwa2vid.models import ChapterSynopsis, SceneCard


def words_per_shown_panel(config: dict[str, Any]) -> float:
    wpm = float(get_nested(config, "script", "target_wpm", default=235))
    dwell = float(get_nested(config, "video", "target_panel_seconds", default=2.5))
    return wpm * dwell / 60.0


def _panel_sort_key(panel_id: str) -> tuple[int, int, str]:
    import re

    m = re.match(r"p(\d+)_(\d+)", panel_id, re.I)
    return (int(m.group(1)), int(m.group(2)), panel_id) if m else (9999, 9999, panel_id)


def select_narrated_panels(
    cards: list[SceneCard],
    synopsis: ChapterSynopsis | None,
    config: dict[str, Any],
    *,
    n_chapters: int = 1,
    pinned: set[str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Pick the panels the script narrates; name a reason for every one it drops.

    Salience, highest first — all signals the pipeline already computes, none of them
    series vocabulary:
      1. the card matches a synopsis plot_fact (grounding.score_fact_against_card);
      2. the panel carries dialogue (the register is dialogue-driven: the reference
         profile measures a reported-speech verb every ~32 words);
      3. named people are present;
      4. pinned panels (chapter closers, the flashforward transition anchor) always stay.
    Ties break by reading order, so the same input always selects the same set.

    A continuity floor caps how many CONSECUTIVE panels may vanish: the reference crops
    and skips, but it never jump-cuts across a whole scene. Every third panel of a long
    dropped run is restored, cheapest-first, which keeps the visual thread without
    meaningfully moving the word budget.
    """
    from manhwa2vid.script.grounding import score_fact_against_card

    story = [c for c in cards if c.is_story and c.panel_ids]
    all_ids = sorted({pid for c in story for pid in c.panel_ids}, key=_panel_sort_key)
    if not all_ids:
        return [], {}

    target_words = float(
        get_nested(config, "script", "words_per_chapter", default=550)
    ) * max(1, n_chapters)
    budget = max(1, round(target_words / words_per_shown_panel(config)))
    if budget >= len(all_ids):
        return all_ids, {}

    pinned = set(pinned or set())
    by_panel: dict[str, SceneCard] = {}
    for card in story:
        for pid in card.panel_ids:
            by_panel[pid] = card

    facts = [f for f in (synopsis.plot_facts if synopsis else []) if f.strip()]
    scores: dict[str, float] = {}
    for pid in all_ids:
        card = by_panel[pid]
        fact_score = max((score_fact_against_card(f, card) for f in facts), default=0.0)
        has_dialogue = bool((card.source_text or "").strip())
        named_people = sum(
            1 for person in card.people if person.name_used or person.ref not in ("", "new")
        )
        scores[pid] = (
            (100.0 if pid in pinned else 0.0)
            + fact_score * 10.0
            + (5.0 if has_dialogue else 0.0)
            + min(named_people, 3) * 1.0
        )

    ranked = sorted(all_ids, key=lambda pid: (-scores[pid], _panel_sort_key(pid)))
    keep = set(ranked[:budget])

    # Continuity floor: break up long dropped runs.
    max_gap = 3
    i = 0
    while i < len(all_ids):
        if all_ids[i] in keep:
            i += 1
            continue
        j = i
        while j < len(all_ids) and all_ids[j] not in keep:
            j += 1
        run = all_ids[i:j]
        for k in range(max_gap, len(run), max_gap + 1):
            keep.add(run[k])
        i = j

    narrated = [pid for pid in all_ids if pid in keep]
    dropped: dict[str, str] = {}
    for pid in all_ids:
        if pid in keep:
            continue
        card = by_panel[pid]
        why = []
        if not (card.source_text or "").strip():
            why.append("no dialogue")
        if not card.people:
            why.append("nobody on screen")
        if scores[pid] < 5.0:
            why.append("matches no plot fact")
        dropped[pid] = "; ".join(why) or "below salience budget"
    return narrated, dropped


def write_curation(paths: dict[str, Path], narrated: list[str], dropped: dict[str, str]) -> None:
    paths["panels_curated_json"].write_text(
        json.dumps({"narrated": narrated, "dropped": dropped}, indent=1), encoding="utf-8"
    )
