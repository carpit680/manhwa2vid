# Where we still differ from the reference channel

Measured 2026-08-26 on the current renders (FP `preview_..._164851`, SL `..._165934`)
against `reference/frozen_player/mamoru_fp_video.mp4` and his ch1-2 transcript, using
the same detectors for both sides.

## Closed — no longer a gap

| | reference | ours |
|---|---|---|
| median shot | 2.87s | 2.30s (FP) / 2.40s (SL) |
| shots < 1.5s | 22% | 32% / 25% |
| shots panning > 0.25 frame-heights | 0% | 6% / 5% |
| max burst of consecutive < 1.2s shots | 3 | 3 |
| true peak | — | −1.38 / −1.30 dBTP |
| edge-clipped text | 43.9% | 45.7% / 44.4% |

## Open gaps, largest first

### 1. Narration is 48% wordier and flatter (biggest remaining gap)

Same two chapters:

| | Mamoru | ours |
|---|---|---|
| words | 963 | **1429** |
| mean sentence | 11.7w | **15.7w** |
| sentences under 8 words | 29% | **11%** |
| dialogue verbs / 1k | 20.8 | **11.9** |
| quoted dialogue spans / 1k | 1.0 | **0.0** |

His rhythm comes from short punches between longer sentences — *"He dodges by a hair."*
*"The ice statue just moved."* *"It's Shimuk."* *"The legend has awakened."* We almost
never write one. He also reports speech twice as often, and quotes a line outright about
once per thousand words; we quote nothing.

Fix direction: a sentence-length **distribution** target (not just a mean), and a
dialogue-verb floor, enforced in the style scorecard rather than asked for in the prompt
— prompt-only voice changes have failed twice in this project and are recorded as such.

### 2. Bubble-dominant frames — FP 33.9% vs his 21.9%

His frames always compose bubble **with** art; he never shows a bare bubble. Ours came
from gutter bands that contain nothing but a bubble. Two fixes are now in (band merge at
split, art substitution at plan time) but **neither is in the delivered videos** — the
first needs a re-split, the second a TTS+render re-run.

### 3. He uses blurred pillarbox; we eliminated it

Sampling his video: a good third of his shots are a tall panel centred with blurred
side bars (0:40, 0:49, 1:25, 2:10, 2:19 in the sample sheet). We now fill the frame on
every shot. That was the user's explicit call and it fixed the dead-space complaint —
recording it here only because "no bars ever" is *further* from the reference than the
reference is, and a tall money-shot panel may deserve to be shown whole.

### 4. Narrator persona: the tour-guide "we"

He addresses the viewer to move them through the story — *"we have to go back 25 years"*,
*"we're at a museum exhibit"*. Three instances in two chapters, and they are what makes
it feel hosted rather than read. We have zero. (The style profile's near-zero
first-person figure counted *"I"*, which he also avoids; this is a different device.)

### 5. Structure

- **Intro**: he opens cold, straight into the scene, no title card and no greeting. We
  open on a 3s title badge over the first shot. Cheap to change if wanted.
- **Outro**: was a static card; now written into the narration (this session). Not yet
  in a rendered video.
- **Chapter dividers**: his long compilations run chapters together with no divider —
  matching what we do, so this is not a gap after all.

### 6. Source resolution

His art is visibly sharper at 1080p. Our sources are 720–800px wide; ESRGAN 2× closes
much of it but not all. Nothing further to do without better scans.

## What I could not measure

The reference file on disk is a 5.3-hour binge compilation with **no subscribe ask
anywhere** — I searched all 75,421 transcript words. Its outro technique, the thing the
user described, is not in this file. The outro implemented this session follows the
user's description, not a measured sample; getting a real per-episode video would let us
check the wording and placement against the real thing.
