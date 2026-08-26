# Fix verification — before/after against the 2026-08-26 audit

New previews: FP `preview_2026-08-26_130021.mp4` (6:15), SL `preview_2026-08-26_131020.mp4` (13:05).
Same measured detectors as the audit; reference = Mamoru's own edit (same-content sample
for bubble/clipped bands).

## Editing rhythm

| | reference | FP before → after | SL before → after |
|---|---|---|---|
| median shot | 2.87s | 3.83s → **2.30s** | 5.00s → **2.40s** |
| shots < 1.5s | 22% | 6.0% → **31.9%** | 0.0% → **25.0%** |
| cuts/min | 16.3 | 14.9 → 21.4 | 11.6 → 20.1 |
| shots (total) | — | 96 → 135 | 159 → 264 |

The SL action climax that played 6 sentences over two 14.2s stills is now 8 shots
(1.1–5.6s) walking the explosion sequence panel by panel.

## Frame content

| | reference | FP after | SL after |
|---|---|---|---|
| bubble >20% of frame | 21.9% | 32.9% (warn) | **24.2% (pass)** |
| text clipped at edge | 43.9% | 45.7% (pass) | 44.4% (pass) |
| opening | — | badge + throne-room art | badge + name bubble WITH the bleeding hand |
| ending | — | cliffhanger → end card | statue reveal → end card |

Dead space: the audited defect (blurred pillarbox bars over 51–52% of screen area) is
structurally gone — every shot is a 16:9 window inside the panel. (The raw "dead width"
number now measures manhwa art flatness; the reference's own edit scores 0.742 on it,
so it is report-only.)

## Audio

| | before | after |
|---|---|---|
| true peak | **+0.30 dBTP (clips)** | **−1.38 / −1.30 dBTP** |
| BGM | none | Lightless Dawn (CC-BY, attribution in assets/bgm/) |
| sentence timing | 92–94% estimated | 100% measured (per-sentence synthesis) |
| pace | 223/222 WPM | ~223 WPM at kokoro_speed 1.34 (recalibrated) |
| ending | audio stops dead | BGM continues under 4.5s end card |

Root causes found on the way (never previously visible): ffmpeg `alimiter` defaults
`level=1` and re-normalizes to 0 dBFS after limiting; default mono AAC bitrate
overshoots ~+1.5 dB; `int(duration*fps)` truncation lost ~1 frame per shot (~4s of
progressive A/V desync at 252 shots).

## Gates

SL passes all 6 render gates. FP passes 5, warns on bubble-dominance (32.9% vs the
reference's 21.9% on the same dialogue-heavy chapters). One upstream fail remains and
is knowingly overridden: `script-final:dialogue-delivery` (5 FP beats drop a printed
system message — a property of the previously approved narration, surfaced by the new
render precondition rather than silently shipped).

## Still open

- FP bubble-dominance warn: the next lever is bubble-avoiding tighter windows (zoom
  past a bubble to the art when composition allows) — camera work, not planning.
- Chapter dividers need page→chapter metadata at ingest (doesn't exist for these
  projects).
- SL direct match rate is 49% (flash == pro tier); bounded fill covers the rest by
  construction, but a second matcher pass over unmatched spans is the designed next
  step if watching reveals drift.
