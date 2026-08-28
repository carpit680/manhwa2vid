# Render audit and threshold reconciliation — 2026-08-28

Phase 1 of `docs/qa-hardening-brief.md`. Every number below was measured with
`tools/measure_render.py`, which shares its detectors with the QA gates
(`src/manhwa2vid/measure/`), so our numbers and the reference channel's are the same
measurement. Raw output: `reports/evidence/measure_fp_2026-08-28.json`,
`reports/evidence/measure_sl_2026-08-28.json`,
`reference/mamoru_metrics_2026-08-28.json`.

Subjects: `preview_2026-08-27_165848.mp4` (FP ch1-2, 6:22) and
`preview_2026-08-27_195630.mp4` (SL ch1-5, 13:12).

## 0. Two corrections to the brief before anything else

**The brief cites evidence that does not exist.** `reports/render_audit_2026-08-28.md`
and `_review/` are referenced as source material. Neither is on disk, in any branch, or
in the stash. This report is that file, created rather than read; the brief's "Current"
column has been treated as claims to verify, not as data.

**Two of its Phase 5 items are already done.** `gap_vs_mamoru_2026-08-26.md` §2 says the
band-merge and art-substitution fixes are "coded but neither is in the delivered videos".
That was true when written and is now stale: `_merge_text_only_bands` runs on the live
hybrid split path (`panels/split.py:476`), the bubble→art swap runs in `plan_shots` fed
by `tts/engine.py`, and both current previews were built after those commits (panels
re-split 08-26 19:53/20:14, timelines 08-27 12:47/19:56). Likewise §G3's two
name-integrity false positives ("Rank Hunter", "Earth Jun-Ho") are fixed with pinned
regression tests.

## 1. The detector decision

**Canonical: the geometric lettering detector** — `panels/regions.text_regions` /
`_text_and_content_masks`. It finds lettering by shape (glyph-sized ink in rows sharing a
height and a stroke width, grown to the bubble holding it). Validated 2026-08-27 across
all 607 panels of both titles with every flagged panel opened by eye: zero false
positives, lowest true-text 0.853 against highest true-art 0.778.

**Demoted to data: the brightness proxies** — `bubble_stats` (`> 232`, solid, some dark
pixels inside) and `dead_width`. These are recorded in every report so historical numbers
stay comparable, and they decide nothing. The reason is measured, not stylistic: the blob
test scored hospital bedding at 76% of frame and a real speech bubble at 0.00, and it
inverted a real verdict — it read the Frost Queen's pale hair as a 34%-of-frame "bubble"
and failed an opening whose lettering had in fact fallen from 48% to 30%.

**Frame-level lettering is measured as AREA — share of the screen.** The panel-level
`text_content_ratio` (lettering as a share of non-background *content*) is deliberately
not reused on frames: the blurred pillarbox counts as content and drags it down, so a
frame that is visibly half speech bubble reads 0.40.

### Methodology validation

Scene detection reproduces `tools/profile_shots.py` exactly on the reference's own
window: 325 shots, 16.2 cuts/min, median 2.87s, 22.2% under 1.5s, longest 16.37s —
against `reference/mamoru_shot_profile.md`'s 325 / 16.25 / 2.87 / 22.2% / 16.37. The
script counters likewise reproduce `reference/profile_srt.py`: 31.34 dialogue verbs/1k
against its published 31.3, mean sentence 12.76 words against its 12.8.

The harness also reproduces this render's own recorded gate data exactly (bubble 29.0,
clipped 42.1, dead 0.64, −1.35 dBTP, 106 shots, median 2.52s, 21.7% under 1.5s), so the
refactor that created it is behaviour-neutral.

Runtime: 16.6s for the 6:22 video, 35.3s for the 13:12 video — inside the brief's 2-minute
budget. The 5h17m reference cost 107.8s for three windows.

## 2. Reference windows

`reference/frozen_player/mamoru_fp_video.mp4` is a 5h17m binge compilation, so a single
window cannot answer everything:

| window | span | what it is for |
|---|---|---|
| **W1** | 0–780s | the reference's own edit of **Frozen Player ch1-2** — the like-for-like baseline for composition gates. Did not exist in the prior profile. |
| **W2** | 300–1500s | continuity with `mamoru_shot_profile.md`; rhythm baselines comparable to the published numbers. |
| **W3** | 10000–11200s | stability check. Where W2 and W3 disagree, the band covers both. |

Caveat: W1 starts at the file's first frame, which is a compilation intro rather than a
chapter cold open, so it is used for composition and not for `opening-strength`.

## 3. Measurements

### Composition (validated detector)

| metric | ref W1 | ref W2 | ref W3 | FP | SL |
|---|---|---|---|---|---|
| lettering area, median | 0.113 | 0.101 | 0.111 | 0.147 | 0.170 |
| lettering area, p95 | 0.378 | 0.306 | 0.324 | 0.417 | — |
| frames with lettering > 30% of screen | 11.0% | 5.5% | 6.5% | **14.9%** | **19.8%** |
| frames with lettering > 40% | 3.8% | 1.9% | 2.5% | 5.6% | — |
| lettering sliced at the frame edge | 67.5% | 69.8% | 69.0% | **45.3%** | **56.5%** |
| bare-bubble frames | 0.4% | 0.0% | 0.2% | **0.0%** | **0.7%** |
| art area, median | 0.637 | 0.636 | 0.602 | 0.504 | 0.628 |

### Rhythm (scene detection, T=0.30)

| metric | ref W1 | ref W2 | ref W3 | FP | SL |
|---|---|---|---|---|---|
| shots | 262 | 325 | 385 | 106 | 234 |
| cuts/min | 20.08 | 16.2 | 19.2 | 16.51 | 17.65 |
| median shot | 2.30s | 2.87s | 2.44s | 2.52s | 2.38s |
| shots under 1.5s | 21.8% | 22.2% | 23.6% | 21.7% | 21.4% |
| longest shot | 13.35s | 16.37s | 13.13s | **16.70s** | **27.77s** |
| runtime in shots > 8s | 14.7% | 22.2% | 13.6% | **28.1%** | 22.6% |
| runtime in shots > 12s | 3.4% | 6.9% | 3.2% | 11.4% | — |

### Audio (whole file)

| metric | FP | SL |
|---|---|---|
| true peak | −1.35 dBTP | −1.32 dBTP |
| integrated loudness | −16.38 LUFS | −16.43 LUFS |
| quiet-window floor (bed) | −34.25 dBFS | −34.68 dBFS |
| tonality ratio (is the bed music?) | 6.26 | 6.58 |
| duck depth | 19.45 dB | 19.72 dB |

### Binding, timing, script

| metric | FP | SL | reference |
|---|---|---|---|
| match rate | 61.1% | 48.7% | n/a |
| panel utilisation | 58.8% | 71.5% | n/a |
| invisible cuts (adjacent duplicate entries) | 6 | 7 | n/a |
| longest merged run | 18.58s | 27.79s | n/a |
| sentences with a measured duration | **100%** | **100%** | n/a |
| dialogue verbs /1k | 6.98 | 2.77 | **31.34** |
| quoted spans /1k | 0.00 | 0.00 | **1.62** |
| sentences under 8 words | 8.9% | 23.7% | **21.5%** |
| mean sentence length | 15.92w | 12.45w | 12.76w |
| noun repetition, worst in any 200w window | 0 over limit | 0 over limit | n/a |

## 4. Verdict on every claim in the brief

| brief claim | verdict | evidence |
|---|---|---|
| true peak −1.4/−1.3, passing | **right** | −1.35 / −1.32 |
| loudness −16.4/−16.4, passing | **right** | −16.38 / −16.43 |
| music floor −34.3/−34.7, ratio 7.0/6.6 | **right** | −34.25/−34.68, ratio 6.26/6.58 |
| duck depth 19.5/19.7, FAIL bed too quiet | **right** | 19.45 / 19.72 |
| accent share 21.7%/21.4% | **right** | exact match |
| median 2.52/2.38 | **right** | exact match |
| cadence 16.7/17.7 | **right** | 16.51 / 17.65 |
| longest shot 16.7 / 27.8 | **right** | 16.70 / 27.77 |
| longtail 28.1% / 22.6% | **right** | exact match |
| bubble-dominance ~50.8%/38.5% "coarse detector" | **wrong / unreproducible** | no detector here yields those. Validated detector: 14.9%/19.8% of frames over 30% lettering. Brightness proxy: 29.0%/17.0% over 20%. |
| clipped-text ~46%, still visible | **stale** | 46% was the 08-26 render. Now 45.3%/56.5% by the validated detector — but the reference measures **67.5–69.8%**, worse than ours. |
| bare bubble: multiple confirmed | **stale for FP, right for SL** | FP 0.0%, SL 0.7% |
| opening B is 24–38% detail for first 10s | **right, and worse than stated** | FP min second 28.3%, SL min second **5.4%** |
| match rate 49%/76% | **half right** | 48.7% is SL, not FP; FP is 61.1%. Labels appear swapped. |
| panel utilisation 44–56% unreached | **stale** | reached: FP 58.8%, SL 71.5% |
| hold-run 6/4 consecutive sentences | **not measurable yet** | needs `TimelineEntry.sentence_numbers`; today only entries-per-run is observable (max 2). Invisible cuts: 6/7. |
| measured-timing-share 6–8% | **wrong now** | 100% on both. Kokoro synthesizes per sentence; the claim predates that. |
| name-integrity was FAILING and shipped | **stale** | passes both; the two known false positives are fixed with tests. Still warn-only — promoting it is Phase 3 work. |
| dialogue-verb density 11.9, reference 20.8 | **wrong on both sides** | ours 6.98/2.77; reference **31.34** with the counter its own profile script uses |
| quoted dialogue 0.0, reference 1.0 | **ours right, reference low** | reference 1.62 |
| sentences under 8 words 11%, reference 29% | **wrong on both sides** | ours 8.9%/23.7%; reference **21.5%** |
| noun-repetition not implemented | **right** | now implemented; both scripts pass at the brief's limit |

## 5. Threshold decisions

Four of the brief's proposed thresholds **fail the reference channel itself**. The brief
instructs that a threshold be defensible from data and corrected in writing rather than
coded against, so:

| gate | brief | adopted | justification |
|---|---|---|---|
| `shot-max-duration` | ≤ 12.0s | **fail > 18s, warn > 12s** | The reference's own longest shot is 16.37s (W2) — 12s would fail the channel being imitated. 18s = reference max + margin. FP 16.70 warns; SL 27.77 fails, which is the real defect. |
| `shot-longtail-share` | ≤ 15% | **fail > 25%, warn > 18%** | Reference runtime in >8s shots is 13.6–22.2% across windows; 15% would fail W2. Band covers the reference's own spread. FP 28.1% fails; SL 22.6% warns. |
| `clipped-text` | ≤ 10% | **report-only, no gate** | The reference measures 67.5–69.8% with the validated detector; ours are 45.3%/56.5%, i.e. already markedly better. A 10% gate would be unreachable for anyone. Panning a 16:9 window over tall bubbled art clips lettering as a matter of course. Recorded as data; revisit only if Phase 5's crop-constraint work makes a low number achievable. |
| `sentence-length-distribution` | ≥ 25% under 8 words | **warn < 18%** | The reference is 21.5% — 25% would fail it. Worse, SL at 23.7% is *more* reference-like than the reference and would still fail. 18% sits below the reference with margin. FP 8.9% warns; SL 23.7% passes. |
| `opening-strength` | ≥ 50% detail every second of first 15s | **fail < 15%, warn < 25%** | Reference per-second art minimum is 26.2% (W2) and 45.7% (W1) — a 50% floor fails the reference. SL's 5.4% minimum is a genuine defect and fails; FP's 28.3% passes. |
| `cuts-per-min` | 12–20 | **12–22** | Reference W1 is 20.08, just outside the brief's band. |
| `bare-bubble` | zero frames | **fail > 0.5%** | The reference is not at zero either (0.0–0.4%). 0.5% is the reference's worst window plus a hair. FP 0.0% passes; SL 0.7% fails. |
| `lettering-share` (replaces `bubble-dominance`) | ≤ reference | **fail > 25%, warn > 14%** | Same-content W1 is 11.0% of frames over 30% lettering. Warn at 14% (reference + 3pp) and fail at 25% keeps a genuinely bubble-heavy render out without punishing dialogue-dense chapters. FP 14.9% warns, SL 19.8% warns. |
| `audio-loudness` | −16 ± 1.0 LUFS | **target ±1 warn, [target−3, target+2] fail; target = `export.loudness_target`** | −16 codifies the *undershoot*: the pipeline targets −14 and lands at −16.4 because `loudnorm linear=true` will not apply gain that breaches TP −1.5. Pinning the gate at −16 would fail a future render that fixes it. |
| `measured-timing-share` | ≥ 80% measured | **retired; replaced by `timing-measured` ≥ 95% identity-matched** | 100% today. The live risk is not estimation but silent regression to `timeline._subdivide_segments` word-proration on a non-Kokoro provider, which an existence check would not catch — so the gate checks per-beat sentence-count identity. |
| `dialogue-verb-density` | ≥ 18/1k | **≥ 18/1k, kept** | Now justified against a like-for-like reference of 31.34/1k rather than the brief's unsourced 20.8. 18 is ~57% of the reference — a floor, not a target. |
| `quoted-dialogue` | ≥ 0.5/1k | **≥ 0.5/1k, kept** | Reference 1.62/1k. |
| `noun-repetition` | > 4 in 200 words | **kept** | Both scripts pass (worst is `hunter` ×4 in SL). Ships as a regression guard, not a fix trigger. |

## 6. Deliberate deviations from the brief

- **`title-badge` gate is not implemented.** The badge was removed at the user's explicit
  request on 2026-08-27 and they did not ask for it back. Gating on the presence of a
  feature the user removed would be following the brief against its owner.
- **`ending-card` becomes a user-supplied thumbnail** (user decision, 2026-08-28): one
  image serves as both the YouTube thumbnail and the end card under the closing hook, with
  a clearly-labelled placeholder when absent. Phase 5.

## 7. False-positive rates — and a gate that cannot ship

A gate that cries wolf trains the operator to force past it, and that already happened
here: both audited videos shipped while `name-integrity` was failing. So every
detector-backed gate was audited by eye on both projects before being allowed to block.

| gate | verdict | evidence |
|---|---|---|
| `name-integrity` | **0 false positives** | the two historical cases ("Rank Hunter" from "E-Rank Hunter", "Earth Jun-Ho" from a correct sentence) are fixed with pinned regression tests; passes both projects |
| `noun-repetition` | **0 false positives** | both scripts pass at >4 per 200 words; responds correctly when tightened (finds `hunter` x4 at a cap of 3, `floor` x7 unexempted), so it is not vacuous |
| `bare-bubble` | **NOT GATEABLE** | see below |
| `lettering-share` | **NOT GATEABLE** | see below |
| `opening-strength` | **warn only** | shares the detector below; the opening window is a smaller surface but the same failure mode is possible |

### Why `bare-bubble` and `lettering-share` cannot ship as gates

The geometric lettering detector was validated on **panels** — clean line art at source
resolution. That validation does not transfer to rendered frames or camera-window crops,
and the numbers say so plainly. On real frames the false positives outscore the true
positives:

| frame | truth | lettering measured |
|---|---|---|
| brick wall, no text at all | art | **0.615** |
| crowd on rock, no text at all | art | **0.818** |
| "E-RANK HUNTER." bubble on black | bare bubble | 0.402 |
| starburst bubble on white | bare bubble | 0.151 |

Four approaches were tried against a 15-window set labelled by eye, and all four overlap:

1. **Frame-level lettering area** — false positives above every true positive, at every
   resolution tested (480/720/960/1280 px wide).
2. **Window-crop lettering area** — BARE 0.122–0.404 vs ART 0.193–0.651.
3. **Container area** (blobs passing the flatness/hull/solidity guards) — mostly 0.000 for
   true bare bubbles; their bubbles fail the container test at window scale.
4. **Detect at panel resolution, intersect with the window rectangle** — the
   methodologically correct version, and still interleaved: sorted by art area the labels
   run BARE, BARE, ART, ART, ART, BARE, BARE, BARE.

Texture is the mechanism. Brick, rock and hatching produce rows of similar-sized,
similar-stroke-width blobs at frame scale, which is exactly the geometric signature of
lettering.

**The defect is real and remains unguarded.** Solo Leveling opens on "E-RANK HUNTER." in a
starburst bubble on pure black at t=6s — the 2026-08-26 audit's A1 defect, still shipping.
The panel behind it (`p0002_03`) scores 0.231 and is correctly *not* text-dominant: the
panel is fine and the **camera window** creates the defect, so the validated panel
classifier cannot catch it either.

Both therefore ship as **report-only measurements**. Per this brief's own rule — a
threshold must be defensible from data — shipping them as blocking gates on an unvalidated
detector would be the same error the `bubble-dominance` gate already made once.

What would unblock them: a window-level detector validated the way the panel one was, on a
labelled set of camera windows rather than panels. That is real work and it is not
smuggled into a threshold.

---

## 8. Pronunciation: verified, attempted twice, rejected twice

`docs/audio-quality-spec.md` §0 identified a real mechanism and this repo is exposed to it.
The fix was tried, listened to, and **rejected**. Recording it so nobody rebuilds it.

### The mechanism is real and reproduces here

This install is **Path B**: `espeak-ng` is not on PATH, but `espeakng-loader` supplies a
bundled binary, so Kokoro's fallback is active and out-of-lexicon names are
**mispronounced rather than deleted**. `tools/qa/tts_env_check.py` settles this on any
machine; run it before trusting anything here.

**22 of 46** proper nouns across both projects' `glossary.json` are outside Kokoro's
178k-entry lexicon and depend on espeak. The spec's examples reproduce exactly
(`Baek`→"beek", `Song Chi-Yul`→"Song KAI-yul"), plus two this repo cares about more:

- `Seo Jun-Ho` → `sˈiO ʤˈʌnhˌO` — "**SEE-oh** Jun-Ho". The Frozen Player protagonist,
  said throughout every video shipped.
- `Carthenon Temple` → `kˈɑɹθɛnən` but its own glossary alias `Cartenon Temple` →
  `kˈɑɹtɛnən`. **One place, two spoken names.** This is `name-integrity`'s downstream
  failure exactly: the gate passes because both spellings are known, and the audio drifts
  anyway. It is also the niche's single most-liked craft complaint ("From Rowan to Robert
  to Ramen to Ron to Roen to Rowen", 634 likes).

### Both fixes lost to the baseline

| attempt | design | envelope vs baseline | user verdict |
|---|---|---|---|
| v1 — spec §0.4 | 27 entries, per-syllable, phonetically faithful | **+26%** articulation (over-articulating) | **rejected** |
| v2 — correction-01 §4 `MIN_LEX` | 8 entries, whole-name, override only broken consonants | **−6.2%** articulation | **rejected** |

v2 is the important one. It was designed specifically to fix what v1 was rejected for, it
succeeded on that measure, and on this repo's rosters it changed only two words
(`Deok-gu` "dee-OCK-goo"→"DUCK-goo", `Chi-Yul` "KAI-yul"→"chee-yul"). It still sounded
worse. Two attempts with opposite designs both lost.

**Conclusion: injecting `lexicon.golds` entries degrades delivery on this voice regardless
of how minimal the entry is.** A plausible mechanism — a gold entry is used verbatim, so
the word stops participating in the sentence-level prosody espeak-derived phonemization
feeds — but that is a hypothesis, not a measurement, and it is not needed to act on the
result. **No lexicon is wired into the pipeline.** The correction's own §7 says it best:
the phoneme string being "more correct" is not evidence that the audio is better.

Methodological note: the first envelope check compared this detector's absolute
articulation rate against the correction's 5.3/6.7 figures. Those came from a different
peak-picker — this one reads the same espeak baseline at 7.47/s — so the comparison was
meaningless. It now measures against the baseline it took itself. That is the third time
in this project a cross-detector comparison has produced a wrong reading.

### What survives, and what is still guarded

- **The deletion guard stays.** Path A is catastrophic and silent: on a machine without
  the espeak fallback, every out-of-lexicon name vanishes from the audio entirely. A
  `tts-phoneme-coverage` gate — zero glossary names resolving to empty phonemes — is still
  worth shipping. It guards deletion, not mispronunciation.
- **`tts-lexicon-valid` is dropped**: there is no lexicon to validate.
- **The remaining lever is the voice, not the phonemes.** A different voice may handle rare
  phoneme sequences better, which is the spec's own argument for preferring H-hours
  training data. That is measured in Phase 5 with F0, and any name-audio revisit rides on
  it — with its own A/B, because that assumption is what failed twice here.
