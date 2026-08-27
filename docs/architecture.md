# manhwa2vid — architecture

How a folder of manhwa pages becomes a narrated recap video, as the code actually works
today. Replaces `architecture.html`, which described the panel-locked script pipeline
that was deleted on 2026-08-26.

The target is the Mamoru Manhwa channel's format. Numbers quoted as "measured" come from
running detectors over that channel's own video and over ours; the method for each is in
`reports/` and `tools/`.

---

## 1. Stages and the artifact contract

Stages never pass data in memory. Each reads its inputs from disk, writes its outputs,
and appends itself to `checkpoint.json`. `models.project_paths()` is the single source of
truth for every path — add one there, never inline.

```
ingest    ingest/          pages/*.png + pages/manifest.json
panels    panels/split.py  panels.json          (per-panel PNG crops)
ocr       ocr/extract.py   ocr.json, scene_cards.json, panels.story.json,
                           excluded_panels.json
script    script/          chapter_facts.json, script.freeform.md, script.audit.json,
                           script.alignment.json, script.shotlist.json,
                           script.json, script.draft.md
tts       tts/engine.py    audio/beat_NNN.wav + .segments.json, timeline.json
render    video/render.py  output/preview_<stamp>.mp4 | output/final.mp4, qa.render.json
export    export/          SRT, thumbnail, metadata
```

Every stage is idempotent by artifact existence: if its output exists it prints
"Using cached …" and returns. `--force` re-runs it, and a stage that invalidates
downstream state deletes those files explicitly (e.g. `split_panels` unlinks
`panels.story.json` / `excluded_panels.json`). When adding a stage, mirror that: cache on
your own artifact, delete anything downstream your output would falsify.

Two human checkpoints are enforced in `pipeline.run_stage`: **TTS** refuses to run until
`script.final.md` exists or `checkpoint.script_approved` is set; **render** refuses
without `timeline.json`, and also refuses over any failed upstream QA gate unless
`--force-past-qa`.

### Project vs series

A *project* is one recap (one chapter range): `projects/<title-slug>-ch<range>/`.
A *series* is shared across projects of the same title:
`projects/<title-slug>/series/` (see `models.series_paths`) and holds the character
bible used for vision cast context. Both resolve relative to `config.find_repo_root()`,
which walks up looking for `config.yaml`. `projects/` is gitignored; tests build
throwaway projects in `tmp_path`.

---

## 2. Script generation — story-first

`script/story_first.py::generate_story_first_script` runs five passes. The ordering is
the architecture: **the narration is written first, and the panels are bound to it
afterwards.** The reverse (write per-panel, assemble later) is what the deleted pipeline
did, and it produced panel captions instead of a story.

1. **read** (`script/read.py`) — one vision pass over the pages recording what they
   literally show: verbatim system messages, plot-carrying dialogue, time markers, cast.
   Writes `chapter_facts.json`. **The writer never sees this file** — it exists so the
   audit has something independent to check against.
2. **write** (`script/freeform.py`) — one creative pass over the raw pages, in windows of
   `script.freeform_max_pages_per_call`, producing narration as prose. Word budget scales
   with chapter count.
3. **audit + revise** (`script/audit.py`) — an adversarial pass lists claims the pages
   do not support; exactly one revision is allowed, and it is accepted **only if the
   finding count shrinks**. Survivors land in `script.audit.json` and raise a WARN gate.
4. **outro** (`script/outro.py`) — two closing sentences that continue the last story
   line into the subscribe/notifications ask. Shape is checked absolutely (≤2 sentences,
   no marketing vocabulary, ask present) with a fixed closing as fallback.
5. **align + match** (`script/align.py`, `script/match.py`) — paragraphs become beats
   bound to panels, then sentences are matched to the panels that depict them.

### Identity: `glossary.json`, not accumulated state

`glossary.json` is a flat, human-editable `name -> aliases` map. It is created empty at
`init` and populated by the read pass (`read.merge_cast_into_glossary`), which **never
overwrites a human edit** — existing entries are only extended.

This replaced a scout/quest/consolidate/link machine that accumulated per-panel identity
state across chapters. That state drifted: it once elected a protagonist called "large
orange demon" and pronounced the lead "they" off 174 polluted descriptors. A flat map
cannot drift that way, and when it is wrong a person fixes it in one line. The
`name-integrity` gate compares narration names against it (advisory — it has known false
positives around grade prefixes like "E-Rank Hunter").

---

## 3. The editing layer — what is on screen, and for how long

This is the half that decides whether the video is watchable, and it is all downstream
of the narration.

**Shot list** (`script/match.py`). Per time block, panels are shown to a vision model in
windows of `align.match_window_panels` (16 — id binding measurably drifts beyond that,
+3 positions at 59 images) and asked which panels *depict* each sentence. Claims are
filtered by a longest-increasing-subsequence pass so sentence order and panel order
agree; a contradiction is dropped, not negotiated with. Saved as `script.shotlist.json`
— claims only, no durations, because durations do not exist until synthesis.

**Shot plan** (`match.plan_shots`, run at TTS time). Joins the claims with each
sentence's *measured* seconds:
- a sentence's seconds split across its claimed panels;
- an **unmatched sentence walks the unclaimed panels between its surrounding matched
  anchors** in reading order — bounded, so it can never cut to an unrelated image. It
  holds the previous shot only when there are no in-between panels;
- **accent cuts** (intra-sentence multi-panel splits) survive below the normal floor,
  down to `align.accent_shot_seconds`;
- **burst guard**: no more than 3 consecutive shots under 1.2s (the reference runs one
  such burst in ten minutes; ours ran bursts of 6 five times over);
- a claimed **text-only panel is swapped for the nearest art panel** — the narrator is
  already speaking that line, so the screen should carry the moment.

**Timeline** (`video/timeline.py`). The plan's seconds pass through untouched; only the
exact-sum A/V lock applies. Re-clamping them with `min/max_panel_seconds` silently undid
the accent cuts and drifted every later cut off its sentence.

**Camera** (`video/effects.py`). Showing the panel **whole, with blurred bars, is the
default** — measured on the reference channel: its sharp centre band is 0.50 of frame
width at the median with bars on 70% of frames. Filling the frame on every shot measured
0.84, further from the reference than the reference is from us. Routing:

| panel shape | treatment |
|---|---|
| already fits 16:9 | fill the frame (the crop costs nothing) |
| taller, but ≥ `letterbox_min_width_fraction` of frame width when shown whole | **whole + blurred bars**, 4% push-in |
| too tall to read whole (extreme strips) | fill-frame camera: capped drift + hard cuts |

The camera **drifts; it does not traverse.** Per-shot travel is capped at
`video.max_pan_frame_fraction` (0.20) and suppressed entirely below
`video.pan_min_seconds` — fast *and* moving is the jarring combination. Measured on the
reference: 0% of its shots travel more than 0.25 frame-heights. Tall panels are covered
by **cutting** to the next salient window, never by sliding down them.

**Panel hygiene.** Three filters keep non-story frames off screen, each answering a
different question:
- `is_blank_panel` / `is_visually_empty` — is there ink at all?
- `regions.is_text_only_panel` — is this a bare speech bubble?
- `regions.is_content_free` — is there anything a viewer can *read as story*? Two
  measured signals with no overlap against real art: content coverage (art 0.32–0.85,
  these 0.06–0.19) and edge-orientation entropy (art 0.865–0.985; speed lines 0.28, a
  single SFX glyph 0.70). Capped by `align.max_content_free_fraction` — a filter that
  can empty the candidate set is a liability.

**Collage splitting** (`panels/regions.py`). Gutter detection only separates panels
stacked full-width with a uniform row between them. Modern webtoon pages are collages —
insets at staggered offsets on a flat background, bridged by bubbles. A 2D pass splits
them per region, absorbs bare bubbles into their art, and folds wide slivers and
bubble-only bands into their neighbour. The background is whatever the page border is,
never assumed white.

---

## 4. Audio

Kokoro synthesizes **one sentence per call**, so every `.segments.json` entry is a
measured duration. Its own chunking grouped up to 9 sentences, which left 92–94% of
sentence timings estimated by character count — worth ~1.5s of cut drift inside a 22s
chunk. Sentence identity between the shot list and the sidecar is the contract that makes
the plan work; `script/sentences.py` is the one splitter both sides use.

Three traps in the ffmpeg chain, all measured (see the audio-chain notes in `reports/`):
- `alimiter` defaults to `level=1`, which re-normalizes back to 0 dBFS **after** limiting
  and silently undoes loudnorm's true-peak headroom. Always `level=false`.
- Default (mono) AAC bitrate overshoots a −1.5 dBTP signal by ~1.5 dB of coding ringing.
  Pinned to 192k.
- `loudnorm` must be two-pass (measure, then apply linearly) or it overshoots true peak.

BGM lives in `assets/bgm/` (CC-BY, credit required — see its `ATTRIBUTION.md`) and is
mixed under the narration, continuing under the end card while the narration is
silence-padded to match.

---

## 5. QA gates

`qa.py` defines the framework: a stage writes `qa.<stage>.json` and calls `enforce()`; a
failed gate raises `QAGateFailure` and blocks the next stage unless `--force-past-qa`
(threaded as `config["_qa_force"]`). Gates encode bugs that actually shipped once.

- **scene** — speakers must be visible in the panel; dialogue summaries must overlap the
  transcription; `panel_ids` clamped to the batch; every story panel must get a card.
- **script** — beats well-formed, name integrity, grounding findings surfaced.
- **timeline** — no blank panels on the final surface, dwell-over-limit, panel-budget
  drops, beats whose panels all vanished, narration pace vs `script.target_wpm`.
- **render** (`video/qa_visual.py`) — measured on the finished file, because nothing
  upstream can prove these absent: opening shot is not a bubble-on-black, bubble
  dominance, edge-clipped text, dead width, true peak, shot rhythm. Bands are calibrated
  against the **reference channel's own edit of the same chapters** — calibrating against
  our old defective videos produced gates the reference itself would fail.

  Two of those six are deliberately **report-only**, and for the same reason: their
  detectors measure a property of manhwa art rather than a defect. `dead-space` reads
  low-detail columns, and the reference video scores worse on it than anything we ship.
  `bubble-dominance` finds large bright blobs; audited on 2026-08-27, 64% of the frames
  it flagged carried a "bubble" over 40% of the frame — pale walls and bedding — while a
  frame holding a real speech bubble scored zero. Both numbers are kept as data. **A
  measurement that cannot separate the defect from the medium must not steer the
  renderer**: tuning framing against either one moves the camera off artwork to satisfy
  a broken ruler. Fix the detector or leave the band alone.

`tests/test_qa_gates.py` holds one regression fixture per observed bug. Keep it that way:
a new failure class gets a gate **and** a fixture.

---

## 6. Providers, and how they fail

`llm/provider.py::get_llm_provider` resolves in order: **explicit argument → env
(`LLM_PROVIDER`) → config → default.** The explicit argument winning matters: every stage
passes its own `<stage>.provider` from config, so `LLM_PROVIDER=mock` alone does **not**
force the mock. The test suite forces offline by blanking API keys, because every hosted
provider falls back to the mock without one (`tests/conftest.py`,
`tests/test_offline_guard.py`).

A missing key downgrades to `MockLLMProvider` with only a warning, so a real run without
one completes and writes a placeholder script. When a script looks nonsensical, check for
that warning first. An *invalid* key behaves differently — the emptiness check passes and
the request raises mid-stage.

Vision calls must pass `max_width` for whole-page images: `scene.vision_max_side` (512)
is tuned for panel crops and destroys pages — a webtoon strip is ~800×10000, so a
longest-side cap renders it as a 40px sliver and every caption becomes unreadable. Use
`read.page_max_width`.

---

## 7. Configuration

`config.yaml` at repo root holds all tunables; `get_nested(config, "script", "target_wpm",
default=220)` is the access idiom. `.env` holds keys and provider selection. Keys are read
where used rather than validated up front, so a new tunable needs no schema change — but
give `get_nested` a default that **matches** the value in `config.yaml`, or the pipeline
behaves differently the moment the key is absent.

Several values are traceable to measured reference numbers (`reference/style_profile.md`,
`reference/mamoru_shot_profile.md`) — `script.target_wpm`, `video.min/max_panel_seconds`,
the camera and shot-rhythm bands. Change them together with the measurement, and
re-measure rather than guessing.
