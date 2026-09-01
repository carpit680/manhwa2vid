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
| `narrator-presence` | warn | 0.3–4.0 narrator turns outward per 1000 words (address frames + first person) | **re-derived 2026-09-01.** Was `narrator-address`, counting only address frames, banded 0.3–2.0 from the competitor corpus (median 0.16, top video 1.01). The writer-narrator persona turns outward through the FIRST PERSON — "I should explain this" — so it scored 0.0 on frames alone and warned while being more present than any script before it. Presence is the sum; measured 1.85–2.64 across four persona arms on two titles, against 1.34 for the previous voice. 4.0 still catches a script that has become a podcast about a manhwa |
| `persona-voice` | warn | 0.6–3.5 writer asides per 1000 words | **new 2026-09-01.** Counts sentences where the narrator explains a rule the chapter assumes, compares it to life outside the book, recalls an earlier scene, notes a translation, or judges the writing or the art. The FLOOR is the load-bearing half: the first `writer_light` and `writer_medium` budgets were worded as prohibitions and produced ZERO asides, and nothing in the pipeline noticed the persona had silently failed to appear. Measured across the four arms: 1.85, 2.42, 2.57, 3.37. **Re-banded 2026-09-01** when the asked-for rate gained a length taper (`personas.aside_rate_per_1k`): the approved 6-minute render ran 2.42/1k and the user asked for roughly half *over long videos*, so rather than a flat halving that would thin the short video they had just approved, the target now falls from ~2.4/1k on a short recap to 1.2/1k at 20 chapters — one aside every ~4 minutes of runtime at full length. One band must accept both ends, hence 0.6–3.5 |
| `opener-rhythm` | warn | pronoun-open ≤ 40%, back-to-back opener ≤ 10%, connector-open ≥ 7% | **derived 2026-08-31 from the reference channel and the rhythm pass** (script/rhythm.py). Reference: 25.7% pronoun-open, 4.6% back-to-back, ~15% connector ("Then" alone 7.5%). Pre-pass scripts measured 35.3-46.7 / 11.0-25.0 / 1.1-3.7 on prose; the deterministic pass lands all three at ≤37.0 / ≤9.1 / ≥9.0, and the bands wrap that worst case with margin. Counters are `rhythm.opener_profile` — same ones the pass itself uses |
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
| `no-repeated-panels` | **fail** | no panel appears in two separate merged runs | 2026-08-30, promoted from warn same day (user decision): the shot planner's gap rule (`_gap_spare`) makes this exactly 0 on real artifacts, so nonzero is a regression — and the class shipped twice while warns scrolled past. Deliberate callback edits take `--force-past-qa` |
| `reading-order` | **fail** | merged-run sequence non-decreasing in `panels.story.json` order | 2026-08-30. Watched twice before it was measured: 16 inversions on FP (jumps back by up to 71 panels), 11 on SL — every large one an unconstrained "nearest unused panel" search in the shot planner (five sites: bare-bubble swap, bounded fill, cross-beat breaker, split borrow, final pass). All five now take substitutes only from the reading-order gap between the panels shown before and after; an empty gap keeps the long dwell. This gate notices the next unconstrained search however it arrives |
| `match-rate` | warn | ≥ 70% of non-outro sentences bound to their own panel | **re-derived 2026-08-28 from the fixed matcher** (window-scoped claims + distinct-sentence filter objective): measured FP 63.0%, SL 57.1%, up from 56.5/46.7. The brief's 70 was unsourced and unreachable — the matcher is instructed to claim nothing for narrator commentary, and the model volunteers a claim for only 74.6–78.7% of sentences, so 70 demanded matching nearly everything claimable. Outro sentences are excluded from the denominator (not panel-grounded by design). The residual gap to the ceiling is the monotonic filter refusing out-of-order claims — correct behaviour . **Re-derived up to 70 on 2026-08-31**: adjacent co-claims (two neighbouring sentences sharing the panel they both depict, folded into one shot) plus a short-gap second pass removed the dominant filter loss — panel contention, 50 of SL's 70 destroyed sentences. Measured post-fix: SL 77%, FP ch1-2 87%, ch3-4 89% |
| `panel-utilisation` | warn | ≥ 60% of story panels reach the screen | brief |
| `hold-run` | warn | ≤ 3 consecutive sentences on one panel | brief. Reports "not measured" when `sentence_numbers` is absent rather than passing |
| `timing-measured` | **fail** | ≥ 95% of sentences identity-matched to a measured sidecar | replaces the brief's "≥80% measured"; it is 100% today, so this guards a regression to word-proration |
| `panel-budget`, `narration-pace`, `beat-panels-missing` | warn | — | pre-existing |

## render

| gate | severity | threshold | source |
|---|---|---|---|
| `opening-shot` | **fail** | first 15s: luma > 16, lettering < 55%, **every second ≥ 15% art** | reference per-second art minimum is 26.2%; the brief's 50% would fail it. SL measures 5.4% |
| `true-peak` | fail | ≤ −1.0 dBTP | audio spec §6, tightened from −0.8 |
| `audio-loudness` | pass −26.0…−13.0 LUFS; warn to −30/−10; fail beyond | the 12-video competitor corpus | **re-derived 2026-08-30.** Field median −19.81, range −25.89 (vault_med, 3 K views) … −14.72 (outpost_top, 6.2 M views) — the loudest video in the corpus is also the most-watched, so the field does not punish loud. The prior form measured distance from `export.loudness_target` (−14 ± 1) and warned on our own −15.37 while FAILING −20.0, the field median: it scored adherence to a platform constant rather than whether the mix is wrong. Ceiling −13.0 sits above both the platform point and every field video, so a limiter is doing work the mix should not need; floor −26.0 is quieter than the whole field. We still PRODUCE at `export.loudness_target` −14.0 |
| `audio-music-present` | FAIL | bed floor > −60 dBFS | **re-derived 2026-08-30 against the competitor corpus.** The old −40 failed NINE of twelve field videos, including Mamoru's 5.2M (−44.2) and Tobs' 1.6M (−42.2) — it codified our own mix, not the format. A bed-less render measures −64.7 and the quietest real field video −57.4, so −60 is what honestly separates absence from a quiet bed. Tonality is REPORTED but no longer gated: absence scores 2.87 against that video's 2.71, so it cannot tell silence from music |
| `audio-bed-separation` | warn | 13–36 dB | **renamed from `audio-duck-depth` and re-derived from the corpus 2026-08-30.** Sidechain ducking is off by default (it pumped once `kokoro_trim_ms` cut inter-sentence gaps below its release), so "duck depth" stopped describing the chain — but voice-to-bed separation matters either way. Field measures 13.0–35.7 dB, median 21.9; ours 26.2. Judged on the ESTIMATE metric, the only one computable for competitors (no narration stem), with its known 2–7 dB bias applied identically to both sides. The stem value stays in the report as the more accurate number |
| `audio-lra` | FAIL | 1.5–4.5 LU | **measured off the reference channel's own audio** (2026-08-28): the full 5h17m track of the Mamoru Frozen Player video (`reference/frozen_player/mamoru_fp_audio.wav`, audio-only pull of the same video id the visual profile used) measures **2.50 LU** by loudnorm and **2.6 LU** by ebur128. The spec's 5–9 was an unsourced proposals-table row no single-voice TTS chain can reach — raw Kokoro narration measures 2.0 LU before any processing. Floor 1.5 catches range being CRUSHED (dynamic-loudnorm fallback); ceiling 4.5 catches dynamics this format never produces. Same measurement: reference integrated −17.5 LUFS (plays quieter than the −14 platform point; not copied) and true peak −0.77 dBTP, which would fail our own −1.0 gate — ours stays stricter |
| `audio-two-pass` | warn | absent unless the loudnorm measurement pass failed to parse | the fallback runs loudnorm in single-pass DYNAMIC mode, which compresses loudness range — it used to be a console line that scrolled away. If `audio-lra` failed, this gate says why |
| `shot-median` | warn | 2.0–3.5s | reference 2.30–2.87s |
| `shot-accent-share` | warn | ≥ 15% under 1.5s | reference 21.8–23.6% |
| `shot-cadence` | warn | 12–22 cuts/min | reference 16.2–**20.08**; the brief's 12–20 would fail W1 |
| `shot-max-duration` | warn > 12s, **fail > 18s** | longest time ONE IMAGE is on screen, from `merged_runs` over the planned timeline | the reference's own longest shot is **16.37s**; the brief's 12s fail would fail the reference. **Measure changed 2026-09-01**: it read ffmpeg scene detection on the finished file, which the renderer itself defeats — `render._long_hold_segments` cuts a long same-panel run into alternating fill/letterbox framings so a held image does not read as a frozen frame, and the detector scores each framing change as a cut. On the three shipped renders the detector reported 8.6 / 8.83 / 8.93s while one image actually sat for 18.3 / 19.14 / 16.2s, and all three passed. The detector value is still recorded as `detector_longest_s`. Re-checked against the honest measure the thresholds hold: the two >18s holds are both the final run on the final panel of their chapter, mid-video holds top out at 16.2s, and there is one of those across 488 runs |
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
