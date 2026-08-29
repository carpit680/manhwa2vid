# QA gates

Every gate, what it measures, its threshold and where that threshold came from. Written
because `docs/qa-hardening-brief.md` requires that no threshold ship without a
justification traceable to data — and because four of the brief's own proposals turned out
to fail the reference channel itself.

**Reference values** are measured from `reference/frozen_player/mamoru_fp_video.mp4` with
the same code the gates use (`src/manhwa2vid/measure/`), over three windows recorded in
`reference/mamoru_metrics_2026-08-28.json`. Comparing a number from one detector against a
threshold from another is the single most expensive mistake in this project's history; it
has produced a wrong conclusion three times.

**Severity policy.** A gate blocks only once its false-positive rate is zero on both
existing projects. Until then it warns, with the promotion recorded here. This is not
timidity: both audited videos shipped over a FAILING `name-integrity`, because a gate that
cries wolf teaches the operator to reach for `--force-past-qa`.

## A note on three broken metrics

Three measurements in this document were wrong before they were right, and each was caught
only by looking at what the number was made of rather than at the number:

1. **Duck depth** read p75 − p10 of the mix. It said 10.39 dB where the truth was 2.91 —
   the bed was three decibels under the voice while the gate called it healthy. Now
   measured from the narration stem at mix time.
2. **Quoted spans** treated the apostrophe as a quote delimiter, so every contraction
   matched. It put the reference at 1.62 per 1k; the real figure is 1.16, and the spans it
   had found were fragments like "re nothing" out of "they're nothing".
3. **Frame lettering** is validated on panels and does not transfer to rendered frames,
   where a brick wall outscores a real speech bubble.

The common shape: a plausible number, in the right units, moving in the right direction,
measuring the wrong thing. Print the matches, not just the count.

## script-story-first

| gate | severity | threshold | source |
|---|---|---|---|
| `beats-have-panels` | fail | every paragraph matches ≥1 panel | pre-existing |
| `panel-coverage` | warn | ≥ `align.min_panel_fraction` | pre-existing |
| `name-integrity` | **fail** | zero names absent from the glossary | promoted 2026-08-28; FP rate zero, three false positives fixed with regression tests |
| `beats-wellformed` | fail | no broken/truncated sentences | pre-existing |
| `grounding` | warn | audit findings survived the revision | pre-existing |
| `dialogue-verb-density` | warn | ≥ 18 per 1k words | reference **31.34**; floor is ~57% of it |
| `quoted-dialogue` | warn | ≥ 0.5 spans per 1k | reference **1.16** (re-measured; the first figure counted apostrophes in contractions) |
| `sentence-length` | warn | ≥ 18% of sentences under 8 words | reference **21.5%**. The brief said 25%, which the reference itself would fail |
| `noun-repetition` | warn | ≤ 4 repeats of a content word per rolling 200 words, cast exempt | brief |

## timeline

| gate | severity | threshold | source |
|---|---|---|---|
| `no-blank-panels` | fail | no blank panel in the timeline | pre-existing |
| `closing-shot-is-art` | fail | last shot is not a text-dominant panel | 2026-08-27 |
| `dwell-over-limit` | warn | no **merged run** over `max_panel_seconds × dwell_warn_multiplier` | reads runs, not entries — an 18.6s hold was two entries of 7.4s and 11.2s |
| `no-invisible-cuts` | warn | no consecutive entries on one panel | 2026-08-27 |
| `match-rate` | warn | ≥ 70% of non-outro sentences bound to their own panel | brief; floor re-derivation pending the window-scoped matcher (2026-08-28). Outro sentences are excluded from the denominator — the outro is deliberately not panel-grounded (script/outro.py), so its misses were a design decision scored as matcher failures |
| `panel-utilisation` | warn | ≥ 60% of story panels reach the screen | brief |
| `hold-run` | warn | ≤ 3 consecutive sentences on one panel | brief. Reports "not measured" when `sentence_numbers` is absent rather than passing |
| `timing-measured` | **fail** | ≥ 95% of sentences identity-matched to a measured sidecar | replaces the brief's "≥80% measured"; it is 100% today, so this guards a regression to word-proration |
| `panel-budget`, `narration-pace`, `beat-panels-missing` | warn | — | pre-existing |

## render

| gate | severity | threshold | source |
|---|---|---|---|
| `opening-shot` | **fail** | first 15s: luma > 16, lettering < 55%, **every second ≥ 15% art** | reference per-second art minimum is 26.2%; the brief's 50% would fail it. SL measures 5.4% |
| `true-peak` | fail | ≤ −1.0 dBTP | audio spec §6, tightened from −0.8 |
| `audio-loudness` | fail outside [target−3, +2], warn outside ±1 | vs `export.loudness_target` | **not** the spec's −16±1, which codifies the current undershoot |
| `audio-music-present` | **fail** | bed floor > −40 dBFS **and** tonality > 5 | audio spec §6; catches an empty `assets/bgm/` |
| `audio-duck-depth` | warn → fail | 12–15 dB | audio spec §6. Measured from the narration STEM at mix time — the mix alone overstates the duck by 2–7 dB, so the gate is absent rather than wrong when the stem is unavailable  **Cross-checked against the reference's mix 2026-08-28** with the same window-RMS estimator on both files: the reference's quiet-percentile sits ~7 dB below its speech level where ours sits ~11 — the channel runs a HOTTER bed than the 12–15 band produces. Retuning would change the whole mix's feel; deferred to a listening decision, recorded here so the band is not mistaken for reference-derived |
| `audio-lra` | FAIL | 1.5–4.5 LU | **measured off the reference channel's own audio** (2026-08-28): the full 5h17m track of the Mamoru Frozen Player video (`reference/frozen_player/mamoru_fp_audio.wav`, audio-only pull of the same video id the visual profile used) measures **2.50 LU** by loudnorm and **2.6 LU** by ebur128. The spec's 5–9 was an unsourced proposals-table row no single-voice TTS chain can reach — raw Kokoro narration measures 2.0 LU before any processing. Floor 1.5 catches range being CRUSHED (dynamic-loudnorm fallback); ceiling 4.5 catches dynamics this format never produces. Same measurement: reference integrated −17.5 LUFS (plays quieter than the −14 platform point; not copied) and true peak −0.77 dBTP, which would fail our own −1.0 gate — ours stays stricter |
| `audio-two-pass` | warn | absent unless the loudnorm measurement pass failed to parse | the fallback runs loudnorm in single-pass DYNAMIC mode, which compresses loudness range — it used to be a console line that scrolled away. If `audio-lra` failed, this gate says why |
| `shot-median` | warn | 2.0–3.5s | reference 2.30–2.87s |
| `shot-accent-share` | warn | ≥ 15% under 1.5s | reference 21.8–23.6% |
| `shot-cadence` | warn | 12–22 cuts/min | reference 16.2–**20.08**; the brief's 12–20 would fail W1 |
| `shot-max-duration` | warn > 12s, **fail > 18s** | — | the reference's own longest shot is **16.37s**; the brief's 12s fail would fail the reference |
| `shot-longtail-share` | warn > 18%, **fail > 25%** | runtime in shots > 8s | reference 13.6–**22.2%**; the brief's 15% would fail W2 |
| `clipped-text` | report-only | — | reference **67.5–69.8%** vs our 45.3/56.5 — it is worse than us. The brief's 10% is unreachable |
| `lettering-share`, `bare-bubble` | report-only | — | detector not validated at frame resolution — see below |
| `bubble-dominance`, `dead-space` | report-only | — | detectors measure a property of manhwa art, not a defect |

### Why four composition measures are not gates

`panels.regions.text_regions` is validated on **panels** — clean line art at source
resolution, zero false positives across all 607 panels of both titles. That validation does
not transfer to rendered frames. Measured on real frames: a brick wall with no text at all
scores **0.615** and a crowd on rock **0.818**, against **0.402** for a genuine
"E-RANK HUNTER." bubble. Texture produces rows of similar-sized, similar-stroke-width blobs,
which is the geometric signature of lettering.

Four separating rules were tried against a 15-window eye-labelled set — frame-level area,
window-crop area, container area, and detect-at-panel-then-intersect-window — and all four
overlap. The defect is real (Solo Leveling still opens on a bubble on black) but the
**camera window** creates it, so even the validated panel classifier cannot see it: the
panel behind that frame scores 0.231 and is correctly not text-dominant.

Unblocking them means validating a window-level detector the way the panel one was
validated — on a labelled set of camera windows. That is real work, and it is not to be
smuggled into a threshold.
