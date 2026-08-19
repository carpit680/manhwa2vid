# Why the pipeline isn't Mamoru yet — evidence from Frozen Player ch1–2

Three-arm controlled comparison on identical source material (2026-08-19):

- **Arm A** — Mamoru Manhwa's actual video (`youtube.com/watch?v=drpDZ2HUGn8`, ch1-2
  segment 1:46–5:57, transcript in `mamoru_fp.en.srt`)
- **Arm B** — Claude reading all 277 panels in one context and writing
  `ch1-2_gold_script.md` (25 beats, ~1,100 words) before seeing any pipeline output
- **Arm C** — the full pipeline (scout→ocr→cast→script) on the same panels, same
  glossary, `gemini-3-flash-preview` vision / `gemini-3.5-flash` text

## The headline numbers

| | Mamoru (A) | Claude gold (B) | Pipeline (C) |
|---|---|---|---|
| words for ch1-2 | 979 | ~1,100 | ~1,150 |
| narration units | 82 sentences | 25 beats | **18 beats (config cap)** |
| beats shipped from the fallback path | — | — | **13 of 18 (72%)** |
| story panels shown | ~half, cropped | n/a | all 211 (hard gate) |
| implied runtime @ min dwell | 4.2 min | n/a | **8–9 min** |

Every hard QA gate was green and the run exited 0. **A green run still produced a
script in which the alignment audit had replaced 72% of the narration with outline
text.** The safety net was the author.

## Where each observed defect was born (verified layer by layer)

| Defect in shipped script | Born in | Evidence |
|---|---|---|
| "Khali… yielded his spot", "Skaya… stayed behind" (both false) | **synopsis** | fabrications sit in `named_cast` roles; flowed outline→fallback→ship |
| ch2 cliffhanger missing (friends CAN be freed — the point of the chapter) | **synopsis** | card p0024_01 has `[YOU ARE ABLE TO REMOVE THE SEAL…]` verbatim; `plot_facts` compressed it to its negative ("unable to free") |
| "flashback to twenty-five years ago" (it's 76 hours) | **chapter read** | project-scoped read normalized the double time-jump; `last_flashforward_panel` empty |
| comfort-scene joke flattened to "tears of gratitude" (punchline is "NOT!") | **narration** | cards carried the exchange + speakers correctly, incl. the NOT panel |
| dust brushed off "the swordswoman" (it's Skaya) | **vision** | adjacent cards contradict: p0023_09 says Skaya, p0023_13 says swordswoman |
| "raises his mask" (he takes it off), "preparing for the next hunt" | **narration** (one of the 5 surviving beats) | invention under compression; audit missed it |

Vision errors exist (~5% of cards) but the two story-breaking defects were born in
the synopsis and shipped because the fallback path routes around the writer.

## The three structural causes

**1. The beat budget does not scale with input.** `script.max_beats: 18` was tuned on
a 53-panel chapter (2.9 panels/beat). Here it met 211 story panels: 11.7 panels/beat.
At that compression every beat summarizes a dozen panels in ~45 words, the adversarial
verifier correctly finds claims those panels don't support, rewrites can't fix a
budget problem, and the grounded fallback fires — 13 times. `words_per_panel` fell
below its own band (5.5 vs 6.0 floor). Mamoru uses 82 sentences for this material;
the Claude gold uses 25 beats. The pipeline was forced to tell it in 18.

**2. Panel conservation conflicts with the reference format.** 277 panels ×
1.5–2.0 s minimum dwell = 8–9 minutes of video; Mamoru covers the same chapters in
4.2 minutes at 234 WPM by showing roughly half the panels, cropped and zoomed. The
target format DROPS panels. Ours may not — so at fixed WPM the video must either
drone (pad dwells) or strobe. This is the arithmetic behind "it mostly feels like a
stringed narration of image descriptions": narrating every panel IS the description
of every panel.

**3. The synopsis is a lossy bottleneck feeding an over-eager fallback.** plot_facts
is the only channel through which whole-story meaning reaches the outline, and it is
prose-compressed: reveals lose their polarity, cast roles grow invented backstory.
When the audit then rejects narration wholesale, that lossy text is what ships.
No gate notices that the last panels' verbatim reveal never appears in any beat, and
no gate fails a run where most of the script came from the fallback path.

## What "Claude did it manually" actually consists of

Arm B differs from Arm C in two separable ways. Perception: reading panels directly
was ~100% accurate on attribution vs ~95% for cards — a small edge. Editorial: the
gold DROPS ~40% of moments, keeps the reveal for last, tracks what the chapter means
("seal, not tomb"), and never needs a fallback. The editorial difference is the gap;
the perceptual one is minor. Mamoru's video confirms it: he reorders scenes, pulls
future exposition backward, and writes synthesis lines that appear in no panel
("the plan writes itself: climb the tower, get the magic, melt the ice, bring them
home").

## Answer to "better models, larger context, or new architecture?"

- **Not better vision models.** The cards contained the critical facts — the seal
  reveal verbatim, the hardest speaker attribution correct. A tier ablation
  (flash vs 3.1-pro, 3 runs each on the two failing windows) was harness-limited
  (single-card responses in 10/12 calls — itself a response-shape flakiness worth
  fixing) but the one clean run captured the reveal. Upgrading vision attacks the
  ~5% card noise, not the shipped defects.
- **Not larger context.** Narration already runs whole-story in one call; the writer
  saw everything and still had its output discarded 13 times by the audit loop.
- **Architecture, four changes, in this order:**
  1. **Scale the beat budget** from story-panel count and the words-per-panel band
     (211 panels → ~25–30 beats). Cheap, unblocks everything else.
  2. **Add a curation stage**: rank panels within each beat, show the strongest
     ~50–60%, drop the rest. Resolves the dwell/WPM conflict; enables 4–6 min
     chapters at 237 WPM. This is the single change that separates "slideshow of
     everything" from Mamoru's format.
  3. **Protect reveals from synopsis compression**: pivotal panels (system messages,
     final-panel exclamations) must reach the outline as quoted evidence, and a gate
     should fail the run when the last story panels' content appears in no beat.
  4. **Recalibrate the audit loop**: judge support at beat level when beats carry
     many panels; cap the fallback at a fraction of beats and fail loudly beyond it.
     A run where the safety net writes 72% of the script must not exit green.
- **Writer-tier text model: worth one A/B later.** 3 of the 5 surviving narration
  beats contained inventions (mask direction inverted, "preparing for the next
  hunt"). After fixes 1–4 make narration actually ship, compare gemini-3.5-flash
  against a pro-tier writer on the same evidence.

## Also fixed/learned during this experiment

- Resolution independence: `page_width` is now a ceiling (800px native honored);
  split thresholds scale with width; gutters and blank slivers detected by
  UNIFORMITY, not whiteness — the dark-page title exposed both, and the fix also
  improved Solo Leveling (its dungeon pages had been shipping as unsplit strips).
- Identity generalized: MC resolved as `char_seo_jun_ho` from the glossary alone,
  27 bible entries, all cast gates green, zero Solo Leveling leakage.
- Mamoru's register: 234–237 WPM, ~12 w/sentence — our measured profile holds. The
  meme-slang is concentrated in the opening hook, not the body.
- Glossary lifecycle: edits after `init` don't reseed the bible until the cast
  stage; scout ran with 0 profiles. Harmless here, worth a re-seed hook.
