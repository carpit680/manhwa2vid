"""Bind finished narration to panels — after the writing, never before.

This is the inversion. The old pipeline chose panels first and asked a model to write
words for them, which made omission, compression and reordering structurally
impossible; this stage takes prose that is already final and finds the images that
illustrate it. Panels the narration never calls for simply do not appear, and a cold
open legitimately shows page 20 before page 1.

Alignment is *retrieval*, not generation — "which pages is this paragraph talking
about" is a far easier question than "write a paragraph for these panels", which is why
a cheap model is fine here and why nothing it returns can damage the prose. The mapping
call cannot rewrite a single word: its output is a page range per paragraph, and every
failure mode below degrades to showing slightly wrong images, never to changing what is
said.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.llm.vision_utils import page_max_width
from manhwa2vid.models import Panel, ScriptBeat, save_json
from manhwa2vid.panels.filter import load_story_panels
from manhwa2vid.qa import QAReport
from manhwa2vid.script.freeform import paragraphs

console = Console()

_SYSTEM = """You match paragraphs of a finished recap narration to the manhwa pages they
describe. You are not writing or editing text — only pointing at pages.

You are given numbered paragraphs and then the chapter's pages in reading order.

Return JSON only:
{"map": [{"paragraph": 1, "first_page": "0002", "last_page": "0005"}, ...]}

Rules:
- One entry per paragraph, in paragraph order, covering every paragraph.
- A paragraph's range is the pages whose ART shows what it narrates. Ranges may be a
  single page. Consecutive paragraphs usually advance through the chapter, but a recap
  may open on a LATE moment and jump back — if paragraph 1 narrates the climax, give it
  the climax's pages, not page 1.
- Ranges may overlap slightly when two paragraphs cover one continuous moment.
- Never invent page numbers. Use only pages you were shown."""


def _page_of(panel_id: str) -> str:
    match = re.match(r"p(\d+)_", panel_id)
    return match.group(1) if match else ""


def _normalize_page(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits.zfill(4) if digits else ""


def request_alignment(
    para_texts: list[str],
    pages: list[Path],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Ask a model which pages each paragraph is about. Returns raw map entries."""
    from manhwa2vid.llm.provider import get_llm_provider

    provider = get_llm_provider(get_nested(config, "align", "provider", default=None), config)
    model = get_nested(config, "align", "model", default=None)
    if model:
        provider.vision_model = model
    provider.temperature = 0.0

    numbered = "\n\n".join(f"[paragraph {i}]\n{t}" for i, t in enumerate(para_texts, start=1))
    raw = provider.describe_labeled_panels(
        [(f"[page {p.stem}]", p) for p in pages],
        f"{_SYSTEM}\n\nPARAGRAPHS:\n\n{numbered}",
        max_width=page_max_width(config),
    )
    data = json.loads(raw) if isinstance(raw, str) else raw
    return list(data.get("map") or [])


#: The narration's own way of saying it just jumped in time. These open a paragraph
#: that legitimately begins a new time block.
_TIME_JUMP_RE = re.compile(
    r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|twenty[- ]?five|"
    r"seventy[- ]?six|a\s+few|several)[\s-]+"
    r"(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?|decades?)\s+"
    r"(?:earlier|later|ago|before|after|prior)|"
    r"\b(?:meanwhile|back in the|years later|moments later|earlier that)\b",
    re.I,
)

_BOUNDARY_SYSTEM = """You are locating printed scene-break captions in manhwa panels.

You are given a caption's text, then a series of labeled panels from one page.

Return JSON only: {"panel": "p0005_14"} — the id of the panel that CONTAINS that
caption, or {"panel": null} if none of them do. Report only what you can read."""


def locate_boundary_panels(
    paths: dict[str, Path],
    panels: list[Panel],
    config: dict[str, Any],
) -> list[str]:
    """Panel ids where a printed time skip begins.

    The read stage records the PAGE a marker appears on, and that is too coarse to cut
    on: these pages are 10-14k pixel scroll strips, and page 0005 of Frozen Player holds
    the end of the Frost Queen fight in panels 1-13 and "76 HOURS AGO, ANTARCTICA" in
    panel 14. Cutting the whole page into the flashback would strand thirteen fight
    panels — worse than the bug it fixes. So the marker's page is narrowed to the marker's
    PANEL with one cheap vision call per boundary page.
    """
    facts_path = paths.get("chapter_facts_json")
    if not facts_path or not facts_path.exists():
        return []
    try:
        markers = json.loads(facts_path.read_text(encoding="utf-8")).get("time_markers") or []
    except Exception:
        return []
    if not markers:
        return []

    by_page: dict[str, list[Panel]] = {}
    for panel in panels:
        by_page.setdefault(_page_of(panel.id), []).append(panel)

    from manhwa2vid.llm.provider import get_llm_provider

    provider = get_llm_provider(get_nested(config, "align", "provider", default=None), config)
    model = get_nested(config, "align", "model", default=None)
    if model:
        provider.vision_model = model
    provider.temperature = 0.0

    found: list[str] = []
    for marker in markers:
        page = _normalize_page(marker.get("page"))
        text = str(marker.get("text") or "").strip()
        page_panels = by_page.get(page) or []
        if not text or not page_panels:
            continue
        if len(page_panels) == 1:
            found.append(page_panels[0].id)
            continue
        try:
            raw = provider.describe_labeled_panels(
                [(f"[{p.id}]", paths["root"] / p.image_path) for p in page_panels],
                f'{_BOUNDARY_SYSTEM}\n\nCAPTION TO FIND: "{text}"',
            )
            pid = (json.loads(raw) if isinstance(raw, str) else raw).get("panel")
        except Exception:
            pid = None
        if pid and any(p.id == pid for p in page_panels):
            found.append(str(pid))
    return found


def distribute_within_blocks(
    panel_lists: list[list[str]],
    ordered_ids: list[str],
    block_of: list[int],
    blocks: list[tuple[int, int]],
    min_panels: dict[int, int] | None = None,
) -> list[list[str]]:
    """Lay each block's panels out as contiguous runs, sized by each paragraph's airtime.

    Decide all the LENGTHS first, then lay them end to end. That ordering is the whole
    point: forward progress, no duplicates, no gaps and no leftovers are then true by
    construction rather than by a rule that has to be got right.

    Three earlier versions tried to steer this with the alignment model's per-paragraph
    page ranges and each broke differently — a 33-word beat handed 170 panels because it
    sat last in its block; a beat frozen 22.9s because a greedy neighbour ate its share;
    then leftovers dealt from the block's tail to early paragraphs, which put 7 of Solo
    Leveling's 38 beats back into stepping backward. The model's ranges are simply not
    reliable enough at 38 paragraphs to divide a block by, and every attempt to correct
    them added a rule that interacted badly with the last one.

    So the map no longer sizes anything. It is still requested and saved to
    script.alignment.json for inspection, and TIME BOUNDARIES (which come from captions
    the chapter prints, not from the model) still decide where blocks begin — that is
    what actually keeps the picture with the narration. Within a block, a recap moves
    front to back, and how long it lingers is how long the narrator talks.
    """
    del panel_lists  # sizes come from airtime; the model's ranges are advisory only
    min_panels = min_panels or {}
    out: list[list[str]] = [[] for _ in block_of]

    for block_idx, (lo, hi) in enumerate(blocks):
        members = [i for i, b in enumerate(block_of) if b == block_idx]
        available = hi - lo
        if not members or available <= 0:
            continue

        wants = [max(1, min_panels.get(i + 1, 1)) for i in members]
        total = sum(wants)
        # Largest-remainder apportionment: proportional, integral, and sums EXACTLY to
        # the panels available — so nothing is left over to deal out afterwards.
        exact = [available * w / total for w in wants]
        lengths = [max(1, int(x)) for x in exact]
        while sum(lengths) > available and max(lengths) > 1:
            lengths[lengths.index(max(lengths))] -= 1
        remainder = available - sum(lengths)
        for k in sorted(range(len(members)), key=lambda j: -(exact[j] - int(exact[j])))[
            : max(0, remainder)
        ]:
            lengths[k] += 1

        cursor = lo
        for para_i, length in zip(members, lengths):
            end = min(cursor + length, hi)
            out[para_i] = ordered_ids[cursor:end]
            cursor = end
        if cursor < hi and members:
            out[members[-1]] = out[members[-1]] + ordered_ids[cursor:hi]

    return [
        run or [ordered_ids[blocks[block_of[i]][0]]] for i, run in enumerate(out)
    ]


def clamp_to_time_blocks(
    panel_lists: list[list[str]],
    para_texts: list[str],
    ordered_ids: list[str],
    boundary_ids: list[str],
) -> list[list[str]]:
    """Keep each paragraph's panels inside the time block its narration is in.

    Without this the picture crossed a printed time skip a whole beat before the
    narrator did: the Frost Queen fight was still being described while the panels had
    already cut to "76 HOURS AGO". A viewer reads that as a broken video, and no
    quality of narration survives it.
    """
    cuts = sorted(
        {ordered_ids.index(b) for b in boundary_ids if b in ordered_ids}
    )
    if not cuts:
        return panel_lists
    edges = [0, *cuts, len(ordered_ids)]
    blocks = [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]

    # Paragraph -> block. Block advances at each paragraph that ANNOUNCES a jump.
    index_of = {pid: i for i, pid in enumerate(ordered_ids)}
    block_of: list[int] = []
    current = 0
    for text in para_texts:
        if _TIME_JUMP_RE.search(text) and current + 1 < len(blocks):
            current += 1
        block_of.append(current)

    # A paragraph that announces a jump should open ON the caption that prints it —
    # otherwise the chapter's own "76 HOURS AGO" panel is the one image nobody shows.
    boundary_at = {ordered_ids.index(b): b for b in boundary_ids if b in ordered_ids}
    first_para_of_block: dict[int, int] = {}
    for i, block_idx in enumerate(block_of):
        first_para_of_block.setdefault(block_idx, i)

    clamp_to_time_blocks.last_blocks = blocks          # reused by the caller
    clamp_to_time_blocks.last_block_of = block_of

    out: list[list[str]] = []
    for pids, block_idx in zip(panel_lists, block_of):
        lo, hi = blocks[block_idx]
        kept = [pid for pid in pids if lo <= index_of.get(pid, -1) < hi]
        if not kept:
            # Everything fell outside the block. Fall back to the END the paragraph
            # overran, not to the block's head: a beat narrating the fight's aftermath
            # whose panels sat past the boundary was sent back to the chapter's opening
            # and replayed page one mid-scene.
            want = max(1, len(pids))
            positions = [index_of[pid] for pid in pids if pid in index_of]
            overran_end = bool(positions) and min(positions) >= hi
            block = ordered_ids[lo:hi]
            kept = block[-want:] if overran_end else block[:want]
        caption = boundary_at.get(lo)
        if caption and first_para_of_block.get(block_idx) == len(out) and caption not in kept:
            kept = [caption, *kept]
        out.append(kept)
    return out


def _nearest_page(ordered_pages: list[str], page: str) -> str:
    if page in ordered_pages:
        return page
    return min(ordered_pages, key=lambda pg: abs(int(pg or 0) - int(page or 0)))


def expand_to_panels(
    entries: list[dict[str, Any]],
    n_paragraphs: int,
    panels: list[Panel],
    *,
    empty_ids: set[str] | None = None,
    min_panels: dict[int, int] | None = None,
) -> list[list[str]]:
    """Turn paragraph→page ranges into paragraph→panel lists, deterministically.

    Everything after the model call is plain code so a re-run with the same map produces
    the same video. Two fallbacks, both chosen to fail toward "slightly wrong images"
    rather than "a beat with no images", because a beat that resolves to zero panels has
    its audio dropped from the mix entirely.
    """
    min_panels = min_panels or {}
    by_page: dict[str, list[str]] = {}
    for panel in panels:
        by_page.setdefault(_page_of(panel.id), []).append(panel.id)
    ordered_pages = sorted(by_page)
    if not ordered_pages:
        return [[] for _ in range(n_paragraphs)]

    ranges: dict[int, tuple[str, str]] = {}
    for entry in entries:
        try:
            index = int(entry.get("paragraph"))
        except (TypeError, ValueError):
            continue
        if not 1 <= index <= n_paragraphs:
            continue
        first = _normalize_page(entry.get("first_page"))
        last = _normalize_page(entry.get("last_page")) or first
        if first:
            ranges[index] = (first, last if last >= first else first)

    out: list[list[str]] = []
    for index in range(1, n_paragraphs + 1):
        if index not in ranges:
            # Unmapped paragraph: interpolate between its neighbours so it still lands
            # somewhere plausible in the chapter rather than at page 1.
            prev_end = next(
                (ranges[j][1] for j in range(index - 1, 0, -1) if j in ranges), ordered_pages[0]
            )
            next_start = next(
                (ranges[j][0] for j in range(index + 1, n_paragraphs + 1) if j in ranges),
                ordered_pages[-1],
            )
            lo, hi = min(prev_end, next_start), max(prev_end, next_start)
        else:
            lo, hi = ranges[index]

        picked = [pid for page in ordered_pages if lo <= page <= hi for pid in by_page[page]]
        if empty_ids:
            # Visually empty panels (mostly-white margins, transition fragments) are
            # never worth 2.5s of screen; drop them unless they are ALL the range has.
            kept = [pid for pid in picked if pid not in empty_ids]
            if kept:
                picked = kept
        if picked and min_panels.get(index, 0) > len(picked):
            # The paragraph's airtime needs more images than its range holds — one FP
            # beat ended up as a single panel frozen for 17 seconds because the range
            # was thin and the emptiness filter thinned it further. Borrow whole
            # adjacent pages, nearest first, until the estimated dwell is sane.
            need = min_panels[index]
            lo_i = ordered_pages.index(_nearest_page(ordered_pages, lo))
            hi_i = ordered_pages.index(_nearest_page(ordered_pages, hi))
            while len(picked) < need and (lo_i > 0 or hi_i < len(ordered_pages) - 1):
                skip = empty_ids or set()
                if hi_i < len(ordered_pages) - 1:
                    hi_i += 1
                    extra = [p for p in by_page[ordered_pages[hi_i]] if p not in skip]
                    picked = picked + extra
                if len(picked) < need and lo_i > 0:
                    lo_i -= 1
                    extra = [p for p in by_page[ordered_pages[lo_i]] if p not in skip]
                    picked = extra + picked
        if not picked:
            # The range named pages that have no story panels (all blank/filtered).
            # Borrow the nearest page that does, so the beat keeps its audio.
            nearest = min(ordered_pages, key=lambda pg: (abs(int(pg) - int(lo or ordered_pages[0]))))
            picked = list(by_page[nearest])
        out.append(picked)
    return out


def key_panels_for(
    panel_ids: list[str],
    max_keys: int = 3,
    scores: dict[str, float] | None = None,
) -> list[str]:
    """A few load-bearing panels per beat, returned in the beat's own order.

    With content scores available (fraction of the frame that is actually art), the
    keys are the most content-dense panels — replacing the positional spread that was
    only ever a placeholder and happily crowned a margin-heavy panel. Without scores,
    the positional spread remains so old callers behave identically.
    """
    if len(panel_ids) <= max_keys:
        return list(panel_ids)
    if scores:
        ranked = sorted(panel_ids, key=lambda pid: scores.get(pid, 0.0), reverse=True)
        chosen = set(ranked[:max_keys])
        return [pid for pid in panel_ids if pid in chosen]
    step = (len(panel_ids) - 1) / (max_keys - 1)
    keys: list[str] = []
    for i in range(max_keys):
        pid = panel_ids[round(i * step)]
        if pid not in keys:
            keys.append(pid)
    return keys


def split_long_paragraphs(paras: list[str], max_words: int = 90) -> list[str]:
    """Break paragraphs too long to bind to images precisely, at sentence boundaries.

    Granularity is a PRODUCTION concern and belongs here, not in the writer's prompt.
    Telling the writer "a paragraph is the unit that will later be matched to images"
    leaked exactly the panel-thinking this architecture removes, and the run that carried
    that line produced 10 paragraphs for 198 panels — ~20 panels of screen time per audio
    file, which is far too coarse for A/V precision. The writing is untouched: this only
    decides where an already-written paragraph is cut.
    """
    out: list[str] = []
    for para in paras:
        words = para.split()
        if len(words) <= max_words:
            out.append(para)
            continue
        sentences = re.split(r"(?<=[.!?])\s+", para.strip())
        chunk: list[str] = []
        count = 0
        for sentence in sentences:
            chunk.append(sentence)
            count += len(sentence.split())
            if count >= max_words:
                out.append(" ".join(chunk))
                chunk, count = [], 0
        if chunk:
            # Never leave a stub: fold a short tail back into the previous chunk.
            tail = " ".join(chunk)
            if len(tail.split()) < 20 and out:
                out[-1] = f"{out[-1]} {tail}"
            else:
                out.append(tail)
    return out


def align_script(
    text: str,
    paths: dict[str, Path],
    config: dict[str, Any],
) -> tuple[list[ScriptBeat], QAReport]:
    """Freeform prose in, ScriptBeats out. One beat per paragraph."""
    max_words = int(get_nested(config, "align", "max_beat_words", default=90))
    para_texts = split_long_paragraphs(paragraphs(text), max_words)
    pages = sorted(paths["pages"].glob("*.png"))
    panels = load_story_panels(paths)

    entries = request_alignment(para_texts, pages, config)
    boundary_ids = locate_boundary_panels(paths, panels, config)
    save_json(
        paths["script_alignment_json"], {"map": entries, "time_boundaries": boundary_ids}
    )

    from manhwa2vid.panels.split import panel_visual_stats_file

    stats = {p.id: panel_visual_stats_file(paths["root"] / p.image_path) for p in panels}
    empty_ids = {pid for pid, (empty, _score) in stats.items() if empty}
    scores = {pid: score for pid, (_empty, score) in stats.items()}
    if empty_ids:
        console.print(f"[dim]Align: {len(empty_ids)} visually empty panel(s) excluded[/]")
    # Airtime estimate per paragraph: words / (wpm/60). A paragraph must own at least
    # ceil(airtime / max_panel_seconds) panels or a single image freezes on screen for
    # its whole read (measured: one 17-second hold).
    wpm = float(get_nested(config, "script", "target_wpm", default=200))
    max_sec = float(get_nested(config, "video", "max_panel_seconds", default=5.0))
    min_panels = {
        i + 1: max(1, int(-(-len(t.split()) / (wpm / 60.0) // max_sec)))
        for i, t in enumerate(para_texts)
    }
    panel_lists = expand_to_panels(
        entries, len(para_texts), panels, empty_ids=empty_ids, min_panels=min_panels
    )
    ordered_ids = [
        p.id for p in sorted(panels, key=lambda x: x.id) if p.id not in empty_ids
    ]
    if boundary_ids:
        panel_lists = clamp_to_time_blocks(
            panel_lists, para_texts, ordered_ids, boundary_ids
        )
        blocks = clamp_to_time_blocks.last_blocks
        block_of = clamp_to_time_blocks.last_block_of
        console.print(f"[dim]Align: time blocks cut at {boundary_ids}[/]")
    else:
        blocks = [(0, len(ordered_ids))]
        block_of = [0] * len(para_texts)
    panel_lists = distribute_within_blocks(
        panel_lists, ordered_ids, block_of, blocks, min_panels
    )

    beats = [
        ScriptBeat(
            beat_id=i,
            panel_ids=pids,
            narration=para,
            key_panel_ids=key_panels_for(pids, scores=scores),
        )
        for i, (para, pids) in enumerate(zip(para_texts, panel_lists), start=1)
    ]

    report = QAReport(stage="align")
    empty = [b.beat_id for b in beats if not b.panel_ids]
    report.add(
        "beats-have-panels",
        False if empty else True,
        f"paragraph(s) {empty} matched no panels — their audio would be dropped entirely",
        empty=empty,
    )

    shown = {pid for b in beats for pid in b.panel_ids}
    # Coverage over panels WORTH showing — deliberately dropping blanks must not read
    # as lost coverage.
    countable = [p for p in panels if p.id not in empty_ids]
    fraction = len(shown) / max(1, len(countable))
    floor = float(get_nested(config, "align", "min_panel_fraction", default=0.4))
    report.add(
        "panel-coverage",
        True if fraction >= floor else "warn",
        f"narration calls for {fraction:.0%} of story panels (floor {floor:.0%}) — "
        "low coverage usually means the alignment map collapsed, not that the writing "
        "was selective",
        fraction=round(fraction, 3),
        shown=len(shown),
        total=len(countable),
        excluded_empty=len(empty_ids),
    )
    console.print(
        f"[green]Aligned[/] {len(beats)} paragraph(s) → {len(shown)}/{len(panels)} "
        f"story panels ({fraction:.0%})"
    )
    return beats, report
