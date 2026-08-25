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


def expand_to_panels(
    entries: list[dict[str, Any]],
    n_paragraphs: int,
    panels: list[Panel],
) -> list[list[str]]:
    """Turn paragraph→page ranges into paragraph→panel lists, deterministically.

    Everything after the model call is plain code so a re-run with the same map produces
    the same video. Two fallbacks, both chosen to fail toward "slightly wrong images"
    rather than "a beat with no images", because a beat that resolves to zero panels has
    its audio dropped from the mix entirely.
    """
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
        if not picked:
            # The range named pages that have no story panels (all blank/filtered).
            # Borrow the nearest page that does, so the beat keeps its audio.
            nearest = min(ordered_pages, key=lambda pg: (abs(int(pg) - int(lo or ordered_pages[0]))))
            picked = list(by_page[nearest])
        out.append(picked)
    return out


def key_panels_for(panel_ids: list[str], max_keys: int = 3) -> list[str]:
    """A few load-bearing panels per beat, evenly spread across its run.

    With no scene cards there is no salience signal, so this is deliberately positional
    rather than pretending to judge importance. It exists so `budget_panels_for_beat`
    keeps a spread when it has to drop panels, instead of clustering on the opening.
    """
    if len(panel_ids) <= max_keys:
        return list(panel_ids)
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
    save_json(paths["script_alignment_json"], {"map": entries})
    panel_lists = expand_to_panels(entries, len(para_texts), panels)

    beats = [
        ScriptBeat(
            beat_id=i,
            panel_ids=pids,
            narration=para,
            key_panel_ids=key_panels_for(pids),
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
    fraction = len(shown) / max(1, len(panels))
    floor = float(get_nested(config, "align", "min_panel_fraction", default=0.4))
    report.add(
        "panel-coverage",
        True if fraction >= floor else "warn",
        f"narration calls for {fraction:.0%} of story panels (floor {floor:.0%}) — "
        "low coverage usually means the alignment map collapsed, not that the writing "
        "was selective",
        fraction=round(fraction, 3),
        shown=len(shown),
        total=len(panels),
    )
    console.print(
        f"[green]Aligned[/] {len(beats)} paragraph(s) → {len(shown)}/{len(panels)} "
        f"story panels ({fraction:.0%})"
    )
    return beats, report
