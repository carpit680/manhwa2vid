#!/usr/bin/env python3
"""Measure a corpus of competitor videos with OUR detectors, so the field and we are
directly comparable.

    tools/measure_corpus.py [--corpus reference/corpus] [--out reference/corpus/corpus_metrics.json]

Every channel in the niche is measured by the same code that gates our own renders
(`manhwa2vid.measure.*`), which is the whole point: a number here and a number in
`qa.render.json` mean the same thing. Where a metric cannot be computed from a section
(anything needing the full runtime), it is omitted rather than estimated.

Layout expected, as produced by the fetch script:

    reference/corpus/<label>/<id>_open.{mp4,webm}     first 120 s
    reference/corpus/<label>/<id>_mid.{mp4,webm}      240 s from the middle
    reference/corpus/<label>/<id>_close.{mp4,webm}    last ~70 s
    reference/corpus/<label>/<id>.info.json           yt-dlp metadata
    reference/corpus/<label>/<id>.en*.vtt             auto-subtitles (full runtime)

This tool may read `reference/`; `src/` may not — tests/test_series_agnostic.py enforces
that, which is why every measurement function takes its paths as arguments.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np  # noqa: E402

from manhwa2vid.measure.script_text import (  # noqa: E402
    dialogue_verb_density,
    quoted_span_rate,
    sentence_length_stats,
)
from manhwa2vid.measure.shots import detect_cuts, shot_lengths, shot_stats  # noqa: E402

VIDEO_EXT = (".mp4", ".webm", ".mkv")


# --------------------------------------------------------------------------- helpers
def _probe(path: Path, entries: str) -> str:
    return subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", entries, "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()


def _pcm(path: Path, sr: int = 22050) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
         "-f", "f32le", "-"],
        capture_output=True,
    ).stdout
    return np.frombuffer(raw, np.float32)


def _find(folder: Path, suffix: str) -> Path | None:
    for ext in VIDEO_EXT:
        hits = sorted(folder.glob(f"*{suffix}{ext}"))
        if hits:
            return hits[0]
    return None


# --------------------------------------------------------------------------- audio
def loudness(path: Path) -> dict[str, Any]:
    """Integrated loudness, range and true peak — the same loudnorm pass the gates use."""
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-i", str(path),
         "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    start = proc.stderr.rfind("{")
    if start == -1:
        return {}
    try:
        d = json.loads(proc.stderr[start:])
        return {
            "lufs": float(d["input_i"]),
            "lra_lu": float(d["input_lra"]),
            "true_peak_dbtp": float(d["input_tp"]),
        }
    except (ValueError, KeyError, TypeError):
        return {}


def prosody(path: Path, sr: int = 22050) -> dict[str, Any]:
    """Pause structure and pitch movement — the two things that separate a human read
    from a synthesised one, measured the same way on both sides.

    Pauses are counted against a level 30 dB below the speech peak, so a music bed does
    not fill them in: a bed-only window still sits far under the voice.
    """
    try:
        import librosa
    except ImportError:
        return {}
    y = _pcm(path, sr)
    if y.size < sr:
        return {}
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=256)[0]
    db = 20 * np.log10(np.maximum(rms, 1e-6))
    quiet = db < (np.percentile(db, 95) - 30.0)
    runs, run = [], 0
    for q in quiet:
        if q:
            run += 1
        elif run:
            runs.append(run * 256 / sr)
            run = 0
    pauses = [r for r in runs if r > 0.15]
    minutes = y.size / sr / 60.0
    out = {
        "pauses_over_150ms_per_min": round(len(pauses) / max(minutes, 1e-6), 1),
        "pause_mean_s": round(float(np.mean(pauses)), 3) if pauses else 0.0,
        "pause_median_s": round(float(np.median(pauses)), 3) if pauses else 0.0,
        "speech_share_pct": round(100.0 * float(np.mean(~quiet)), 1),
    }
    f0 = librosa.yin(y, fmin=70, fmax=400, sr=sr)
    voiced = f0[(f0 > 75) & (f0 < 380)]
    if voiced.size > 50:
        semis = 12 * np.log2(voiced / np.median(voiced))
        out["f0_median_hz"] = round(float(np.median(voiced)), 1)
        out["f0_spread_semitones"] = round(
            float(np.percentile(semis, 90) - np.percentile(semis, 10)), 1
        )
    return out


# --------------------------------------------------------------------------- picture
def editing(path: Path) -> dict[str, Any]:
    """Cut rhythm — the reference channel was profiled with exactly this detector."""
    dur = float(_probe(path, "format=duration") or 0)
    if dur <= 0:
        return {}
    # shot_stats takes LENGTHS, not cut timestamps — passing cuts makes a 119 s
    # timestamp read as a 119 s shot and the median explodes.
    cuts = detect_cuts(path)
    st = shot_stats(shot_lengths(cuts, dur), dur)
    st["section_seconds"] = round(dur, 1)
    return st


# --------------------------------------------------------------------------- script
_VTT_TAG = re.compile(r"<[^>]+>")
_VTT_TIME = re.compile(r"\d\d:\d\d:\d\d[.,]\d\d\d\s*-->")


def read_vtt(path: Path) -> tuple[str, float]:
    """Plain text plus last cue time, with the rolling-caption duplication removed.

    Auto-captions repeat the previous cue's tail in the next cue. Naively concatenating
    inflates every word-count-derived metric — this is the same de-duplication used on
    the reference SRT.
    """
    words: list[str] = []
    last_t = 0.0
    for block in re.split(r"\n\s*\n", path.read_text(errors="ignore")):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        for ln in lines:
            if "-->" in ln:
                m = re.findall(r"(\d\d):(\d\d):(\d\d)[.,](\d\d\d)", ln)
                if m:
                    h, mi, s, ms = m[-1]
                    last_t = max(last_t, int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000)
        text = " ".join(
            _VTT_TAG.sub("", ln) for ln in lines
            if "-->" not in ln and not ln.strip().isdigit() and not ln.startswith("WEBVTT")
            and not ln.startswith(("Kind:", "Language:", "NOTE"))
        )
        w = text.split()
        if not w:
            continue
        for k in range(min(len(w), len(words)), -1, -1):
            if words[len(words) - k:] == w[:k]:
                words.extend(w[k:])
                break
        else:
            words.extend(w)
    return " ".join(words), last_t


def script_metrics(text: str, seconds: float) -> dict[str, Any]:
    d = dialogue_verb_density(text)
    q = quoted_span_rate(text)
    s = sentence_length_stats(text)
    n_words = d["words"]
    low = text.lower()
    out = {
        "words": n_words,
        "wpm": round(n_words / (seconds / 60.0), 1) if seconds > 0 else None,
        "dialogue_verbs_per_1k": d["per_1k"],
        "quoted_per_1k": q["per_1k"],
        "mean_sentence_words": s["mean_words"],
        "under_8w_pct": s["under_8_pct"],
        # Manhwa Tales' rule: stop repeating the character's name, use "bro"/"our guy".
        "second_person_per_1k": round(
            1000.0 * len(re.findall(r"\b(you|your|you're)\b", low)) / max(n_words, 1), 2
        ),
        "casual_epithet_per_1k": round(
            1000.0 * len(re.findall(r"\b(bro|our guy|my guy|dude|homie|this guy)\b", low))
            / max(n_words, 1), 2
        ),
    }
    return out


# --------------------------------------------------------------------------- driver
def measure_one(folder: Path) -> dict[str, Any]:
    label = folder.name
    rec: dict[str, Any] = {"label": label}

    info = sorted(folder.glob("*.info.json"))
    if info:
        d = json.loads(info[0].read_text(errors="ignore"))
        rec["meta"] = {
            "id": d.get("id"),
            "channel": d.get("channel"),
            "subs": d.get("channel_follower_count"),
            "views": d.get("view_count"),
            "duration_s": d.get("duration"),
            "title": d.get("title"),
        }

    vtt = sorted(folder.glob("*.vtt"))
    if vtt:
        text, last_t = read_vtt(vtt[0])
        secs = (rec.get("meta") or {}).get("duration_s") or last_t
        if text:
            rec["script"] = script_metrics(text, float(secs or 0))

    for section in ("open", "mid", "close"):
        v = _find(folder, f"_{section}")
        if not v:
            continue
        block: dict[str, Any] = {"file": v.name}
        block.update(editing(v))
        block.update(loudness(v))
        block.update(prosody(v))
        rec[section] = block
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="reference/corpus")
    ap.add_argument("--out", default="reference/corpus/corpus_metrics.json")
    ap.add_argument("--only", default=None, help="substring filter on label")
    args = ap.parse_args()

    root = Path(args.corpus)
    results = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if args.only and args.only not in folder.name:
            continue
        print(f"  measuring {folder.name} ...", flush=True)
        try:
            results.append(measure_one(folder))
        except Exception as exc:  # noqa: BLE001 — one bad video must not lose the corpus
            print(f"    failed: {type(exc).__name__}: {exc}")
            results.append({"label": folder.name, "error": str(exc)})

    Path(args.out).write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\n  wrote {args.out} ({len(results)} entries)")


if __name__ == "__main__":
    main()
