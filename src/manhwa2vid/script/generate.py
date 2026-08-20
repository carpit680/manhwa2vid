"""Recap script generation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.characters.bible import format_bible_for_prompt, load_series_bible, naming_priority_rules
from manhwa2vid.characters.link import run_cast_linking
from manhwa2vid.config import get_nested
from manhwa2vid.llm.provider import apply_stage_model, get_stage_llm
from manhwa2vid.models import (
    ChapterSynopsis,
    PanelCast,
    ProjectMeta,
    SceneCard,
    ScriptBeat,
    ScriptDraft,
    ScriptOutlineBeat,
    SeriesBible,
    save_json,
)
from manhwa2vid.panels.filter import load_story_scene_cards
from manhwa2vid.script.grounding import (
    compact_panel_evidence,
    evidence_for_panels,
    format_seeded_outline_for_prompt,
    preassign_outline_from_facts,
    enforce_reading_order,
    inject_closer_evidence,
)
from manhwa2vid.script.lint import banned_words, lint_and_rewrite_script
from manhwa2vid.script.synopsis import (
    format_synopsis_for_prompt,
    generate_chapter_synopsis,
)

console = Console()

_PANEL_SORT_RE = re.compile(r"p(\d+)_(\d+)", re.I)


def _load_prompt_template(name: str) -> str:
    path = Path(__file__).parent / "prompts" / name
    return path.read_text(encoding="utf-8")


def _panel_sort_key(panel_id: str) -> tuple[int, int, str]:
    match = _PANEL_SORT_RE.match(panel_id)
    if match:
        return int(match.group(1)), int(match.group(2)), panel_id
    return 9999, 9999, panel_id


def _scene_cards_to_context(cards: list[SceneCard], bible: SeriesBible) -> str:
    return compact_panel_evidence(cards, bible)


def _sticky_label(person: Any, bible: SeriesBible) -> str:
    if person.ref in bible.characters:
        profile = bible.characters[person.ref]
        if profile.tier.value in ("main", "supporting") or profile.canonical_name[:1].isupper():
            # Prefer canonical name for known cast; keep descriptor only for pure minors
            if not profile.canonical_name.lower().startswith(("guy ", "man ", "woman ", "blonde ")):
                return profile.canonical_name
    return person.name_used or person.descriptor or person.ref


def _cast_context_for_beats(
    outline_beats: list[ScriptOutlineBeat],
    attribution: list[PanelCast],
    bible: SeriesBible,
    cards: list[SceneCard] | None = None,
    *,
    words_per_panel: int = 14,
    max_beat_words: int = 60,
) -> str:
    attr_map = {row.panel_id: row for row in attribution}
    lines: list[str] = []
    for beat in outline_beats:
        people: list[str] = []
        for panel_id in beat.panel_ids:
            row = attr_map.get(panel_id)
            if not row:
                continue
            for person in row.people:
                mc_tag = " [MC]" if person.ref == bible.protagonist_id else ""
                label = _sticky_label(person, bible)
                entry = f"{label}(ref={person.ref}{mc_tag})"
                if entry not in people:
                    people.append(entry)
        char_ids = ", ".join(beat.character_ids) if beat.character_ids else "(from cast below)"
        evid = evidence_for_panels(beat.panel_ids, cards or []) if cards else ""
        # A concrete per-beat word ceiling: every word over budget stretches this beat's
        # panels on screen (audio locks the visuals), so vague "be brief" doesn't cut it.
        # Ceiling, because panels*rate has no upper bound: a 12-panel beat would get a
        # 168-word budget, which is a paragraph of screen-time debt. The measured
        # references (both golds, the reference channel) all sit near 40-45 words/beat.
        max_words = min(max(12, len(beat.panel_ids) * words_per_panel), max_beat_words)
        lines.append(
            f"Beat {beat.beat_id} [{', '.join(beat.panel_ids)}]: "
            f"char_ids={char_ids}; on_screen={'; '.join(people) or '(none)'}; plot={beat.plot_beat}\n"
            f"  MAX {max_words} words for this beat — hard limit, cut the weakest detail first.\n"
            f"  EVIDENCE (narrate ONLY this):\n{evid or '(none)'}\n"
            f"  Do not preview later locations — protagonist id={bible.protagonist_id or '?'}"
        )
    return "\n".join(lines)


def _story_so_far(bible: SeriesBible, meta: ProjectMeta) -> str:
    """Chapters BEFORE this range: approved-script summaries, gaps filled by the brief-read.

    chapter_summaries only exist for chapters whose scripts a human approved; the story
    map covers everything the brief-read pass skimmed. An approved summary wins when
    both exist — it reflects the actual narration voice.
    """
    from manhwa2vid.story.brief import load_story_map, story_so_far_from_map

    merged: dict[str, str] = story_so_far_from_map(load_story_map(meta.series_slug), meta)
    chapter_key = meta.chapters.split("-")[0].strip()
    for ch, summary in bible.chapter_summaries.items():
        if ch != chapter_key:
            merged[ch] = summary
    if not merged:
        return "(first chapter — no prior story)"
    prior = [
        f"Ch {ch}: {summary}"
        for ch, summary in sorted(merged.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0)
    ]
    return "\n".join(prior)


def _story_ahead(meta: ProjectMeta) -> str:
    """Forward knowledge from the brief-read: mechanics and trajectory, never spoilers."""
    from manhwa2vid.story.brief import load_story_map, story_ahead_from_map

    return story_ahead_from_map(load_story_map(meta.series_slug), meta)


def _beats_to_markdown(draft: ScriptDraft) -> str:
    lines = [
        f"# {draft.title} — Chapters {draft.chapters}",
        "",
        f"**Hook:** {draft.hook}",
        "",
        "## Beats",
        "",
    ]
    for beat in draft.beats:
        lines.extend(
            [
                f"### Beat {beat.beat_id}",
                (
                    f"<!-- panels: {', '.join(beat.panel_ids)}"
                    + (f" | key: {', '.join(beat.key_panel_ids)}" if beat.key_panel_ids else "")
                    + " -->"
                ),
                "",
                beat.narration,
                "",
            ]
        )
    lines.append("---")
    lines.append("Edit freely. Save approved version as script.final.md")
    return "\n".join(lines)


def _parse_markdown_beats(path: Path) -> list[ScriptBeat]:
    """Parse beats from markdown (for final script after human edit)."""
    text = path.read_text(encoding="utf-8")
    beats: list[ScriptBeat] = []
    current_panels: list[str] = []
    current_keys: list[str] = []
    current_lines: list[str] = []
    beat_id = 0

    for line in text.splitlines():
        if line.startswith("<!-- panels:"):
            body = line.replace("<!-- panels:", "").replace("-->", "")
            panels_part, _, key_part = body.partition("|")
            current_panels = [p.strip() for p in panels_part.split(",") if p.strip()]
            current_keys = [
                p.strip()
                for p in key_part.replace("key:", "").split(",")
                if p.strip()
            ]
        elif line.startswith("### Beat"):
            if current_lines and beat_id:
                beats.append(
                    ScriptBeat(
                        beat_id=beat_id,
                        panel_ids=current_panels or [f"unknown_{beat_id}"],
                        narration=" ".join(current_lines).strip(),
                        key_panel_ids=[k for k in current_keys if k in current_panels],
                    )
                )
            beat_id += 1
            current_lines = []
        elif line.startswith("#") or line.startswith("**Hook:") or line == "---":
            if line == "---":
                break
            continue
        elif beat_id > 0 and line.strip():
            if line.strip().lower().startswith("edit freely"):
                break
            current_lines.append(line.strip())

    if current_lines and beat_id:
        beats.append(
            ScriptBeat(
                beat_id=beat_id,
                panel_ids=current_panels or [f"unknown_{beat_id}"],
                narration=" ".join(current_lines).strip(),
                key_panel_ids=[k for k in current_keys if k in current_panels],
            )
        )
    return beats


def load_script_beats(paths: dict[str, Path]) -> ScriptDraft:
    if paths["script_json"].exists():
        data = json.loads(paths["script_json"].read_text())
        return ScriptDraft.model_validate(data)
    final = paths["script_final"] if paths["script_final"].exists() else paths["script_draft"]
    beats = _parse_markdown_beats(final)
    meta = json.loads(paths["meta"].read_text())
    return ScriptDraft(title=meta["title"], chapters=meta["chapters"], beats=beats)


def _covered_panel_ids(beats: list[ScriptBeat] | list[ScriptOutlineBeat]) -> set[str]:
    return {pid for beat in beats for pid in beat.panel_ids}


def _attach_missing_panels_to_beats(
    all_panel_ids: list[str],
    beats: list[ScriptBeat],
) -> list[ScriptBeat]:
    """Attach uncovered story panels to the nearest story beat — never invent caption beats."""
    if not beats:
        return beats

    covered = _covered_panel_ids(beats)
    missing = [pid for pid in all_panel_ids if pid not in covered]
    if not missing:
        return beats

    # Build ordered list of (panel_id, beat_index) anchors from existing coverage
    anchors: list[tuple[str, int]] = []
    for idx, beat in enumerate(beats):
        for pid in sorted(beat.panel_ids, key=_panel_sort_key):
            anchors.append((pid, idx))
    if not anchors:
        beats[0].panel_ids = list(dict.fromkeys([*beats[0].panel_ids, *missing]))
        return beats

    for panel_id in missing:
        best_idx = 0
        best_dist = 10**9
        p_key = _panel_sort_key(panel_id)
        for anchor_id, beat_idx in anchors:
            a_key = _panel_sort_key(anchor_id)
            dist = abs(p_key[0] - a_key[0]) * 100 + abs(p_key[1] - a_key[1])
            if dist < best_dist:
                best_dist = dist
                best_idx = beat_idx
        beats[best_idx].panel_ids = list(dict.fromkeys([*beats[best_idx].panel_ids, panel_id]))
        beats[best_idx].panel_ids.sort(key=_panel_sort_key)
        anchors.append((panel_id, best_idx))

    console.print(
        f"[yellow]Attached {len(missing)} uncovered panel(s) to nearest story beats[/] "
        f"(no caption filler)"
    )
    return beats


def _panel_cast_index(cards: list[SceneCard], bible: SeriesBible) -> str:
    """Compact panel → cast map for outline coverage (no frame captions)."""
    return compact_panel_evidence(cards, bible)


def _complete_json(llm: Any, system: str, user: str, *, fallback_model: str = "llama-3.3-70b-versatile") -> dict[str, Any]:
    """Complete with JSON mode; retry once on validate failure with fallback model."""
    try:
        raw = llm.complete(system, user, json_mode=True)
        if raw.strip():
            return json.loads(raw)
    except Exception as exc:
        console.print(f"[yellow]JSON complete failed ({getattr(llm, 'model', '?')}):[/] {exc}")

    original = getattr(llm, "model", None)
    if hasattr(llm, "model") and original != fallback_model:
        console.print(f"[yellow]Retrying JSON with fallback model[/] {fallback_model}")
        llm.model = fallback_model
        try:
            # Trim user payload for fallback reliability
            trimmed = user if len(user) < 24000 else user[:12000] + "\n…\n" + user[-8000:]
            raw = llm.complete(system, trimmed, json_mode=True)
            return json.loads(raw)
        finally:
            if original:
                llm.model = original
    raise RuntimeError("script JSON generation failed")


def _chapter_count(meta: ProjectMeta, paths: dict[str, Path] | None) -> int:
    """How many chapters this project covers, from data.

    Preferred source is pages/sources.json (written at ingest, one record per page with
    its chapter_num) — it reflects what was actually imported. Falls back to parsing
    meta.chapters ("3", "1-10", "2,4"), then to 1. Never a per-series value.
    """
    try:
        if paths is not None:
            src = paths["pages"] / "sources.json"
            if src.exists():
                records = json.loads(src.read_text(encoding="utf-8"))
                chapters = {r.get("chapter_num") for r in records if r.get("chapter_num") is not None}
                if chapters:
                    return len(chapters)
    except Exception:
        pass
    total = 0
    for part in str(meta.chapters or "").split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", part)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            total += max(0, hi - lo + 1)
        elif part.isdigit():
            total += 1
    return max(1, total)


def _target_beat_count(meta: ProjectMeta, paths: dict[str, Path] | None, config: dict[str, Any]) -> int:
    """Beats scale with how much story there is, not a fixed constant.

    A fixed max_beats=18 was tuned on a single ~50-panel chapter (2.9 panels/beat) and
    then met a 211-panel two-chapter project: 11.7 panels/beat, every beat forced to
    summarize a dozen panels, and the alignment audit correctly rejected 13 of 18 of
    them. The stable quantity across the measured references is beats per CHAPTER
    (hand-written golds: 17 and ~12/chapter; the reference channel: ~12/chapter), so
    the budget derives from chapter count, clamped by min_beats and the max_beats cap.
    """
    per_chapter = int(get_nested(config, "script", "beats_per_chapter", default=14))
    min_beats = int(get_nested(config, "script", "min_beats", default=10))
    cap = int(get_nested(config, "script", "max_beats", default=45))
    return max(min_beats, min(cap, per_chapter * _chapter_count(meta, paths)))




_REVEAL_STOP = frozenset(
    """
    the a an and or but so of to in on at for with from by as is are was were be been
    have has had this that it its his her their you your they them he she we i not no
    what when where who how why there here then than now all any some very really just
    """.split()
)


def _closing_panel_terms(cards: list[SceneCard], tail: int = 6) -> set[str]:
    """Distinctive content words from the last few story panels' on-panel text."""
    by_panel: dict[str, str] = {}
    for card in cards:
        for pid in card.panel_ids:
            by_panel[pid] = card.source_text or ""
    ordered = sorted(by_panel, key=_panel_sort_key)
    text = " ".join(by_panel[pid] for pid in ordered[-tail:]).lower()
    words = re.findall(r"[a-z][a-z'-]{3,}", text)
    return {w for w in words if w not in _REVEAL_STOP}

def _run_outline_pass(
    meta: ProjectMeta,
    cards: list[SceneCard],
    bible: SeriesBible,
    synopsis: ChapterSynopsis,
    config: dict[str, Any],
    paths: dict[str, Path] | None = None,
) -> tuple[str, list[ScriptOutlineBeat]]:
    template = _load_prompt_template("outline.txt")
    max_beats = _target_beat_count(meta, paths, config)
    system = template.format(max_beats=max_beats)

    seeded = preassign_outline_from_facts(synopsis, cards, bible, max_beats=max_beats)
    # Beats must be contiguous runs in reading order, or two of them narrate one moment.
    seeded = enforce_reading_order(seeded)
    # The ending is pinned from the panels themselves, not trusted to prose compression.
    seeded = inject_closer_evidence(seeded, cards)
    console.print(f"[dim]Seeded outline from plot_facts → {len(seeded)} panel-grounded beats[/]")

    llm = apply_stage_model(get_stage_llm("script", config), "script", config)

    all_panel_ids = sorted({pid for card in cards for pid in card.panel_ids}, key=_panel_sort_key)
    user = (
        f"Title: {meta.title}\nChapters: {meta.chapters}\n\n"
        f"Protagonist id: {bible.protagonist_id or '(detect from bible)'}\n"
        f"Return EXACTLY {len(seeded)} beats, beat_id 1..{len(seeded)}, panel_ids unchanged.\n"
        f"All story panel_ids to cover ({len(all_panel_ids)}): {', '.join(all_panel_ids)}\n\n"
        f"{naming_priority_rules(bible, config)}\n\n"
        f"Chapter synopsis (arc + sticky cast; facts are a checklist, not free reassignment):\n"
        f"{format_synopsis_for_prompt(synopsis)}\n\n"
        f"Story so far:\n{_story_so_far(bible, meta)}\n\n"
        + (f"Story ahead (context only — never previewed in beats):\n{_story_ahead(meta)}\n\n" if _story_ahead(meta) else "")
        + f"Character bible:\n{format_bible_for_prompt(bible)}\n\n"
        f"SEEDED beats (KEEP panel_ids; smooth plot_beat wording only):\n"
        f"{format_seeded_outline_for_prompt(seeded, cards)}\n\n"
        f"Full panel evidence:\n{_scene_cards_to_context(cards, bible)}"
    )
    # The model reliably ignores the beat count on the first ask, so verify and re-ask
    # once with the shortfall named. _reconcile_outline_panels is the backstop, but a
    # collapsed outline throws away the LLM's wording for every merged beat — retrying
    # is what actually keeps that wording.
    attempt_user = user
    for attempt in range(2):
        try:
            data = _complete_json(llm, system, attempt_user)
            outline = [ScriptOutlineBeat.model_validate(b) for b in data.get("beats", [])]
            if len(outline) < len(seeded) and attempt == 0:
                console.print(
                    f"[yellow]Outline returned {len(outline)}/{len(seeded)} beats — re-asking[/]"
                )
                attempt_user = (
                    f"{user}\n\nYour previous reply returned {len(outline)} beats. "
                    f"That is WRONG. Return all {len(seeded)} seeded beats, beat_id "
                    f"1..{len(seeded)}, each with its seeded panel_ids unchanged. "
                    "Rewrite only the plot_beat wording."
                )
                continue
            # Prefer LLM wording but restore panel bindings from seed if LLM drifted
            outline = _reconcile_outline_panels(seeded, outline)
            outline = enforce_reading_order(outline)
            outline = inject_closer_evidence(outline, cards)
            if outline:
                return str(data.get("hook", synopsis.logline)), outline
        except Exception as exc:
            console.print(f"[yellow]Outline LLM failed — using seeded outline:[/] {exc}")
            break

    return synopsis.logline or "Chapter recap", seeded


def _reconcile_outline_panels(
    seeded: list[ScriptOutlineBeat],
    llm_beats: list[ScriptOutlineBeat],
) -> list[ScriptOutlineBeat]:
    """Keep LLM plot wording when possible, but never lose seed panel bindings."""
    if not llm_beats:
        return seeded
    # The seed is the deterministic, panel-grounded structure; the LLM pass is only
    # allowed to smooth wording. A materially shorter beat list means it merged scenes,
    # and reconciling would dump every orphaned panel onto the survivors (one ch1 run
    # produced a single 32-panel beat spanning half the chapter). Keep the seed's
    # structure and graft on whatever wording we can match by beat_id.
    if len(llm_beats) < max(2, int(len(seeded) * 0.75)):
        console.print(
            f"[yellow]Outline pass collapsed {len(seeded)} seeded beats to {len(llm_beats)}[/] — "
            "keeping seeded structure, grafting LLM wording only"
        )
        llm_plot = {b.beat_id: b.plot_beat.strip() for b in llm_beats if b.plot_beat.strip()}
        return [
            b.model_copy(update={"plot_beat": llm_plot.get(b.beat_id, b.plot_beat)})
            for b in seeded
        ]
    seed_by_id = {b.beat_id: b for b in seeded}
    # If LLM kept same beat count and mostly same panels, accept with seed fallback per beat
    reconciled: list[ScriptOutlineBeat] = []
    used_panels: set[str] = set()
    for beat in llm_beats:
        seed = seed_by_id.get(beat.beat_id)
        panels = [pid for pid in beat.panel_ids if pid]
        if seed and (not panels or set(panels) != set(seed.panel_ids)):
            # If overlap is weak, force seed panels
            overlap = set(panels) & set(seed.panel_ids)
            if len(overlap) < max(1, len(seed.panel_ids) // 2):
                panels = list(seed.panel_ids)
                plot = beat.plot_beat.strip() or seed.plot_beat
                char_ids = beat.character_ids or seed.character_ids
            else:
                plot = beat.plot_beat.strip() or seed.plot_beat
                char_ids = beat.character_ids or seed.character_ids
        else:
            plot = beat.plot_beat
            char_ids = beat.character_ids
            if seed and not panels:
                panels = list(seed.panel_ids)
        panels = [pid for pid in panels if pid not in used_panels]
        if not panels and seed:
            panels = [pid for pid in seed.panel_ids if pid not in used_panels]
        if not panels:
            continue
        used_panels.update(panels)
        reconciled.append(
            ScriptOutlineBeat(
                beat_id=len(reconciled) + 1,
                panel_ids=sorted(panels, key=_panel_sort_key),
                character_ids=char_ids,
                plot_beat=plot,
            )
        )
    # Attach any seed panels the LLM dropped
    missing = [pid for b in seeded for pid in b.panel_ids if pid not in used_panels]
    if missing and reconciled:
        shims = [
            ScriptBeat(
                beat_id=b.beat_id,
                panel_ids=b.panel_ids,
                narration=b.plot_beat,
                character_ids=b.character_ids,
            )
            for b in reconciled
        ]
        all_ids = sorted({pid for b in seeded for pid in b.panel_ids}, key=_panel_sort_key)
        shims = _attach_missing_panels_to_beats(all_ids, shims)
        plot_by_id = {r.beat_id: r.plot_beat for r in reconciled}
        reconciled = [
            ScriptOutlineBeat(
                beat_id=s.beat_id,
                panel_ids=s.panel_ids,
                character_ids=s.character_ids,
                plot_beat=plot_by_id.get(s.beat_id, s.narration),
            )
            for s in shims
        ]
    return reconciled or seeded


def _token_overlap(a: str, b: str) -> float:
    """Share of a's content tokens that also appear in b (hook-vs-beat-1 dedup)."""
    ta = {t for t in re.findall(r"[a-z0-9]+", a.lower()) if len(t) > 3}
    tb = {t for t in re.findall(r"[a-z0-9]+", b.lower()) if len(t) > 3}
    if not ta:
        return 0.0
    return len(ta & tb) / len(ta)


def _mark_closer_beat(
    outline_beats: list[ScriptOutlineBeat],
    synopsis: ChapterSynopsis,
) -> list[ScriptOutlineBeat]:
    """Flag the final outline beat as the chapter closer and fold the open thread into
    its plot so the narration ends on a forward hook instead of trailing off."""
    if not outline_beats:
        return outline_beats
    last = outline_beats[-1]
    thread = next((t.strip() for t in synopsis.open_threads if t.strip()), "")
    plot = last.plot_beat
    if thread and thread.lower() not in plot.lower():
        plot = f"{plot} / CLOSER — end on this open thread: {thread}"[:400]
    outline_beats[-1] = last.model_copy(update={"is_closer": True, "plot_beat": plot})
    return outline_beats


def _bible_names_in_text(text: str, bible: SeriesBible) -> list[str]:
    """Canonical main/supporting names present in a narration string."""
    low = text.lower()
    hits: list[str] = []
    for profile in bible.characters.values():
        if profile.merged_into or not profile.canonical_name.strip():
            continue
        if profile.tier.value not in ("main", "supporting"):
            continue
        name = profile.canonical_name.strip()
        # tolerate hyphen/space and unicode-hyphen variants
        variants = {name.lower(), name.lower().replace("-", " "), name.lower().replace("‑", "-")}
        if any(v in low for v in variants):
            hits.append(name)
    return hits


def _chunked(seq: list[Any], size: int) -> list[list[Any]]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def _narration_chunk_user(
    meta: ProjectMeta,
    chunk: list[ScriptOutlineBeat],
    hook: str,
    bible: SeriesBible,
    attribution: list[PanelCast],
    synopsis: ChapterSynopsis,
    config: dict[str, Any],
    cards: list[SceneCard] | None,
    *,
    introduced: list[str],
    running_summary: list[str],
    whole_script: bool = False,
) -> str:
    # Writing every beat in one context is the biggest quality lever available: a model
    # can only guarantee "each moment lands once" when it is the author of all of them.
    # Say so explicitly, or it treats the batch as just another chunk.
    scope_note = (
        f"\nYou are writing the ENTIRE recap in this one response - all {len(chunk)} beats, "
        "start to finish. Compose it as a single continuous script, not as independent "
        "summaries: every fact, exchange, and reaction appears in exactly ONE beat, each "
        "beat picks up where the last left off, and the arc builds to the closer. You "
        "already know what the earlier beats said, because you wrote them.\n"
        if whole_script
        else ""
    )
    closer_note = ""
    if any(b.is_closer for b in chunk):
        closer_ids = [b.beat_id for b in chunk if b.is_closer]
        thread = next((t.strip() for t in synopsis.open_threads if t.strip()), "")
        closer_note = (
            f"\nBeat(s) {closer_ids} are the CLOSER — this is the chapter's ending. "
            f"Tie back to the core tension ({synopsis.logline or 'the chapter logline'}) in one clause, "
            f"then land on this open thread as a concrete forward hook: {thread or '(derive from the arc)'}. "
            f"Do not trail off mid-moment.\n"
        )
    return (
        f"Title: {meta.title}\nChapters: {meta.chapters}\nHook: {hook}\n"
        f"{scope_note}{closer_note}\n"
        f"Already introduced (never repeat their intro clause): "
        f"{', '.join(introduced) or '(nobody yet — this chunk contains the first beats)'}\n\n"
        f"{naming_priority_rules(bible, config)}\n\n"
        f"Chapter synopsis (naming/continuity only — do NOT preview later acts):\n"
        f"{format_synopsis_for_prompt(synopsis)}\n\n"
        f"Story so far:\n{_story_so_far(bible, meta)}\n"
        + (
            "\nStory AHEAD (from a brief read of later chapters). Use ONLY to keep names,"
            " emphasis and WORLD MECHANICS consistent with where the story goes — e.g."
            " clarify a system rule the way the reference channel pulls mechanics"
            " backward. NEVER reveal or foreshadow future PLOT events:\n"
            + _story_ahead(meta) + "\n"
            if _story_ahead(meta)
            else ""
        )
        + (
            "Narration already written this chapter (continue seamlessly, do not repeat):\n"
            + "\n".join(running_summary[-12:])
            + "\n"
            if running_summary
            else ""
        )
        + f"\nCharacter bible:\n{format_bible_for_prompt(bible)}\n\n"
        f"Outline beats to narrate now + EVIDENCE (one narration per beat_id):\n"
        f"{_cast_context_for_beats(chunk, attribution, bible, cards, words_per_panel=int(get_nested(config, 'script', 'words_per_panel_target', default=14)), max_beat_words=int(get_nested(config, 'script', 'max_beat_words', default=60)))}"
    )


def _sighted_complete_json(
    llm: Any,
    system: str,
    user: str,
    beats: list[ScriptOutlineBeat],
    paths: dict[str, Path] | None,
    config: dict[str, Any],
    max_images: int | None = None,
) -> dict[str, Any]:
    """Narration call with the beats' own panels attached.

    The writer used to compose from TEXT scene cards while the alignment audit checked its
    output against IMAGES — an image-blind author judged by a sighted critic. Everything
    the cards omitted was invisible to the writer and then flagged as invention. Showing
    the writer the panels it is narrating removes that asymmetry; the audit becomes a
    safety net rather than the primary quality mechanism.

    Falls back to the text-only path when panels are unavailable or the provider has no
    labeled-vision support, so nothing depends on this succeeding.
    """
    if paths is None or not get_nested(config, "script", "sighted_narration", default=True):
        return _complete_json(llm, system, user)
    try:
        from manhwa2vid.panels.filter import load_story_panels

        panel_map = {p.id: p for p in load_story_panels(paths)}
        labeled: list[tuple[str, Path]] = []
        for ob in beats:
            for pid in ob.panel_ids:
                panel = panel_map.get(pid)
                if panel is None:
                    continue
                path = paths["root"] / panel.image_path
                if path.exists():
                    labeled.append((f"BEAT {ob.beat_id} / PANEL {pid}:", path))
        if not labeled:
            return _complete_json(llm, system, user)
        # Cap images, not beats — the text evidence still covers every panel. But cap by
        # SUBSAMPLING round-robin across beats, never by truncation: a whole-chapter pass
        # carries every beat's panels, and slicing the head left every beat after the
        # fifth image-blind while the prompt still claimed it could see them.
        if max_images is None:
            max_images = int(get_nested(config, "script", "max_narration_images", default=60))
        if len(labeled) > max_images:
            by_beat: dict[int, list[tuple[str, Path]]] = {}
            for ob in beats:
                by_beat[ob.beat_id] = [x for x in labeled if x[0].startswith(f"BEAT {ob.beat_id} /")]
            kept: list[tuple[str, Path]] = []
            depth = 0
            while len(kept) < max_images and any(len(v) > depth for v in by_beat.values()):
                for bid in by_beat:
                    if len(kept) >= max_images:
                        break
                    if len(by_beat[bid]) > depth:
                        kept.append(by_beat[bid][depth])
                depth += 1
            labeled = [x for x in labeled if x in kept]
        prompt = (
            f"{system}\n\n"
            # VERIFICATION stance, not description. The first wording ("narrate what you
            # can see in them") turned the writer into a captioner — the shipped video
            # read as "a stringed narration of image descriptions": plates on counters,
            # jacket colours, 'with a startled expression'. Images exist to keep the
            # story HONEST (who is present, what actually happens), never to be described.
            "The images below are the panels for these beats, labeled by beat and panel "
            "id. They are for FACT-CHECKING only: use them to confirm who is present and "
            "what actually happens, and to catch anything the text evidence gets wrong. "
            "Do NOT describe the images — no visual inventory, no clothing or object "
            "detail unless the story turns on it. Write the beats as one continuous "
            "story in the voice the system prompt defines.\n\n"
            f"{user}"
        )
        raw = llm.describe_labeled_panels(labeled, prompt)
        # Keep the last raw narration response for forensics — "which field did the
        # model actually return" is undiagnosable once parsing has flattened it.
        try:
            debug_dir = paths["root"] / "debug"
            debug_dir.mkdir(exist_ok=True)
            with (debug_dir / "narration_responses.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"n_beats": len(beats), "raw": raw}) + "\n")
        except Exception:
            pass
        return json.loads(raw)
    except Exception as exc:
        console.print(f"[yellow]Sighted narration unavailable ({type(exc).__name__}) — using text evidence[/]")
        return _complete_json(llm, system, user)


def _run_narration_pass(
    meta: ProjectMeta,
    outline_beats: list[ScriptOutlineBeat],
    hook: str,
    bible: SeriesBible,
    attribution: list[PanelCast],
    synopsis: ChapterSynopsis,
    config: dict[str, Any],
    cards: list[SceneCard] | None = None,
    paths: dict[str, Path] | None = None,
) -> tuple[list[ScriptBeat], list[int], list[int]]:
    """Chunked narration: outline beat_ids/panel_ids are authoritative; the LLM only
    supplies narration text. Returns (beats, beat_ids_missing_after_retry)."""
    template = _load_prompt_template("recap.txt")
    target_wpm = get_nested(config, "script", "target_wpm", default=150)
    commentary = meta.commentary_level or get_nested(config, "script", "commentary_level", default="light")
    genz_level = get_nested(config, "script", "genz_level", default="medium")
    ban = ", ".join(banned_words(config))
    # 0 (the default) = ONE pass over the whole chapter. The gold-standard script was
    # written that way — one context holding every beat — and that is precisely why it
    # never repeated a moment or contradicted itself across beats. Chunking made each
    # group an independent sample: beat 17 could not know beat 18 was about to narrate
    # the same gate entrance, and `running_summary` (a 180-char digest) was too thin to
    # substitute for having actually written the earlier beats.
    configured = int(get_nested(config, "script", "narration_chunk_size", default=0))
    chunk_size = len(outline_beats) if configured <= 0 else max(1, configured)

    # Name the beat that owns the rewind, so the line is spoken WHILE the transition
    # panel is on screen rather than a beat early over the previous scene's art.
    transition_note = ""
    try:
        if paths is not None and paths["scene_story_map_json"].exists():
            tp = str(
                json.loads(paths["scene_story_map_json"].read_text()).get(
                    "last_flashforward_panel", ""
                )
            ).strip()
            if tp:
                owner = next((b.beat_id for b in outline_beats if tp in b.panel_ids), None)
                if owner is not None:
                    transition_note = (
                        f"\n\nTEMPORAL PLACEMENT: the opening flashforward ENDS at panel {tp}, "
                        f"in BEAT {owner}. Close THAT beat by marking the return to the "
                        "present as an image change: ONE short sentence naming where the "
                        "story now is, the way a cut does — no announcement, no "
                        "\"meanwhile\", no explaining that time has moved. Beats before "
                        "it are inside the flashforward and never mention the shift; "
                        "beats after it are simply in the present and never re-announce "
                        "it.\n"
                    )
    except Exception:
        transition_note = ""

    system = template.format(
        target_wpm=target_wpm,
        commentary_level=commentary,
        genz_level=genz_level,
        ban_words=ban,
        naming_priority_rules=naming_priority_rules(bible, config),
    ) + transition_note

    llm = apply_stage_model(get_stage_llm("script", config), "script", config)

    introduced: list[str] = []
    running_summary: list[str] = []
    beats_out: list[ScriptBeat] = []
    missing: list[int] = []
    narration_fallbacks: list[int] = []

    for chunk in _chunked(outline_beats, chunk_size):
        user = _narration_chunk_user(
            meta, chunk, hook, bible, attribution, synopsis, config, cards,
            introduced=introduced, running_summary=running_summary,
            whole_script=len(chunk) == len(outline_beats) and len(chunk) > 1,
        )
        got: dict[int, str] = {}
        got_keys: dict[int, list[str]] = {}
        try:
            data = _sighted_complete_json(llm, system, user, chunk, paths, config)
            for item in data.get("beats", []):
                if isinstance(item, dict) and str(item.get("narration", "")).strip():
                    bid = int(item.get("beat_id", -1))
                    got[bid] = str(item["narration"]).strip()
                    keys = item.get("key_panels")
                    if isinstance(keys, list):
                        got_keys[bid] = [str(k).strip() for k in keys if str(k).strip()]
            returned = sum(1 for v in got_keys.values() if v)
            console.print(f"[dim]key_panels returned on {returned}/{len(chunk)} beats[/]")
        except Exception as exc:
            console.print(f"[yellow]Narration chunk failed, retrying per beat:[/] {exc}")

        for ob in chunk:
            narration = got.get(ob.beat_id, "")
            if not narration:
                narration = _retry_single_beat(
                    llm, system, meta, ob, hook, bible, attribution, synopsis, config, cards,
                    introduced=introduced, running_summary=running_summary, paths=paths,
                )
            if not narration:
                # Last resort: the outline's own plot_beat, which is deterministic and
                # panel-grounded. Losing ONE beat failed the whole chapter at the
                # beat-conservation gate — a whole re-run (and a full vision pass) for a
                # single empty completion. Terse-but-true beats dropping the beat, and
                # the beat is still recorded as a fallback so it shows up in QA.
                from manhwa2vid.script.lint import local_sanitize_narration

                narration = local_sanitize_narration(
                    (ob.plot_beat or "").split("/ CLOSER")[0].strip()
                )
                if narration:
                    narration_fallbacks.append(ob.beat_id)
            if not narration:
                missing.append(ob.beat_id)
                continue
            beat = ScriptBeat(
                beat_id=ob.beat_id,
                panel_ids=list(ob.panel_ids),  # authoritative — the LLM cannot drift panels
                narration=narration,
                character_ids=list(ob.character_ids),
                # Only ids actually in this beat count; the model echoes ids and a stray
                # one must not pin a panel from another beat.
                key_panel_ids=[k for k in got_keys.get(ob.beat_id, []) if k in ob.panel_ids],
            )
            if got_keys.get(ob.beat_id) and not beat.key_panel_ids:
                console.print(
                    f"[yellow]beat {ob.beat_id}: all {len(got_keys[ob.beat_id])} key ids "
                    f"failed containment (model echoed foreign ids)[/]"
                )
            beats_out.append(beat)
            running_summary.append(f"Beat {ob.beat_id}: {narration[:180]}")
            for name in _bible_names_in_text(narration, bible):
                if name not in introduced:
                    introduced.append(name)

    return beats_out, missing, narration_fallbacks


def _retry_single_beat(
    llm: Any,
    system: str,
    meta: ProjectMeta,
    beat: ScriptOutlineBeat,
    hook: str,
    bible: SeriesBible,
    attribution: list[PanelCast],
    synopsis: ChapterSynopsis,
    config: dict[str, Any],
    cards: list[SceneCard] | None,
    *,
    introduced: list[str],
    running_summary: list[str],
    paths: dict[str, Path] | None = None,
) -> str:
    """Regenerate exactly one beat. Two attempts; '' if both fail (caller gates on it)."""
    for attempt in range(2):
        try:
            user = _narration_chunk_user(
                meta, [beat], hook, bible, attribution, synopsis, config, cards,
                introduced=introduced, running_summary=running_summary,
            )
            data = _sighted_complete_json(llm, system, user, [beat], paths, config)
            for item in data.get("beats", []):
                if isinstance(item, dict) and str(item.get("narration", "")).strip():
                    return str(item["narration"]).strip()
        except Exception as exc:
            console.print(f"[yellow]Single-beat retry {attempt + 1} failed for beat {beat.beat_id}:[/] {exc}")
    return ""


def generate_script(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> ScriptDraft:
    if paths["script_draft"].exists() and not force:
        console.print(f"[dim]Using existing script draft[/] → {paths['script_draft']}")
        return load_script_beats(paths)

    from manhwa2vid.script.grounding import configure_grounding_keywords

    glossary: dict = {}
    if paths["glossary"].exists():
        try:
            glossary = json.loads(paths["glossary"].read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            glossary = {}
    configure_grounding_keywords(config, glossary)

    if not paths["scene_enriched_json"].exists() or force:
        run_cast_linking(meta, paths, config, force=force)

    cards = load_story_scene_cards(paths)
    if not cards:
        scene_data = json.loads(paths["scene_json"].read_text())
        cards = [SceneCard.model_validate(s) for s in scene_data]

    bible = load_series_bible(meta.series_slug, meta.title)

    attribution: list[PanelCast] = []
    if paths["cast_attribution_json"].exists():
        attribution = [
            PanelCast.model_validate(a)
            for a in json.loads(paths["cast_attribution_json"].read_text(encoding="utf-8"))
        ]

    synopsis = generate_chapter_synopsis(
        meta,
        cards,
        bible,
        attribution,
        config,
        out_path=paths["script_synopsis_json"],
    )
    # Reload bible after synopsis sticky-name merges
    bible = load_series_bible(meta.series_slug, meta.title)

    hook, outline_beats = _run_outline_pass(meta, cards, bible, synopsis, config, paths)
    outline_beats = _mark_closer_beat(outline_beats, synopsis)
    save_json(
        paths["script_outline_json"],
        {"hook": hook, "beats": [b.model_dump(mode="json") for b in outline_beats]},
    )

    beats, missing_beats, narration_fallbacks = _run_narration_pass(
        meta, outline_beats, hook, bible, attribution, synopsis, config, cards, paths=paths
    )

    from manhwa2vid.qa import QAReport, enforce, qa_forced

    report = QAReport(stage="script")
    outline_ids = [b.beat_id for b in outline_beats]
    script_ids = [b.beat_id for b in beats]
    report.add(
        "narration-complete",
        "warn" if narration_fallbacks else True,
        f"beat(s) {narration_fallbacks} fell back to outline text (empty completion)"
        if narration_fallbacks else "",
        fallbacks=narration_fallbacks,
    )
    empty_beats = [b.beat_id for b in beats if not b.narration.strip()]
    report.add(
        "beats-nonempty",
        not empty_beats,
        f"beat(s) with EMPTY narration: {empty_beats} — these would render as silent "
        "dead air" if empty_beats else "",
        empty=empty_beats,
    )
    report.add(
        "beat-conservation",
        not missing_beats and script_ids == outline_ids,
        f"outline={len(outline_ids)} script={len(script_ids)} missing={missing_beats}"
        if missing_beats or script_ids != outline_ids else "",
        outline_ids=outline_ids, script_ids=script_ids, missing=missing_beats,
    )

    # A beat carrying far more panels than its peers is the signature of a collapsed
    # outline: the reconciler re-homes every orphaned panel onto the survivors, and the
    # result is one beat narrating half the chapter (its panels then dwell for seconds
    # each with nothing said about them). beat-conservation cannot see this — it compares
    # outline to script AFTER the collapse already happened.
    panel_counts = {b.beat_id: len(b.panel_ids) for b in beats}
    if panel_counts:
        median = sorted(panel_counts.values())[len(panel_counts) // 2]
        bloated = {bid: n for bid, n in panel_counts.items() if n > max(8, median * 3)}
    else:
        bloated = {}
    report.add(
        "beat-panel-balance",
        not bloated,
        f"beat(s) carry far more panels than the median ({median if panel_counts else 0}): "
        f"{bloated}" if bloated else "",
        bloated={str(k): v for k, v in bloated.items()},
    )

    # Universe = the story panel INVENTORY (panels.story.json), never the scene cards:
    # a panel the scene stage dropped must count as uncovered here, not vanish silently.
    from manhwa2vid.panels.filter import load_story_panels

    all_panels = sorted({p.id for p in load_story_panels(paths)}, key=_panel_sort_key)
    covered = _covered_panel_ids(beats)
    rehomed = len(all_panels) - len(covered & set(all_panels))
    if covered != set(all_panels) and rehomed:
        beats = _attach_missing_panels_to_beats(all_panels, beats)
    report.add(
        "panel-conservation",
        True if rehomed == 0 else ("warn" if rehomed <= max(1, len(all_panels) // 10) else False),
        f"{rehomed} of {len(all_panels)} story-inventory panel(s) re-homed to nearest beat "
        "(includes any the scene stage dropped)" if rehomed else "",
        rehomed=rehomed, total=len(all_panels),
    )

    hook_overlap = _token_overlap(hook, beats[0].narration if beats else "")
    report.add(
        "hook-dedup",
        True if hook_overlap <= 0.6 else "warn",
        f"beat 1 repeats {hook_overlap:.0%} of the hook" if hook_overlap > 0.6 else "",
        overlap=round(hook_overlap, 2),
    )
    closer = next((b for b in outline_beats if b.is_closer), None)
    # The chapter's final panels are its chosen ending; their content must reach the
    # last beats. Positional, not series-specific — see grounding.inject_closer_evidence.
    tail_terms = _closing_panel_terms(cards, tail=3)
    late_text = beats[-1].narration.lower() if beats else ""
    covered = [t for t in tail_terms if t in late_text]
    report.add(
        "reveal-coverage",
        bool(covered) if tail_terms else True,
        "" if not tail_terms or covered else (
            f"none of the final panels' content ({', '.join(sorted(tail_terms)[:6])}) "
            "appears in the last two beats — the ending was compressed away"
        ),
    )
    report.add("closer-present", closer is not None and bool(beats) and beats[-1].beat_id == (closer.beat_id if closer else -1),
               "" if closer else "no closer beat in outline")
    enforce(report, paths["root"], force=qa_forced(config))

    beats = lint_and_rewrite_script(
        beats,
        bible,
        paths["cast_attribution_json"],
        config,
        scene_cards=cards,
    )

    if get_nested(config, "script", "verify_alignment", default=True):
        from manhwa2vid.panels.filter import load_story_panels
        from manhwa2vid.script.lint import rewrite_beat
        from manhwa2vid.script.verify import audit_frame_alignment

        panel_map = {p.id: p for p in load_story_panels(paths)}
        audit, major = audit_frame_alignment(beats, panel_map, paths["root"], config, bible=bible)
        if major:
            console.print(f"[yellow]Alignment audit:[/] rewriting {len(major)} beat(s) with major unsupported claims")
            fixed: list[ScriptBeat] = []
            for beat in beats:
                if beat.beat_id in major:
                    issues = [f"unsupported claim: {c}" for c in major[beat.beat_id]]
                    new_text = rewrite_beat(
                        beat, bible, attribution, config, issues=issues, scene_cards=cards
                    )
                    fixed.append(beat.model_copy(update={"narration": new_text}))
                else:
                    fixed.append(beat)
            beats = fixed

            # Converge: re-audit only the rewritten beats. A beat whose major claims
            # SURVIVE its rewrite falls back to the deterministic outline plot_beat —
            # terse but panel-grounded always beats fluent but invented. Without this
            # floor the audit's findings never reliably reached the shipped narration.
            rewritten = [b for b in beats if b.beat_id in major]
            _re_report, still_major = audit_frame_alignment(rewritten, panel_map, paths["root"], config, bible=bible)
            if still_major:
                from manhwa2vid.script.lint import local_sanitize_narration, rotate_protagonist_name

                plot_by_id = {ob.beat_id: ob.plot_beat for ob in outline_beats}
                console.print(
                    f"[yellow]Alignment audit:[/] {len(still_major)} beat(s) still unsupported after "
                    f"rewrite — falling back to grounded outline text: {sorted(still_major)}"
                )
                fallbacks: list[ScriptBeat] = []
                for beat in beats:
                    if beat.beat_id in still_major and beat.beat_id in plot_by_id:
                        grounded = plot_by_id[beat.beat_id].split("/ CLOSER")[0].strip()
                        grounded = rotate_protagonist_name(local_sanitize_narration(grounded), bible)
                        # A continuity beat can carry an EMPTY plot_beat; replacing real
                        # narration with '' shipped a silent beat once. Unverified prose
                        # beats dead air — keep the rewrite when the fallback is empty.
                        if grounded:
                            fallbacks.append(beat.model_copy(update={"narration": grounded}))
                        else:
                            fallbacks.append(beat)
                    else:
                        fallbacks.append(beat)
                beats = fallbacks
            audit.add(
                "grounded-fallback",
                "warn" if still_major else True,
                f"beat(s) {sorted(still_major)} replaced with outline text" if still_major else "",
                beats=sorted(still_major),
            )
            # The fallback is a per-beat safety net; when it authors a large FRACTION of
            # the script, the run has failed and must say so. On the second title tested
            # 13 of 18 beats shipped as outline text behind an all-green report — the
            # audit was flagging honest whole-beat summarization at high panel density,
            # and the "safety" path quietly became the writer.
            max_frac = float(get_nested(config, "qa", "max_fallback_fraction", default=0.34))
            frac = len(still_major) / max(1, len(beats))
            audit.add(
                "fallback-fraction",
                frac <= max_frac,
                f"{len(still_major)}/{len(beats)} beats ({frac:.0%}) shipped from the fallback path"
                f" — over the {max_frac:.0%} budget; the script is not narration" if frac > max_frac else "",
            )
        enforce(audit, paths["root"], force=qa_forced(config))

    # FINAL deterministic polish — after every LLM pass. Audit rewrites run after the
    # lint pipeline and happily reintroduce appearance appositives and stray name forms
    # (beat 7 kept "a man with short grey hair and a blue jacket" through one whole
    # iteration because the strip ran before the rewrite that re-added it). Nothing that
    # generates text may run after this block.
    from manhwa2vid.script.lint import (
        enforce_mc_name_budget,
        fix_pronoun_case as _fix_case,
        strip_caption_sentences,
        dedupe_intra_beat_sentences,
        repair_malformed_openings,
        strip_duplicate_transitions,
        strip_repeated_appositives,
        trim_overlong_beats,
        repair_truncated_sentences,
        repair_subject_comma,
        strip_internal_labels,
        lock_transition_line,
        strip_appearance_descriptors,
        dedupe_cross_beat_sentences,
        strip_trailing_closer_sentence,
        derive_key_panels,
    )

    beats = strip_repeated_appositives(beats, bible)
    beats = strip_caption_sentences(beats, bible)
    transition_panel = ""
    transition_line = ""
    try:
        if paths["scene_story_map_json"].exists():
            story_map = json.loads(paths["scene_story_map_json"].read_text())
            transition_panel = str(story_map.get("last_flashforward_panel", "")).strip()
            # Written once by the whole-chapter read; locked here so the narration pass
            # cannot embellish the most audible line in the recap.
            transition_line = str(story_map.get("return_to_present_line", "")).strip()
    except Exception:
        transition_panel = ""
        transition_line = ""
    beats = strip_duplicate_transitions(beats, transition_panel)
    beats = lock_transition_line(beats, transition_panel, config, transition_line)
    beats = repair_malformed_openings(beats)
    beats = repair_subject_comma(beats)
    beats = repair_truncated_sentences(beats)
    beats = strip_internal_labels(beats, bible)
    beats = strip_appearance_descriptors(beats, bible)
    beats = dedupe_intra_beat_sentences(beats)
    beats = dedupe_cross_beat_sentences(beats)
    beats = trim_overlong_beats(beats, config)
    beats = derive_key_panels(beats, cards)
    beats = strip_trailing_closer_sentence(beats)
    beats = enforce_mc_name_budget(beats, bible, config)

    from manhwa2vid.script.lint import lint_malformed_opening

    final_report = QAReport(stage="script-final")
    malformed = sorted(lint_malformed_opening(beats))
    final_report.add(
        "beats-wellformed",
        not malformed,
        f"beat(s) starting mid-sentence after repair: {malformed}" if malformed else "",
        malformed=malformed,
    )
    enforce(final_report, paths["root"], force=qa_forced(config))

    from manhwa2vid.script.scorecard import score_script

    enforce(score_script(beats, bible, config), paths["root"], force=qa_forced(config))

    draft = ScriptDraft(
        title=meta.title,
        chapters=meta.chapters,
        beats=beats,
        hook=hook,
    )

    save_json(paths["script_json"], draft)
    paths["script_draft"].write_text(_beats_to_markdown(draft), encoding="utf-8")
    console.print(f"[green]Script draft written[/] → {paths['script_draft']} ({len(beats)} beats)")

    try:
        from manhwa2vid.review.storyboard import write_storyboard

        board = write_storyboard(paths, draft)
        console.print(f"[dim]Storyboard for review →[/] {board}")
    except Exception as exc:  # a review artifact must never block the stage
        console.print(f"[yellow]Storyboard generation failed:[/] {type(exc).__name__}: {exc}")

    return draft
