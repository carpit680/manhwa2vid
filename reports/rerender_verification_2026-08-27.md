# Re-render verification — Frozen Player ch1-2, 2026-08-27

`preview_2026-08-27_054434.mp4` — 6:22, 106 planned shots, 100 distinct panels.
First render with the chapter badge and end card removed.

Method: every number below is measured over the **whole** runtime, and every claim that
a frame "looks like" something was checked by opening the frame. Two of the conclusions
here reverse a measurement that looked convincing until it was looked at.

## Fixed, and holding

| Audit item | Then | Now | Reference |
|---|---|---|---|
| C. editing rhythm — median shot | 3.83s | **2.43s** | 2.87s |
| C. shots under 1.5s | 6.0% | **19.8%** | 22.2% |
| C. cuts/min | 14.91 | **16.67** | 16.25 |
| B1. mean dead width | 68% | **62%** | 74% |
| F. true peak | +0.30 dBTP | **−1.35 dBTP** | ceiling −0.8 |
| E. timing contract | estimated | runtime 381.60s vs timeline 381.58s (**+0.02s**) | — |
| H1. meaningless frames | present | **0 of 100** shown panels are content-free | — |
| A1. opening | 19s of bubbles on black (SL) | opens on artwork, luma 155, 0% bubble | — |

All six render gates pass. The four frame classes flagged from screenshots stay at zero
runtime. Camera mix is 59.4% letterbox (whole panel, blurred bars) / 40.6% fill-frame /
**0% strip scroll** — the "everything is scrolling" complaint is structurally gone; the
worst-motion shot in the video was opened and is a slow push-in on full-bleed art.

## Not fixed

**1. The video now ends on the exact frame the audit called defect A2.**
Removing the end card re-exposed it: the last 18.6 seconds are the "WHAT?!" starburst
bubble on black. The end card had been covering this, not solving it. Two causes stack:
the closing paragraph's panels end on a shock-reaction bubble panel, and that panel is
scheduled **twice in a row**.

**2. Six runs of adjacent duplicate panels — cuts that do not exist.**
p0024_02 (18.6s), p0020_10 (14.4s), p0019_01 (12.3s), p0015_02, p0017_05, p0012_01. The
planner thinks it scheduled 106 shots; the viewer sees 100. The longest hold is 18.6s,
not the 16.7s the timeline reports, and neither the dwell limit nor the burst guard can
see it because both read the planned entries. The render gate is unaffected — it scene-
detects the finished file — so this is invisible to every current check.

**3. Bubble- and text-dominant frames are still frequent, and the detector cannot find them.**
Roughly a quarter of sampled frames are dominated by text: "BUT WE TRUST YOU." on black,
"BUT THE WORLD" in a white box, "ALL THE PLAYERS HEARD THE SAME EXACT MESSAGE.",
"I ABSORBED IT!". `is_text_only_panel` flags **0 of 100** shown panels, because it
requires a large *bright* region (`bright > 0.2 and mid < 0.15`) and these are the
inverse — small bright text on a large dark field.

The obvious repair does not work, and this was tested rather than assumed. A bimodal
rule (ink + ground > 0.80, mid-tone < 0.06) flags 7 panels, but opening all 7 shows
**3 are real art** — a face with a bubble, a hooded figure, a mouth close-up. Cropping
to content first does not separate them either: verified text panels land at mid-tone
0.013–0.051 and verified art panels at 0.037–0.052, fully overlapping. The art in these
panels is line work on flat fills, which is tonally identical to text on flat fill.

**No brightness-based test can distinguish "bubble on black" from "silhouette on black."**
This is the same wall the `bubble-dominance` gate hit this morning. A working detector
needs a non-tonal signal — glyph structure (small connected components of consistent
stroke width in a row), or a panel-level judgement from the vision pass that already
reads every panel.

**4. Clipped text unchanged at 46.0%** (audit 46%, reference 43.9%). Within the
reference's own rate, so arguably at the floor for a moving camera over bubbled art.

**5. Integrated loudness −16.38 LUFS against a −14 target.** Not caused by the end-card
removal (the previous render measured −16.40). `loudnorm` in `linear=true` mode will not
apply gain that would breach TP=−1.5, and this material's crest factor stops it 2.4 LU
short. Reaching −14 needs gentle compression before normalization, not a config change.
YouTube only turns audio down, so this ships ~2.4 dB quieter than a channel that
compresses.

## Correction to an earlier claim

This morning's note said the `bubble-dominance` detector is "substantially measuring flat
pale area, not bubbles". That was drawn from the worst-scoring frames, which biased the
sample toward large pale walls. The contact sheet shows genuinely bubble-dominant frames
are also common. Both statements about the *detector* stand — it is too imprecise to gate
on — but the *problem* it points at is real and visible, which item 3 above covers.

---

# Follow-up, same day: the three fixes, and a render bug found on the way

## The bug that invalidates the analysis above

`upscale_panels` cached 2x images by **file presence alone**. Panel ids are POSITIONAL
(`pNNNN_MM`), so re-running the panels stage reassigns them. Frozen Player was re-split on
2026-08-26 19:53; its upscale cache is dated 12:14. **64 of 172 cached upscales held a
completely different picture from the panel of the same name**, and every render since —
including both analysed earlier in this report — composited the old image while the
timeline named the new one. Solo Leveling was affected too (42 of 271).

Nothing downstream could see it. The timeline, the QA gates, the durations and the
runtime were all self-consistent, and all six render gates passed. It surfaced only when
a frame was opened and compared against the panel the timeline claimed was on screen: the
video showed a speech bubble at a timestamp whose panel is a figure in a coat.

Fixed with two independent checks — the panel must not be newer than its cache, and the
cache must be exactly `scale` times its source's size. Both titles self-heal on their next
render (FP's redid 65). **Treat any conclusion about specific frames in earlier renders as
unreliable.**

## The detector

`is_text_only_panel` asks a tonal question and cannot work on whole panels: it flags 0 of
FP's 100 shown panels, because it needs a large BRIGHT region and half the offending
frames are white type on black. No tonal rule can work — after cropping to content,
verified text panels measure mid-tone 0.013-0.051 and verified art panels 0.037-0.052,
fully overlapping. Line art on flat fill IS tonally identical to text on flat fill.

`regions.text_content_ratio` asks a geometric question: find lettering by shape (glyph-
sized ink in rows sharing one height and one stroke width), grow it to the bubble that
holds it, report that as a fraction of NON-background pixels. Four guards each killed a
specific false positive found by opening the panel — flat interior, bounded hull, convex
blob, and a hull that adds no content beyond the blob.

Validated on all 607 panels of both titles with every flagged panel opened by eye: at 0.82
it flags 10, all genuine lettering, **zero false positives**. Lowest true text 0.853,
highest true art 0.778; both pinned as numbers in tests.

## Results on FP ch1-2

| | before | after |
|---|---|---|
| shown panels that are lettering/void | 5 (**24.5s**) | 0 (**0.0s**) |
| closing shot | "WHAT?!" starburst | artwork ("AH, SHIT.") |
| distinct panels shown | 100 | 100 |
| runtime | 381.58s | 381.58s |
| edge-clipped text | 46.0% | **38.9%** |
| median shot / <1.5s / cuts-min | 2.41s / 23.0% / 16.67 | unchanged |

Six render gates pass, zero warnings.

## What is still open

**Bubble-dominant WINDOWS.** Panel-level exclusion cannot reach a camera window inside a
tall art panel. "ARE YOU TELLING ME THE FROST QUEEN WASN'T THE END?!" is a crop of
p0016_16, a tall strip that is mostly art. Two such frames remain in a 24-frame sample.
The fix is to score candidate camera windows with `text_content_ratio` — filed as its own
task. Note the panel-tuned 0.82 threshold under-reads on rendered frames, because the
blurred pillarbox counts as content; recalibrate on frames before gating.

**Six invisible cuts remain** where a beat has more narration than panels and there is no
unclaimed panel to advance to. Reported by the new `no-invisible-cuts` gate.

---

# Camera windows (task #80)

Panel-level exclusion cannot reach a window chosen *inside* a tall art panel. The camera
picked those windows with `effects._bubble_boxes`, a brightness test that found "large
pale region", not "bubble" — it missed the jagged "WHAT?!" starburst entirely, which,
being full of high-contrast spikes, then **attracted** the window instead of repelling
it, while flagging white walls and steering the camera off real art. Replaced with the
validated `regions.text_regions`.

**Measured before changing anything**, over FP's 42 fill-frame panels, counting windows
where lettering covers more than 30% of the screen: **21 with no down-weight, 10 at the
old 0.15 weight, 14 at 0.40, 18 at 0.55.**

## Two corrections the frames forced

**Sound effects are not speech bubbles.** SFX is painted ON the art, exactly where the
action is, so suppressing it walks the camera away from the subject. At weight 0.15 the
opening reframed off Frozen Player's only character onto an empty door. Three ways to
separate SFX from bubbles were tried and measured: containers-only (20 windows — most
bubbles have no detectable container), a size filter (12–16), and a flat-ring test (21).
None gave both. It is a genuine trade-off, and **0.40** is the middle: most of the gain,
subject still framed.

**The opening-shot gate was measuring the wrong thing.** It read the Frost Queen's pale
hair as a 34%-of-frame "bubble" and FAILED an opening that had improved — lettering over
the first four seconds fell 48% → 30%, and the second shot moved off its speech bubble
onto her face. It now measures lettering with the validated detector at a 0.55 band; the
blob number is still recorded but decides nothing.

## Net effect on the video

| measured with the validated detector | old camera | new camera |
|---|---|---|
| frames where lettering covers >30% of screen | 16.8% | **14.1%** |
| frames where lettering is sliced at the frame edge | 47.6% | 49.0% |

A modest net gain, not a transformation: the remaining text-heavy frames are windows on
panels that are genuinely mostly bubble. The opening's subject is framed lower than
before, though fully visible. Six render gates pass. **If the old opening framing is
preferred, revert `video.bubble_salience_weight` to 1.0** — that keeps the detector for
edge-slice avoidance and the panel test while leaving salience untouched.

Two performance fixes were needed and are verified to leave the detector's output
identical: cache the container search by tone, and break out of the row grouping once
past its vertical bound (it was O(n²), and a 22000px strip carries tens of thousands of
glyph-sized components — two camera tests went 0.4s → 30s, now 2s).
