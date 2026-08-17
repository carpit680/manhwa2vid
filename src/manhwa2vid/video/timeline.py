"""Panel ↔ narration timeline alignment."""

from __future__ import annotations

import json
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


def budget_panels_for_beat(
    panel_ids: list[str],
    audio_duration_s: float,
    drop_floor: float,
) -> list[str]:
    """
    Drop panels a beat's audio cannot show for even `drop_floor` seconds each.

    split_beat_durations never extends past the audio, so a beat holding more panels than
    its narration can pay for silently starves all of them (18 panels over 7s of audio =
    0.4s each). Showing fewer panels for a readable duration beats flashing all of them.

    This floor is deliberately lower than `min_panel_seconds`: mild compression (a panel
    getting 1.5s instead of 2s) is fine and must not cost the viewer a panel. Only
    genuinely unreadable dwells trigger a drop.
    """
    if not panel_ids or drop_floor <= 0:
        return panel_ids

    affordable = max(1, int(audio_duration_s // drop_floor))
    if len(panel_ids) <= affordable:
        return panel_ids
    if affordable == 1:
        return [panel_ids[0]]

    step = (len(panel_ids) - 1) / (affordable - 1)
    chosen: list[str] = []
    for i in range(affordable):
        pid = panel_ids[round(i * step)]
        if pid not in chosen:
            chosen.append(pid)
    return chosen


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


def split_beat_durations(audio_duration_s: float, n_panels: int, *, min_sec: float, max_sec: float) -> list[float]:
    """
    Split beat audio across panels so sum(durations) == audio_duration exactly.

    Prefer even split. If even split exceeds max_sec, cap at max and redistribute
    remainder to other panels (still summing to audio). Never extend past audio
    to satisfy min_sec — borrow from longer siblings when possible; otherwise
    allow panels shorter than min_sec so A/V stay locked.
    """
    if n_panels <= 0:
        return []
    if n_panels == 1:
        return [audio_duration_s]

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
) -> Timeline:
    min_sec = float(get_nested(config, "video", "min_panel_seconds", default=2.0))
    max_sec = float(get_nested(config, "video", "max_panel_seconds", default=8.0))
    fps = int(get_nested(config, "video", "fps", default=30))
    drop_floor = float(get_nested(config, "video", "panel_drop_floor_seconds", default=1.0))

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

        budgeted = budget_panels_for_beat(panel_ids, duration, drop_floor)
        dropped += len(panel_ids) - len(budgeted)
        panel_ids = budgeted

        segs = split_beat_durations(duration, len(panel_ids), min_sec=min_sec, max_sec=max_sec)
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
