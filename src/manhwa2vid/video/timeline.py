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


def _resolve_panels_for_beat(beat: ScriptBeat, panel_map: dict[str, Panel], all_ids: list[str]) -> list[str]:
    ids = [pid for pid in beat.panel_ids if pid in panel_map]
    if ids:
        return ids
    return all_ids[:1]


def build_timeline(
    beats: list[ScriptBeat],
    panels: list[Panel],
    audio_dir: Path,
    config: dict[str, Any],
) -> Timeline:
    min_sec = float(get_nested(config, "video", "min_panel_seconds", default=2.0))
    max_sec = float(get_nested(config, "video", "max_panel_seconds", default=8.0))
    fps = int(get_nested(config, "video", "fps", default=30))

    panel_map = {p.id: p for p in panels}
    all_ids = [p.id for p in panels]
    entries: list[TimelineEntry] = []
    cursor = 0.0

    for beat in beats:
        audio_path = audio_dir / f"beat_{beat.beat_id:03d}.wav"
        if not audio_path.exists():
            audio_path = audio_dir / f"beat_{beat.beat_id:03d}.mp3"
        duration = audio_duration(audio_path) if audio_path.exists() else 5.0

        panel_ids = _resolve_panels_for_beat(beat, panel_map, all_ids)
        if not panel_ids:
            continue

        per_panel = duration / len(panel_ids)
        raw_durations = [per_panel] * len(panel_ids)

        scale = duration / sum(raw_durations) if raw_durations else 1.0
        for pid, raw in zip(panel_ids, raw_durations):
            seg = max(min_sec, min(max_sec, raw * scale))
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

    return Timeline(entries=entries, total_duration=cursor, fps=fps)
