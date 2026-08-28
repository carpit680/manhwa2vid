# QA hardening brief

Goal: make it **impossible to render or export a video that carries any of the defects
below**. Every defect gets a measurement, a threshold, and a blocking gate. Nothing here
is done until a deliberately-broken input is proven to fail the gate.

Source evidence, read all three before starting:
- `reports/video_defect_audit_2026-08-26.md` — original defect audit
- `reports/gap_vs_mamoru_2026-08-26.md` — reference channel comparison
- `reports/render_audit_2026-08-28.md` — re-measurement of the 2026-08-27 previews

---

## Phase 1 — build the measurement harness first

Do not fix anything yet. Build `tools/measure_render.py` that takes a rendered mp4 (plus
its `timeline.json`, `script.final.md` and shot list) and emits a single JSON report with
every metric in the gate table below. It must run offline and take under two minutes on a
13-minute video.

Then **independently reproduce** the figures in `render_audit_2026-08-28.md` against
`_review/preview_2026-08-27_165848.mp4` and `_review/preview_2026-08-27_195630.mp4`.
Where your number disagrees with that report, investigate and record which is right — that
report's composition detector is a coarse "bright-and-flat block area" proxy and is
explicitly flagged as wider than the 08-26 blob detector. **Pick one detector, document it,
and use it for both current and reference measurements from now on.** Comparisons across
different detectors are worthless and have already caused one wrong conclusion in this
project.

Re-measure the Mamoru reference with the same detector so every threshold has a
like-for-like reference value. Do not carry forward reference numbers measured with a
different detector.

## Phase 2 — fix the false positives before adding gates

`reports/video_defect_audit_2026-08-26.md` §G3 records that some gate failures are false
positives — "Rank Hunter" flagged as a name when it is a fragment of "E-Rank Hunter",
"Earth Jun-Ho" flagged from a correct sentence. That report's own conclusion is that false
positives train the operator to ignore the gate, and that is exactly what happened: both
audited videos shipped while `name-integrity` was FAILING.

So: before any gate becomes blocking, drive its false-positive rate to zero on the two
existing projects. A gate that cries wolf is worse than no gate. Record the FP rate for
each gate in the report JSON.

## Phase 3 — the gate set

Implement each as a named gate in the existing QA framework, with a severity of `fail`
(blocking) or `warn`. Thresholds below are **starting proposals derived from the reference
channel and the audits — validate each against your re-measured reference and adjust with
a written justification.** Do not accept a threshold you cannot defend from data.

### Audio
| Gate | Threshold | Current |
|---|---|---|
| `audio-true-peak` | <= -1.0 dBTP | -1.4 / -1.3 — passing |
| `audio-loudness` | -16 +/- 1.0 LUFS integrated | -16.4 / -16.4 — passing |
| `audio-music-present` | quiet-window floor (p10 of 50ms RMS) > -40 dBFS, and tonal (peak/mean of the quiet-window spectrum > 5) | -34.3 / -34.7, ratio 7.0 / 6.6 — passing |
| `audio-duck-depth` | narration p75 minus quiet floor, in 12-15 dB | 19.5 / 19.7 — **FAIL, bed too quiet** |

### Editing rhythm
| Gate | Threshold | Current |
|---|---|---|
| `shot-accent-share` | >= 15% of shots under 1.5s | 21.7% / 21.4% — passing |
| `shot-median` | 2.0-3.5s | 2.52 / 2.38 — passing |
| `shot-cadence` | 12-20 cuts/min | 16.7 / 17.7 — passing |
| `shot-max-duration` | no shot > 12.0s | 16.7 / **27.8 — FAIL** |
| `shot-longtail-share` | <= 15% of runtime in shots > 8s | 28.1% / 22.6% — **FAIL both** |

### Composition
| Gate | Threshold | Current |
|---|---|---|
| `bubble-dominance` | share of frames whose largest bright-flat region exceeds 20% of frame <= reference value | ~50.8% / 38.5% (coarse detector) — **FAIL, largest remaining defect** |
| `bare-bubble` | **zero** frames containing a speech bubble with no story art in frame | multiple confirmed — **FAIL** |
| `clipped-text` | <= 10% of frames have an OCR text region intersecting the frame boundary | ~46% at 08-26, still visible — **FAIL** |
| `opening-strength` | every second of the first 15s has >= 50% detail-bearing area | B is 24-38% for the first 10s — **FAIL** |
| `ending-card` | final 5s contains an end card; no single frame held > 6s at the end | both end on a dead held panel — **FAIL** |
| `title-badge` | if a badge is drawn, it persists >= 2.0s | drawn on one frame (1/30s) at 08-26 — **FAIL** |

### Panel binding
| Gate | Threshold | Current |
|---|---|---|
| `match-rate` | >= 70% of sentences bound to their own panel | 49% / 76% at 08-26 — **FAIL on SL** |
| `panel-utilisation` | >= 60% of story panels reach the screen | 44-56% never reached — **FAIL** |
| `hold-run` | no more than 3 consecutive sentences on one panel | 6 / 4 at 08-26 — **FAIL** |

### Script quality — highest priority, see note below
| Gate | Threshold | Current |
|---|---|---|
| `name-integrity` | zero unresolved or inconsistent character names across the whole script | was FAILING and shipped twice — **make blocking** |
| `noun-repetition` | no noun phrase repeated more than 4 times in any rolling 200-word window | not implemented |
| `dialogue-verb-density` | >= 18 reporting verbs per 1000 words | 11.9 — **FAIL** (reference 20.8) |
| `quoted-dialogue` | >= 0.5 quoted spans per 1000 words | 0.0 — **FAIL** (reference 1.0) |
| `sentence-length-distribution` | >= 25% of sentences under 8 words | 11% — **FAIL** (reference 29%) |

### Timing
| Gate | Threshold | Current |
|---|---|---|
| `measured-timing-share` | >= 80% of sentences have a measured, not estimated, duration | 6-8% — **FAIL** |

**Why the script gates rank highest.** A comment-mining pass over ~950 comments across 16
videos and 6 channels found that viewers punish script errors roughly two orders of
magnitude harder than voice quality. The single highest-liked craft complaint in the niche
is a name-consistency failure ("From Rowan to Robert to Ramen to Ron to Roen to Rowen",
634 likes). Second is a noun-repetition failure (a channel repeating "apothecary" instead
of using pronouns, 78 likes for a viewer asking for a counter). Complaints about robotic
TTS timbre drew 0-2 likes. `name-integrity` and `noun-repetition` are therefore the two
highest-value gates in this document.

## Phase 4 — wire the gates as blocking

`pipeline.py` already refuses to render over failed upstream QA (`upstream_failures`).
Extend that so:
1. Visual and audio gates run **after** render and block **export**, since they can only be
   measured on the output.
2. `--force-past-qa` prints every failing gate by name, requires an explicit
   `--i-understand` confirmation, and writes the override plus the failing gate list into
   the project's checkpoint so it is permanently visible in `status`.
3. `manhwa2vid status` shows the gate table with pass/fail/warn per gate.

## Phase 5 — fix the defects

Ordered by value per unit effort. Do not batch these; land and verify one at a time.

1. **Ship the band-merge and art-substitution fixes.** `gap_vs_mamoru_2026-08-26.md` §2
   records both as coded but absent from the delivered videos. They target the largest
   remaining visual defect. Verify they are actually reachable from the current render path
   before writing anything new — this may be a wiring bug, not missing code.
2. **`name-integrity` blocking, false positives at zero.**
3. **`noun-repetition` lint** with pronoun substitution in the script stage.
4. **Forced alignment for sentence timing.** You have the script and the audio, so this is
   alignment, not transcription — WhisperX or aeneas, local and free. Replaces
   `_subdivide_segments` character-count estimation. Fixes root cause #4 and unlocks
   `measured-timing-share`.
5. **Cap shot duration.** Split any dwell over 10s across two panels, or add a slow push.
6. **Fix the opening.** Select the strongest-detail panel of the first chapter for the cold
   open; never open on a bubble or a near-black frame.
7. **End card**, and raise the music bed ~5 dB.
8. **OCR text bounding boxes as crop constraints** — a crop must contain a text region
   entirely or exclude it entirely. This kills `clipped-text` deterministically with no
   generation step.
9. **Raise match rate and panel utilisation.** The hold-on-uncertainty rule was a deliberate
   choice but at 49% it is the dominant behaviour rather than the fallback.

## Phase 6 — prove it

For each gate, write a test that feeds a deliberately broken input and asserts the gate
fails. A gate with no failing test is not trusted. Add these to the existing offline suite.

Then re-render both `_review` projects end to end and produce
`reports/render_audit_<date>.md` in the same format as the existing ones, showing every
gate green.

---

## Rules

- **Measure before you fix.** Every claim in this brief is falsifiable; if a number here is
  wrong, correct it in writing rather than coding against it.
- **One detector, documented.** Never compare metrics produced by different detectors.
- **No gate ships without a failing test.**
- **No threshold ships without a justification** traceable to reference data.
- **Do not weaken a gate to make a render pass.** If a threshold is wrong, say why in the
  report and change it deliberately; do not tune it to the current output.
- Keep the offline guarantee: `tests/test_offline_guard.py` must still pass.
