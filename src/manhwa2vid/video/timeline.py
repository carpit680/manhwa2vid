"""Panel ↔ narration timeline alignment."""

from __future__ import annotations

import json
import re
import wave
from pathlib import Path
from typing import Any

from manhwa2vid.config import get_nested
from manhwa2vid.models import Panel, ScriptBeat, Timeline, TimelineEntry


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


def _mp3_duration_fallback(path: Path) -> float:
    try:
        from mutagen.mp3 import MP3

        return MP3(str(path)).info.length
    except Exception:
        return max(3.0, len(path.read_bytes()) / 16000)


def audio_duration(path: Path) -> float:
    if path.suffix.lower() == ".wav":
        return _wav_duration(path)
    if path.suffix.lower() == ".mp3":
        return _mp3_duration_fallback(path)
    return 3.0


def panel_salience(
    cards: list[Any],
    attribution: list[Any] | None = None,
) -> dict[str, float]:
    """Deterministic per-panel importance from evidence that already exists.

    Used to rank panels a beat's audio cannot afford to show in full. Signals, by
    weight: on-panel dialogue (the story's engine) > people present > nothing. Position
    bonuses (first/last of beat) are applied at selection time, not here, because the
    same panel can sit in different positions in different beats.
    """
    scores: dict[str, float] = {}
    for card in cards or []:
        has_dialogue = bool(getattr(card, "source_text", "") or (card.get("source_text") if isinstance(card, dict) else ""))
        pids = getattr(card, "panel_ids", None) or (card.get("panel_ids") if isinstance(card, dict) else []) or []
        for pid in pids:
            scores[pid] = max(scores.get(pid, 0.0), 3.0 if has_dialogue else 0.0)
    for row in attribution or []:
        people = getattr(row, "people", None) or (row.get("people") if isinstance(row, dict) else []) or []
        pid = getattr(row, "panel_id", None) or (row.get("panel_id") if isinstance(row, dict) else "")
        if pid:
            scores[pid] = scores.get(pid, 0.0) + min(len(people), 2) * 0.75
    return scores


def select_panels_for_beat(
    panel_ids: list[str],
    key_ids: list[str],
    salience: dict[str, float],
    audio_duration_s: float,
    target_s: float,
    drop_floor: float,
    *,
    keep_last: bool = False,
) -> list[str]:
    """Importance-first panel selection under a pace budget.

    The reference channel shows roughly half the panels at ~2s each; which half is an
    editorial judgment, not a stride. Selection order:
      1. KEY panels — the ones the writer said its narration depends on — are always
         shown, even past the pace budget (a fight or an emotional run may simply need
         more panels; dwell compresses toward `drop_floor` instead of dropping them).
      2. Remaining pace-budget slots fill by salience (dialogue > people > position).
      3. Reading order is always preserved; a beat never goes below ONE panel — an empty
         beat would drop its narration audio from the mix and desync everything after.
    The absolute `drop_floor` cap still applies as the unreadability limit, keys first.
    """
    if not panel_ids:
        return panel_ids
    affordable = max(1, round(audio_duration_s / max(target_s, 0.1)))
    hard_cap = max(1, int(audio_duration_s // drop_floor)) if drop_floor > 0 else len(panel_ids)

    def _pos_bonus(pid: str) -> float:
        if pid == panel_ids[0] or pid == panel_ids[-1]:
            return 1.0
        return 0.0

    chosen = {p for p in panel_ids if p in set(key_ids)}
    if keep_last:
        chosen.add(panel_ids[-1])
    if not chosen:
        chosen.add(max(panel_ids, key=lambda p: (salience.get(p, 0.0) + _pos_bonus(p))))

    remaining = sorted(
        (p for p in panel_ids if p not in chosen),
        key=lambda p: -(salience.get(p, 0.0) + _pos_bonus(p)),
    )
    for pid in remaining:
        if len(chosen) >= affordable:
            break
        chosen.add(pid)

    if len(chosen) > hard_cap:
        keys_first = [p for p in panel_ids if p in chosen and p in set(key_ids)][:hard_cap]
        if keep_last and panel_ids[-1] not in keys_first and len(keys_first) < hard_cap:
            keys_first.append(panel_ids[-1])
        others = sorted(
            (p for p in chosen if p not in keys_first),
            key=lambda p: -(salience.get(p, 0.0) + _pos_bonus(p)),
        )
        chosen = set(keys_first) | set(others[: max(0, hard_cap - len(keys_first))])

    return [p for p in panel_ids if p in chosen]


def budget_panels_for_beat(
    panel_ids: list[str],
    audio_duration_s: float,
    drop_floor: float,
    key_panel_ids: list[str] | None = None,
) -> list[str]:
    """
    Drop panels a beat's audio cannot show for even `drop_floor` seconds each.

    split_beat_durations never extends past the audio, so a beat holding more panels than
    its narration can pay for silently starves all of them (18 panels over 7s of audio =
    0.4s each). Showing fewer panels for a readable duration beats flashing all of them.

    This floor is deliberately lower than `min_panel_seconds`: mild compression (a panel
    getting 1.5s instead of 2s) is fine and must not cost the viewer a panel. Only
    genuinely unreadable dwells trigger a drop.

    `key_panel_ids` are kept ahead of their neighbours. This branch runs whenever scene
    salience is unavailable, and salience loading is wrapped in a bare `except` in
    tts/engine.py — so on any project without enriched scene cards the writer's explicit
    "this panel is load-bearing" marking was silently thrown away and replaced by a blind
    positional stride. The story-first architecture has no scene cards at all, which
    would make that the ONLY path.
    """
    if not panel_ids or drop_floor <= 0:
        return panel_ids

    affordable = max(1, int(audio_duration_s // drop_floor))
    if len(panel_ids) <= affordable:
        return panel_ids

    keys = [p for p in (key_panel_ids or []) if p in panel_ids]
    if affordable == 1:
        return [keys[0]] if keys else [panel_ids[0]]

    chosen: list[str] = []
    if keys:
        # Keys first (capped so they cannot crowd out coverage entirely), then a stride
        # over the rest; finally restore the beat's own order, which IS presentation
        # order — never global reading order.
        for pid in keys[:affordable]:
            chosen.append(pid)
        rest = [p for p in panel_ids if p not in chosen]
        remaining = affordable - len(chosen)
        if remaining > 0 and rest:
            step = max(1, len(rest) / remaining)
            for i in range(remaining):
                idx = min(len(rest) - 1, round(i * step))
                if rest[idx] not in chosen:
                    chosen.append(rest[idx])
        return [p for p in panel_ids if p in chosen]

    step = (len(panel_ids) - 1) / (affordable - 1)
    for i in range(affordable):
        pid = panel_ids[round(i * step)]
        if pid not in chosen:
            chosen.append(pid)
    return chosen


from manhwa2vid.script.sentences import SENTENCE_SPLIT_RE as _SENTENCE_SPLIT


def _subdivide_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Split multi-sentence segments into per-sentence entries by word proration.

    Kokoro's chunks are NOT sentences: it splits on an internal token limit, so one
    measured chunk carried nine sentences and 22 seconds, and a beat that fit in a
    single chunk got no weighting at all (6 of 16 FP beats stayed uniform). The chunk
    boundary timings are exact; inside a chunk, word count is the best available
    estimate — exact at the seams, prorated within.
    """
    out: list[dict[str, Any]] = []
    for seg in segments:
        text = str(seg.get("text") or "")
        seconds = max(float(seg.get("seconds", 0.0)), 0.0)
        sentences = [x.strip() for x in _SENTENCE_SPLIT.split(text.strip()) if x.strip()]
        if len(sentences) <= 1 or seconds <= 0:
            out.append(seg)
            continue
        total_words = sum(len(x.split()) for x in sentences) or 1
        for sentence in sentences:
            out.append(
                {
                    "text": sentence,
                    "seconds": seconds * len(sentence.split()) / total_words,
                }
            )
    return out


def panel_weights_from_segments(
    segments: list[dict[str, Any]], n_panels: int
) -> list[float] | None:
    """Turn per-sentence timings into per-panel dwell weights.

    Panels are already in presentation order and sentences in spoken order, so the
    assignment is contiguous: each sentence owns a run of panels sized pro-rata by its
    share of the beat's audio, and every panel in that run splits the sentence's seconds
    evenly. The result: the screen holds on a moment for as long as the narrator is
    talking about it, and short punch sentences flick past — which is the entire ask.

    Deliberately NOT content-matching sentences to panels semantically: the aligner
    already chose and ordered these panels for this text, so position carries the
    correspondence, and a fuzzy re-match here could only disagree with it.
    """
    segments = _subdivide_segments(segments)
    seconds = [max(float(seg.get("seconds", 0.0)), 0.0) for seg in segments]
    total = sum(seconds)
    if n_panels <= 0 or total <= 0:
        return None
    if len(seconds) == 1:
        return None  # one sentence — even split IS the right answer

    # Sentence i owns panels [bounds[i], bounds[i+1]) — cumulative pro-rata. A tiny
    # sentence may round to an empty run; handled below.
    bounds = [0]
    acc = 0.0
    for sec in seconds:
        acc += sec
        bounds.append(round(acc / total * n_panels))
    bounds[-1] = n_panels

    weights = [0.0] * n_panels
    for i, sec in enumerate(seconds):
        lo, hi = bounds[i], bounds[i + 1]
        if hi <= lo:
            # Sentence too short to own a panel: its time rides on the panel at the
            # boundary so the audio position still matches the picture.
            idx = min(max(lo, 0), n_panels - 1)
            weights[idx] += sec
            continue
        share = sec / (hi - lo)
        for j in range(lo, hi):
            weights[j] += share
    return weights if sum(weights) > 0 else None


def load_beat_segments(audio_dir: Path, beat_id: int) -> list[dict[str, Any]] | None:
    path = audio_dir / f"beat_{beat_id:03d}.segments.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) and data else None
    except Exception:
        return None


def _panel_sort_key(panel_id: str) -> tuple[int, int]:
    import re

    m = re.match(r"p(\d+)_(\d+)", panel_id, re.I)
    return (int(m.group(1)), int(m.group(2))) if m else (9999, 9999)


def _resolve_panels_for_beat(beat: ScriptBeat, panel_map: dict[str, Panel], all_ids: list[str]) -> list[str]:
    ids = [pid for pid in beat.panel_ids if pid in panel_map]
    if ids:
        return ids
    if not all_ids:
        return []
    # All of this beat's panels were excluded (e.g. blank slivers): show the NEAREST
    # surviving panel, not the chapter's first — the audio still plays, so the visual
    # should at least belong to the same neighborhood of the story.
    if beat.panel_ids:
        want = min(_panel_sort_key(pid) for pid in beat.panel_ids)
        nearest = min(
            all_ids,
            key=lambda pid: (
                abs(_panel_sort_key(pid)[0] - want[0]) * 100
                + abs(_panel_sort_key(pid)[1] - want[1])
            ),
        )
        return [nearest]
    return all_ids[:1]


def split_beat_durations(
    audio_duration_s: float,
    n_panels: int,
    *,
    min_sec: float,
    max_sec: float,
    weights: list[float] | None = None,
) -> list[float]:
    """
    Split beat audio across panels so sum(durations) == audio_duration exactly.

    `weights` makes dwell follow the NARRATION: a panel's share of the beat's audio is
    its share of the weight mass (in practice, the measured seconds of the sentence it
    illustrates). Without weights the split is even — which is what made every video a
    metronome: measured before this existed, 16/16 FP beats and 34/38 SL beats gave
    every panel a byte-identical dwell, so the picture never lingered on what was being
    said. The cap/lift/sum-lock machinery below is weight-agnostic.

    If even/weighted split exceeds max_sec, cap at max and redistribute remainder to
    other panels (still summing to audio). Never extend past audio to satisfy min_sec —
    borrow from longer siblings when possible; otherwise allow panels shorter than
    min_sec so A/V stay locked.
    """
    if n_panels <= 0:
        return []
    if n_panels == 1:
        return [audio_duration_s]

    if weights and len(weights) == n_panels and sum(weights) > 0:
        mass = sum(weights)
        raw = [audio_duration_s * max(w, 0.0) / mass for w in weights]
    else:
        raw = [audio_duration_s / n_panels] * n_panels
    # Cap highs, then redistribute leftover to panels still under max
    for _ in range(n_panels + 2):
        over = [(i, d - max_sec) for i, d in enumerate(raw) if d > max_sec + 1e-9]
        if not over:
            break
        leftover = sum(extra for _, extra in over)
        for i, _ in over:
            raw[i] = max_sec
        receivers = [i for i, d in enumerate(raw) if d < max_sec - 1e-9]
        if not receivers:
            # All capped — scale down proportionally to fit audio
            total = sum(raw)
            if total > 0:
                scale = audio_duration_s / total
                raw = [d * scale for d in raw]
            break
        add = leftover / len(receivers)
        for i in receivers:
            raw[i] += add

    # Try to lift panels below min_sec by borrowing from panels above min
    for _ in range(n_panels + 2):
        short = [i for i, d in enumerate(raw) if d + 1e-9 < min_sec]
        if not short:
            break
        donors = [i for i, d in enumerate(raw) if d > min_sec + 1e-9]
        if not donors:
            break
        need = sum(min_sec - raw[i] for i in short)
        spare = sum(raw[i] - min_sec for i in donors)
        if spare <= 1e-9:
            break
        take = min(need, spare)
        for i in short:
            deficit = min_sec - raw[i]
            if deficit <= 0:
                continue
            share = take * (deficit / need) if need else 0
            raw[i] += share
        for i in donors:
            give = take * ((raw[i] - min_sec) / spare) if spare else 0
            raw[i] -= give

    # Final exact sum lock (floating point)
    total = sum(raw)
    if total > 0 and abs(total - audio_duration_s) > 1e-6:
        scale = audio_duration_s / total
        raw = [d * scale for d in raw]
    # Fix residual on last panel
    if raw:
        raw[-1] = audio_duration_s - sum(raw[:-1])
    return raw


def build_timeline(
    beats: list[ScriptBeat],
    panels: list[Panel],
    audio_dir: Path,
    config: dict[str, Any],
    salience: dict[str, float] | None = None,
    shot_plan: dict[int, list[tuple[str, float]]] | None = None,
) -> Timeline:
    min_sec = float(get_nested(config, "video", "min_panel_seconds", default=2.0))
    max_sec = float(get_nested(config, "video", "max_panel_seconds", default=8.0))
    fps = int(get_nested(config, "video", "fps", default=30))
    drop_floor = float(get_nested(config, "video", "panel_drop_floor_seconds", default=1.0))
    target_s = float(get_nested(config, "video", "target_panel_seconds", default=2.5))

    panel_map = {p.id: p for p in panels}
    all_ids = [p.id for p in panels]
    entries: list[TimelineEntry] = []
    cursor = 0.0
    dropped = 0

    for beat in beats:
        audio_path = audio_dir / f"beat_{beat.beat_id:03d}.wav"
        if not audio_path.exists():
            audio_path = audio_dir / f"beat_{beat.beat_id:03d}.mp3"
        duration = audio_duration(audio_path) if audio_path.exists() else 5.0

        panel_ids = _resolve_panels_for_beat(beat, panel_map, all_ids)
        if not panel_ids:
            continue

        # A shot list, when the matcher produced one, decides BOTH what is on screen and
        # for how long: each sentence's measured seconds go to the panels that actually
        # depict it. Without it, panels are apportioned by airtime alone — which measured
        # 86% (FP) / 93% (SL) wrong-panel rate, because even apportionment desynchronises
        # from narration that compresses.
        planned = (shot_plan or {}).get(beat.beat_id)
        if planned:
            planned = [(pid, sec) for pid, sec in planned if pid in panel_map]
        if planned:
            panel_ids = [pid for pid, _sec in planned]
            weights = [sec for _pid, sec in planned]
            segs = split_beat_durations(
                duration, len(panel_ids), min_sec=min_sec, max_sec=max_sec, weights=weights
            )
            for pid, seg in zip(panel_ids, segs):
                panel = panel_map[pid]
                entries.append(
                    TimelineEntry(
                        panel_id=pid,
                        panel_path=panel.image_path,
                        start=cursor,
                        end=cursor + seg,
                        duration=seg,
                        beat_id=beat.beat_id,
                        # `audio_file` is how _mix_audio finds the narration at all: it
                        # collects the distinct files off the entries. Omitting it here
                        # produced a completely SILENT render, and nothing failed —
                        # _mix_audio takes an empty list as "no narration" and copies the
                        # video through. Any new TimelineEntry construction must set it.
                        audio_file=(
                            str(audio_path.relative_to(audio_dir.parent))
                            if audio_path.exists()
                            else None
                        ),
                        subtitle_text=beat.narration,
                    )
                )
                cursor += seg
            continue

        if salience is not None:
            # Importance-first curation: writer-marked key panels always shown, the rest
            # by salience under the pace budget. The last beat's final panel is pinned —
            # the chapter's reveal lives there by construction.
            budgeted = select_panels_for_beat(
                panel_ids,
                beat.key_panel_ids,
                salience,
                duration,
                target_s,
                drop_floor,
                keep_last=beat.beat_id == beats[-1].beat_id,
            )
        else:
            budgeted = budget_panels_for_beat(
                panel_ids, duration, drop_floor, beat.key_panel_ids
            )
        dropped += len(panel_ids) - len(budgeted)
        panel_ids = budgeted

        weights = panel_weights_from_segments(
            load_beat_segments(audio_dir, beat.beat_id) or [], len(panel_ids)
        )
        segs = split_beat_durations(
            duration, len(panel_ids), min_sec=min_sec, max_sec=max_sec, weights=weights
        )
        for pid, seg in zip(panel_ids, segs):
            panel = panel_map[pid]
            entries.append(
                TimelineEntry(
                    panel_id=pid,
                    panel_path=panel.image_path,
                    start=cursor,
                    end=cursor + seg,
                    duration=seg,
                    audio_file=str(audio_path.relative_to(audio_dir.parent)) if audio_path.exists() else None,
                    subtitle_text=beat.narration,
                    beat_id=beat.beat_id,
                )
            )
            cursor += seg

    if dropped:
        from rich.console import Console

        Console().print(
            f"[yellow]Panel budget:[/] dropped {dropped} panel(s) whose beats could not afford "
            f"{drop_floor:.1f}s each — {len(entries)} shown"
        )

    return Timeline(entries=entries, total_duration=cursor, fps=fps, dropped_panels=dropped)
