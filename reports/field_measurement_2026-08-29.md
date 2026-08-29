# The field, measured with our own detectors

2026-08-29. Six competitor channels catalogued (864 videos), twelve videos pulled as
sections and measured with `manhwa2vid.measure.*` — the same code that gates our
renders, so every number here and every number in `qa.render.json` mean the same thing.

Corpus: `reference/corpus/` (gitignored). Tool: `tools/measure_corpus.py`. Raw:
`reference/corpus/corpus_metrics.json`.

## Method and its limits, stated first

- **Sections, not whole files.** Opening 120 s, 240 s from the middle, closing 70 s.
  A 5.66 h video costs ~7 minutes of download. Anything needing full runtime is not
  claimed.
- **Auto-captions have no punctuation.** Six of twelve transcripts carry ≤0.2 sentence
  terminators per 1000 words. For those, `mean_sentence_words`, `under_8w_pct` and
  `quoted_per_1k` are meaningless — a 37,382-word transcript reads as one sentence.
  Only punctuation-free metrics (wpm, verbs/1k, second-person, epithets) are compared
  across the full twelve.
- **n = 12.** Enough to establish ranges and kill theories, not to prove causation.
  Every correlation below is reported with that caveat attached.

## 1. Catalogue: what the channels actually publish

| channel | videos | median views | max | median duration |
|---|---|---|---|---|
| Manhwa Outpost | 324 | 84,000 | 6,100,000 | 2.86 h |
| Tobs (ManhwaCapped) | 254 | 240,000 | 1,600,000 | 2.79 h |
| Manhwa Recap Zone | 182 | 70,000 | 1,100,000 | 1.73 h |
| Mamoru Manhwa | 272 | 332,500 | 5,200,000 | 2.37 h |
| Manga King | 42 | 57,000 | 323,000 | 1.82 h |
| Manhwa Vault | 47 | 3,000 | 63,000 | 1.72 h |
| Isekai Central (original IP) | 15 | 10,000 | 94,000 | 2.34 h |

Independently reproduces the co-work teardown (Mamoru median 332,500 vs its 334K;
Outpost 324 videos; Zone 182). `Tobs Manhwa` is ManhwaCapped renamed.

**The biggest hits are the shortest videos.** Outpost's 6.1 M runs 1.01 h against a
2.86 h channel median; Zone's 1.1 M runs 0.93 h against 1.73 h. "Longer is better" is
not supported.

## 2. Editing and audio — we are inside or ahead of the field on every axis

Mid-section (steady state), our FP render for comparison:

| metric | field median | field range | ours (FP) |
|---|---|---|---|
| LRA | 2.25 LU | 1.20 – 3.90 | 2.1 |
| integrated | −19.8 LUFS | −25.9 … −14.7 | −14.5 |
| true peak | −4.89 dBTP | −6.72 … **+0.65** | −1.40 |
| cuts/min | 13.5 | 4.0 – 24.0 | 18.4 |
| median shot | 4.13 s | 2.03 – 11.27 | 2.82 |
| pauses >150 ms/min | 6.7 | 1.2 – 28.2 | 1.5 |
| F0 spread | 10.3 st | 8.1 – 16.9 | 7.6 (am_adam) / 16.0 (af_heart) |

Three things follow.

**The `audio-lra` band is confirmed by the whole field.** It was re-derived from
Mamoru's track alone (2.50 LU) to 1.5–4.5; the field runs 1.2–3.9. The "flat audio
defect" the spec chased never existed — flat is what this format sounds like, across
every channel measured.

**We are technically ahead, not behind.** Our true peak is safer than the 6.1 M hit,
which clips at **+0.65 dBTP**. We cut faster than the field median. Our loudness sits
at the platform normalisation point while most of the field uploads 5 dB quieter.

**There is no single winning formula.** The two largest videos measured (6.1 M and
5.2 M) disagree on nearly everything: 16.8 vs 24.0 cuts/min, −14.7 vs −19.3 LUFS,
4.0 vs 11.2 pauses/min. Consistent with the teardown's outlier-lottery finding.

## 3. Script — one clear gap, one already won

Metrics valid on all twelve (no punctuation required):

| | field median | field range | ours FP | ours SL |
|---|---|---|---|---|
| wpm | **218.4** | 177.5 – 239.7 | **179** | 232 |
| dialogue verbs /1k | 8.63 | 0.00 – 25.96 | **26.18** | 18.31 |
| second person /1k | 1.25 | 0.00 – **17.75** | 3.74 | 1.53 |
| casual epithets /1k | 0.20 | 0.00 – 2.65 | 0.00 | 0.38 |

**Dialogue density is won.** FP's 26.18/1k is the highest figure in the corpus,
above every competitor including the 1.6 M and 5.2 M videos. The density work landed.

**Speaking rate is now our weakest number.** At `kokoro_speed: 1.15` we deliver 179
wpm. Every video above 1 M views runs 202–232. The only two corpus videos near 178
are the two weakest performers (95 K and 3 K views) — n = 2, so directional only.
Note the rate was chosen by ear *while the pitch-shift and echo artefacts were still
in the chain*; both are now removed, which makes "was it the speed or the artefacts?"
a testable question rather than a preference.

**Second person is the one clear writing gap.** Mamoru's 5.2 M video addresses the
viewer 17.75 times per 1000 words — 4.7× our FP and 14× the field median. It is an
outlier within the field too, which is exactly why it is interesting.

## 4. Packaging — the formula does not survive a within-channel test

Cross-channel, the teardown's pattern appears: every channel writes titles to a median
of **exactly 70 characters** (the YouTube truncation limit), none names the source
manhwa, 36–55 % carry a two-clause reversal. Ours is 55 characters, names the source,
and has none of the devices.

But testing median views of videos **with** vs **without** each feature, within the
same channel:

| feature | Manga King | Outpost | Tobs | Vault | Zone |
|---|---|---|---|---|---|
| reversal clause | 1.37× | 0.83× | 0.94× | 0.76× | 0.96× |
| ≥2 CAPS words | 0.84× | 1.27× | 0.95× | — | 0.88× |
| part-numbering | — | — | — | **2.91×** | — |

No consistent direction. Four of five channels sit below 1.0 on the reversal clause,
the formula's centrepiece. And part-numbering — which cross-channel comparison makes
look fatal, because the channel using it is the smallest — performs **2.91× better**
inside that channel. That is a textbook confound, and it was in an earlier draft of
this analysis until the within-channel test killed it.

**Conclusion: title micro-optimisation is not evidence-backed.** Two categorical facts
survive because they have no within-channel variance to test: write to 70 characters,
and do not name the source in the title.

## 5. Corrections this measurement forced

- **The redundancy lint cannot be built on our OCR.** Narration↔panel-OCR overlap
  measured 0.00, which reads as "clean" — until coverage was checked: **OCR extracts
  zero text across all 519 panels** in both projects. The 0.00 was empty data.
  `read.py` already treats `ocr.json` as optional and reads pixels instead.
- **The prosody gap was overstated.** An earlier reading of one Mamoru mid-section
  (24 pauses/min vs our 1) suggested a large phrasing deficit. Across the field the
  median is 6.7/min with a 1.2–28.2 range; our 1.5 is low but inside it, and the
  6.1 M hit's opening pauses *less* than we do (0.5/min).
- **A tool bug, caught before it published.** `shot_stats` takes shot *lengths*;
  passing cut *timestamps* reported a 58-second median shot inside a 120-second clip.

## 6. What this means for "better than every one of them"

The pipeline is not technically behind the field — on audio and cut rhythm it is ahead,
and on dialogue density it leads outright. The remaining differences are **structural**,
not qualitative:

1. **Runtime.** 6–11 minutes against a field of 0.93–5.66 h. Nothing else in this
   report is as large. It is also the one that invalidates measurement at our current
   scale: we have never observed our own pipeline at 60+ minutes.
2. **Speaking rate.** 179 wpm against a 218 field median.
3. **Second-person address.** 3.74/1k against a 17.75 ceiling.
4. **Title length and source-naming.** Categorical, cheap, uncontested.

Everything else the research proposed — the reversal-clause formula, CAPS density,
part-number avoidance, the redundancy lint, emotion-per-beat — is either unsupported by
this data or unmeasurable with what we have.
