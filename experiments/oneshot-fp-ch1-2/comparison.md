# 2×2 experiment — model vs architecture, Frozen Player ch1-2

**Question:** after weeks of gates and fixes, output is still far from the reference.
Is the bottleneck the writer model, the pipeline architecture, or both?

**Design:** same source (24 pages), same temperature (0.9), same glossary. Two axes:
writer tier (gemini-3.5-flash vs gemini-3.1-pro-preview) × architecture (current
panel-locked pipeline vs ONE freeform call that reads the raw pages and writes the
recap with no beat structure, no panel bindings, no gates).

A material accident strengthened the result: FP's OCR is completely empty (all 211
entries — the known Paddle failure), so the one-shot arms received **no transcript**.
Every system message, floor count, and the 76-hours detail in arms B/C came from the
model reading the raw page images.

## Results

| arm | writer | architecture | fact coverage | story order τ | words | read verdict |
|---|---|---|---|---|---|---|
| gold (manual, Opus-class) | — | freeform | 0.57 | 0.46 | 1048 | the target |
| **B** | pro | **one-shot** | **0.47** | **0.36** | 939 | flows; correct double time-jump; correct cliffhanger polarity; wry asides land |
| **C** | flash | **one-shot** | 0.47 | 0.37 | 982 | same *content* as B, delivered in 6-word machine-gun sentences |
| A | pro | pipeline | 0.47 | 0.33 | 1072 | panel-caption prose, dead stub beats, **wrong time-jump** (inherited from seeded outline), then **blocked by its own dialogue-delivery gate** |
| D | flash | pipeline | 0.39 | 0.24 | 1117 | the shipped best: choppy AND misordered |

(fact coverage = fraction of 303 salient reference terms; τ = story-order agreement
with the reference; both from `tools/script_compare.py`. Blind read:
`blind_read.md`, key in `blind_key.md`.)

## What each axis did

**Architecture moved correctness.** Both one-shot arms — including the *cheap* model —
fixed the defect classes the gap analysis had traced to the synopsis/outline stages:

- the double time-jump ("76 hours earlier" … "25 years later"), which the pipeline
  collapses to "flashback to 25 years ago" — arm A, with the better model, STILL got
  this wrong, because `preassign_outline_from_facts` handed it the broken structure;
- the ch2 cliffhanger polarity ("once strong enough, he CAN unfreeze them"), which
  the synopsis stage once inverted to its negative;
- story order: τ 0.24 → 0.36/0.37 at the same model tier.

**Model tier moved the prose.** B and C carry identical content; B reads like the
reference (transitions, reported-speech flow, a dry read on events), C reads like a
telegram. No measured metric separates them — which is why the by-reading rule exists.

**The pipeline actively harmed the better model.** Arm A shows the pro writer forced
back into panel-annotation register by the beat/panel structure, re-shackled to the
outline's wrong time-jump, and finally rejected by the gate stack (5 required system
lines) — the generator was upgraded and the constraint system threw the result away.

## Verdict

Both hypotheses confirmed, with a clean division of labor:

> **The architecture caps correctness; the model caps craft.** The current pipeline
> sits below a $0.10 single API call on both axes at once.

Costs: arm B was 26,650 tokens in / 1,205 out ≈ $0.10. The pipeline run it beat
makes ~40 LLM calls per chapter pair.

## What this does NOT show yet

- One-shot output has no panel bindings — a timeline/render path for freeform
  narration (post-hoc alignment) does not exist yet.
- No grounding gates ran on B/C; spot-checks found no hallucinations against the
  pages, but a systematic check (the alignment auditor, pointed at the one-shot
  text) hasn't run.
- Single sample per cell at temp 0.9; variance not characterized.
- FP only; SL ch1-5 (67-beat scale) not yet tested one-shot.

## Recommended next step

Invert the writing half: freeform whole-chapter write (pro tier) → mechanical
post-hoc alignment of narration sentences to panels → gates demoted to
instruments (identity + grounding only, one repair max). Perception, identity,
TTS, timeline, and render survive unchanged.
