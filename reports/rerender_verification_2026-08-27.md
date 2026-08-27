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
