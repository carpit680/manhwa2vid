# Video defect audit — FP ch1-2 and SL ch1-5

Measured 2026-08-26 against the current previews (960x540):
`preview_2026-08-26_031006.mp4` (FP, 6:23) and `preview_2026-08-26_032258.mp4` (SL, 13:01).

Method: per-frame statistics over the **whole** runtime (not sampled), ffmpeg scene
detection at the same threshold used to profile Mamoru, plus contact sheets read by eye.

---

## A. Fatal in the first and last 15 seconds

**A1. SL opens with ~19 seconds of speech bubbles on a black screen.**
0:00 "MY NAME IS SUNG JIN-WOO." on black · 0:08 and 0:10 "E-RANK HUNTER." on pure black ·
0:13, 0:15, 0:18 "LOWEST RANK AND WEAKEST HUNTER." — the *same* bubble for ~8 continuous
seconds. A viewer decides in 10 seconds; this is the worst possible opening.

**A2. Both videos end on a dead frame with no closure.**
FP ends on a "WHAT?!" bubble on black held ~5s. SL ends on a pillarboxed statue held ~8s.
No end card, no next-chapter hook, no CTA.

**A3. The chapter/title badge is drawn on exactly one frame (1/30 s).**
`render.py:77` — `motion_frames[0] = add_chapter_badge(...)`. Effectively invisible.

**A4. There is no background music at all.** `assets/bgm/` contains only `.gitkeep`.
The mix path exists (`render.py:163-179`) but never fires — 6 and 13 minutes of dry narration.

## B. Framing — half the screen carries nothing

**B1. 51-52% of runtime-weighted screen area is letterbox/pillarbox.**
Mean dead width 62% (SL) / 68% (FP); 70-75% of frames have >50% of their width carrying
no detail. SL spends 89% of runtime on panels taller than 16:9 and only 4.8% on
frame-shaped panels; FP 68% taller.

**B2. Collage pages are never split, so the camera crawls past clipped insets.**
`_find_gutter_rows` cuts only on full-width uniform rows. Modern webtoon pages are
collages: inset panels of different widths, staggered in x and y, bridged by bubbles.
SL `p0002_02` is 720x1633 containing **three** story panels plus three bubbles; gutter
detection found one cut in the whole page. FP `p0004_03` (800x5682) holds two regions.
Consequence, measured per panel: scroll mode ever shows only 30-64% of these strips,
and always clips the insets at the frame edge.

**B3. 46% of all frames have text clipped by the frame boundary** — both titles.

**B4. A bubble or caption dominates the frame.** FP: 31% of frames have a solid bright
blob covering >20% of the screen (p90 of the largest blob = 54% of the frame). SL: 18% / 35%.

**B5. Source art is only 720-800 px wide.** At 1080p, width-fitting is a 2.4-2.67x upscale;
softness is inherent at that output size regardless of framing.

## C. Editing rhythm vs the reference

| | Mamoru | FP | SL |
|---|---|---|---|
| cuts/min | 16.25 | 14.91 | 11.58 |
| median shot | 2.87s | 3.83s | 5.00s |
| p10 | 0.95s | 1.67s | 2.27s |
| shots < 1.5s | 22.2% | 6.0% | **0.0%** |
| shots < 1s | 10.5% | 1.2% | **0.0%** |
| longest | 16.4s | 10.3s | 18.1s |

**C1. We have no short shots.** A fifth of Mamoru's cuts are accent beats under 1.5s; we
have essentially none. `align.min_shot_seconds: 1.0` plus the under-floor merge deletes
exactly that class of cut.

**C2. SL holds a single image for up to 14.2s (timeline) / 18.1s (measured on screen).**

**C3. The action climax plays over two stills.** SL beat 28 — six sentences covering the
beams obliterating the temple floor, the raid party vaporized, ash choking the cavern,
hunters scattered and crying — runs 28.4s across two panels at 14.18s each.

## D. Sentence→panel matching

**D1. SL matches only 49% of sentences to a panel** (113 of 230); the other 117 hold the
previous shot. FP manages 76%. The hold-on-uncertainty rule was a deliberate choice, but
at a 49% match rate it means half the video's picture is standing still.

**D2. Most of the art never reaches the screen** — 44% of SL's story panels and 56% of FP's.

**D3. Longest hold run: 6 sentences (SL), 4 (FP).**

## E. The timing contract is estimated, not measured

**E1. 92-94% of sentence timings are estimated, not measured.** Kokoro returns chunks
holding up to 7 (FP) and 9 (SL) sentences; only 7 of 88 and 13 of 230 sentences have their
own measured duration. `_subdivide_segments` splits the rest by character count.

**E2. That proxy is worth ~1.5-1.7s of drift.** Observed chars/sec varies by 26% (FP) and
38% (SL) of the mean, and the longest chunks run 22.9s — so a cut inside one can land
~1.5s from where the sentence actually falls, over half a Mamoru shot.

This contradicts the premise recorded in `script/match.py` ("the TTS sidecar supplies
sentence i's measured seconds"). The identity holds; the *granularity* does not.

## F. Audio

**F1. True peak is +0.30 dBTP (FP) and +0.35 (SL)** — above 0, so it clips on transcode.
Should be ≤ -1.0 dBTP.
**F2. LRA 2.3 LU** — very flat dynamics.
Good: -15.5 LUFS integrated (fine for YouTube), 223 / 222 WPM against a 220 target, and
no silence gaps over 1.2s.

## G. The QA framework does not cover any of this

**G1. Both projects rendered while gates were FAILING.** FP: `name-integrity` fail plus
`dialogue-delivery` fail (5 beats dropped a required system message the panel prints).
SL: `name-integrity` fail. Roughly 25 warns each on top.

**G2. No gate exists for any visual defect** — dead space, bubble dominance, clipped text,
opening/ending frames, shot-length distribution, or match rate. `no-blank-panels` passes
happily; `dwell-over-limit` warns and ships.

**G3. Some failures are false positives, which trains you to ignore the gate** —
SL's "Rank Hunter" is a fragment of "E-Rank Hunter"; FP's "Earth Jun-Ho" comes from the
correct sentence "the affluent modern Earth Jun-Ho sees outside his window".

## H. Smaller content issues

- **H1. Meaningless frames**: extreme zoom on Korean SFX lettering (FP 0:51), an
  uncontextualised shoe/sand close-up (SL 11:47).
- **H2. Frames showing fragments of two different panels** (FP 6:11, 6:20; SL 0:47, 2:59, 4:05).
- **H3. Dense-text panels rendered too small to read** (SL 4:49, 7:45).
- **H4. SL runs five chapters with no chapter divider** of any kind.
- **H5. Glossary gap**: "Carthenon Temple" missing from SL's glossary.

---

## Root-cause ranking

1. **Under-splitting of collage pages (B2)** — one defect feeding many. It produces the
   bubble-only openings (A1), the clipped text (B3), the two-panel fragments (H2), and it
   degrades matching (D1), because the matcher is offered a page containing three
   different moments and cannot claim it for one sentence.
2. **Webtoon art in a 16:9 frame (B1/B5)** — a genuine format conflict, not a bug. Half
   the screen is the cost of showing tall art whole. Worth an explicit compositional
   decision rather than a blurred backdrop.
3. **Hold-on-uncertainty at a 49% match rate (D1/C3)** — the failure direction was chosen
   deliberately, but the rate makes it the dominant behaviour rather than the fallback.
4. **Sentence timing granularity (E1/E2)** — smaller than it looks, but it is the reason
   cuts drift from speech even when the matching is right.
5. **Missing production furniture (A2/A3/A4)** — cheap to fix, disproportionate effect.
