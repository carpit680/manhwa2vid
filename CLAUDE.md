# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Tests — MUST clear PYTHONPATH: the login shell sources ROS (/opt/ros/jazzy),
# whose pytest plugins (launch_testing) fail to import and abort collection.
PYTHONPATH= .venv/bin/python -m pytest -q
PYTHONPATH= .venv/bin/python -m pytest tests/test_story_script.py -q
PYTHONPATH= .venv/bin/python -m pytest tests/test_story_script.py::test_name -q

# Install (editable + local GPU TTS)
pip install -e ".[tts-chatterbox,dev]"

# Full run for one project
manhwa2vid init --images /path/to/chapters --title "Solo Leveling" --chapters "1-10" --lang en
manhwa2vid run all --project projects/solo-leveling-ch1-10       # ingest→panels→scout→ocr→cast→script
manhwa2vid review script --project ... --lint                    # report banned wording per beat
manhwa2vid review script --project ... --approve                 # draft → final, unblocks TTS
manhwa2vid run tts --project ...
manhwa2vid run render --project ... --preview
manhwa2vid review preview --project ... --approve
manhwa2vid run render --project ... --final
manhwa2vid run export --project ...                              # SRT + thumbnail + metadata
manhwa2vid status --project ...

# Any single stage, re-running a cached one:
manhwa2vid run <ingest|panels|scout|ocr|cast|script|tts|render|export> --project ... --force
```

There is no linter or formatter configured. `ffmpeg` must be on PATH for TTS post-processing, render, and export.

## Architecture

### Stage pipeline over a file-based artifact contract

`cli.py` → `pipeline.run_stage()` dispatches one `PipelineStage` (`models.py`) to a module. Stages never
pass data in memory across CLI invocations: each reads its inputs from JSON on disk, writes its outputs,
and appends itself to `checkpoint.json`. `models.project_paths()` is the single source of truth for every
artifact path — add a path there, not inline.

```
ingest   ingest/         pages/*.png + pages/manifest.json (+ sources.json for image projects)
panels   panels/split.py panels.json                     (per-panel PNG crops)
scout    characters/     series bible (lookahead chapters, vision sampling)
ocr      ocr/extract.py  ocr.json, scene_cards.json, panels.story.json, excluded_panels.json
cast     characters/link cast_attribution.json, scene_cards.enriched.json
script   script/         script.synopsis.json, script.outline.json, script.json, script.draft.md
tts      tts/engine.py   audio/beat_NNN.wav, timeline.json
render   video/render.py output/preview_<stamp>.mp4, output/final.mp4
export   export/         SRT, thumbnail, metadata
```

Every stage is idempotent by artifact existence: if its output file exists it prints "Using cached …" and
returns. `--force` re-runs it, and stages that invalidate downstream state delete those files explicitly
(e.g. `split_panels` unlinks `panels.story.json` / `excluded_panels.json`; `run_ocr_and_scenes` unlinks the
enriched/attribution/story artifacts). When adding a stage, mirror that: cache on your own artifact and
delete anything downstream that your output would falsify.

Two human checkpoints are enforced in `pipeline.run_stage`: TTS refuses to run until `script.final.md`
exists or `checkpoint.script_approved` is set; render refuses without `timeline.json`.

### Project dir vs. series dir

A *project* is one recap (one chapter range): `projects/<title-slug>-ch<range>/`. A *series* is shared
across projects of the same title: `projects/<title-slug>/series/character_bible.json` (see
`models.series_paths`). The character bible, quest state, and scout samples live at series level and
accumulate across chapters — that's how "story so far" and sticky character names survive between recaps.
Both resolve relative to `config.find_repo_root()`, which walks up looking for `config.yaml`.
`projects/` is gitignored; test fixtures build throwaway projects in `tmp_path`.

### Character identity — the core of this codebase

Roughly half the source is one problem: a vision model describes each panel independently, so the same
person shows up as "guy with green backpack", "the E-Rank hunter", and "Sung Jin-Woo". Resolving those to
one stable id is what makes narration readable. The layers, in the order they run:

- `characters/seed.py` — glossary (`glossary.json`, human-editable) + optional fandom wiki → initial profiles.
- `characters/scout.py` — samples panels from *later* chapters (`characters.lookahead_chapters`) through the
  VLM so the bible knows a character before this chapter's narration needs to name them.
- `characters/quest.py` — per-profile gap loop: `evaluate_sufficiency` lists missing fields (name, hair,
  outfit, pronoun, aliases…), `search_sources` hunts them, `apply_findings` merges, up to
  `characters.quest_max_iterations`. Also elects the protagonist (`detect_protagonist`) and stamps its
  `narration_labels`.
- `characters/resolve.py` — name/descriptor scoring; `is_mc_visual_signal()` gates protagonist assignment so
  a generic "guy with black hair" never gets promoted to MC.
- `characters/consolidate.py` — merges duplicate profiles, enforces `characters.max_main`.
- `characters/link.py` (`cast` stage) — per-chapter pass: heuristic descriptor merges + one LLM merge pass,
  then writes `cast_attribution.json` (panel_id → people). `_reset_bible_if_polluted` rebuilds from glossary
  when the bible has drifted (a protagonist accumulating >8 aliases is the tell).

`bible.format_bible_for_prompt()` and `bible.naming_priority_rules()` are how this state reaches the LLM —
every script prompt embeds them.

### QA gates — nothing fails silently

`qa.py` defines the gate framework: stages write `qa.<stage>.json` (scene, cast, script,
alignment, style) and call `enforce()` — a failed gate raises `QAGateFailure` and blocks the
next stage unless `--force-past-qa` is passed (threaded via `config["_qa_force"]`). The gates
encode bugs that actually shipped once:

- **scene**: speakers must be people visible in the panel; dialogue summaries must overlap
  OCR/bubble transcription or they're cleared; `panel_ids` are clamped to the actual batch
  (the VLM echoes ids and an off-by-one strands the real panel); `cards-coverage` fails the
  stage if any story panel ends up with no card (`ocr/extract.py`). Blank transition slivers
  (ink stats stamped at split time, rule in `panels/filter.py::is_blank_panel`) are excluded
  before OCR/vision ever sees them — they cost tokens and bait hallucinated cards.
- **cast**: every `ref` in attribution must exist in the bible (`link.py::_cast_integrity_report`);
  VLM-invented ids (`char_man_with_green_backpack`) are resolved or seeded, never left dangling.
- **script**: beat conservation (outline ids == script ids — the narration LLM once silently
  dropped 7 of 18 beats), panel conservation **against `panels.story.json`** (never against
  scene cards — that circularity once let five panels vanish), closer-present, hook-dedup.
  The stage also writes `debug/storyboard.html` (narration next to panel thumbnails per
  beat; regenerate after hand-edits with `manhwa2vid storyboard`) — review it before TTS.
- **timeline** (`tts/engine.py::_enforce_timeline_qa`): no blank panels on the final
  surface, dwell > 1.5×`max_panel_seconds` warns (narration outran its panel count),
  panel-budget drops, and beats whose panels all vanished (nearest-panel substitution).
- **alignment** (`script/verify.py`): adversarial VLM pass — a verifier persona lists narration
  claims the beat's actual panels don't support; major misattributions trigger a rewrite.
- **style** (`script/scorecard.py`): measured bands from `reference/style_profile.md`
  (anchor cadence, dialogue verbs, register violations…); warn-only unless `qa.style_blocking`.

`tests/test_qa_gates.py` holds one regression fixture per observed bug — keep it that way:
a new failure class gets a gate AND a fixture.

### Script generation — three passes, all panel-grounded

`script/generate.py::generate_script` runs synopsis → outline → narration, then lints and rewrites.

1. **Synopsis** (`script/synopsis.py`, `prompts/synopsis.txt`) — whole-chapter story understanding:
   logline, acts, `named_cast` (sticky names merged back into the bible), `plot_facts`.
2. **Outline** — `script/grounding.py::preassign_outline_from_facts` *deterministically* matches each
   `plot_fact` to its best-scoring scene card and locks panel ids to it; uncovered panels become continuity
   beats. The LLM only smooths wording, and `_reconcile_outline_panels` restores the seeded panel bindings
   if it drifts. This ordering is deliberate: it's what stops the model from narrating a later scene over
   early panels.
3. **Narration** (`prompts/recap.txt`) — each beat is handed only its own panels' EVIDENCE lines.

`script/lint.py` then checks banned words (`characters.ban_words`), hedging, protagonist-name spam,
narrator-aside overuse, MC-attributed-while-off-screen, and grounding (`unsupported_grounding_keywords`:
narration mentioning coffee/healer/portal when the panel evidence doesn't). Flagged beats go through
`local_sanitize_narration` (regex) first and only then an LLM rewrite.

`script.draft.md` is the human-editable surface. `_beats_to_markdown` / `_parse_markdown_beats` round-trip
through `<!-- panels: … -->` comments — that comment is load-bearing; edits that drop it lose the beat's
panel binding.

### Panels, timeline, render

`panels/split.py` has three modes for image projects (`panels.split_image_files`): `one_to_one` (each
scanlation file is a panel), `always_split` (gutter detection via row-ink density), `hybrid` (gutter-split
when ≥2 panels found, else keep as a scroll strip). PDFs always gutter-split with a chunked fallback.
Debug overlays land in `debug/`.

`panels/filter.py` marks non-story panels (title splashes, scanlation credits, ads) from filename patterns
and scene-card content; downstream code reads `load_story_panels` / `load_story_scene_cards`, never the raw
`panels.json`.

`video/timeline.py::split_beat_durations` splits a beat's audio across its panels so the durations sum
*exactly* to the audio length — min/max panel seconds are best-effort constraints that yield to A/V lock.
`video/effects.py::choose_camera_mode` picks scroll vs. Ken Burns from `Panel.camera_hint` / aspect ratio
(tall webtoon strips scroll). Render builds per-panel clips → concat → mix narration (+ optional BGM from
`assets/bgm/`) → `loudnorm`.

### Providers and silent fallbacks

`llm/provider.py::get_llm_provider` and `tts/provider.py::get_tts_provider` resolve, in order: explicit
argument → env (`LLM_PROVIDER` / `TTS_PROVIDER`) → `config.yaml` → default. **Missing API keys downgrade to
`MockLLMProvider` with only a warning**, so a real run without `GROQ_API_KEY` completes and writes a
placeholder script rather than failing. When a script looks nonsensical, check for that warning first.
An *invalid or expired* key behaves differently — the emptiness check passes and the request raises
`AuthenticationError: 401 expired_api_key` mid-stage, so the script stage dies loudly instead.
`MockLLMProvider.complete` branches on substrings of the *system prompt* ("beat-by-beat", "rewrite this
recap beat", "identify people in this manhwa panel sample", …) — editing prompt text can silently break
tests, so keep those phrases or update the mock alongside.

Groq calls go through `_retry_on_rate_limit` (honors "try again in Ns", but re-raises immediately on
tokens-per-day exhaustion). Vision calls set `max_completion_tokens=4096` and, for qwen models,
`reasoning_effort: "none"` — thinking models otherwise burn the default token budget on `<think>`
and Groq reports `json_validate_failed` with an empty generation. On that error the provider retries
without JSON mode and extracts the object locally (`_extract_json_object`). Model availability is
key-dependent: llama-4-scout vanished from a fresh key in Aug 2026, which is why the configured
vision model is `qwen/qwen3.6-27b`.

### Configuration

`config.yaml` at repo root holds all tunables (`get_nested(config, "script", "max_beats", default=18)` is
the access idiom). `.env` holds keys and provider selection. Config keys are read where used rather than
validated up front, so a new tunable needs no schema change — but do give `get_nested` a default matching
the value in `config.yaml`.

### Reference style target

`reference/style_profile.md` holds narration statistics measured from the Mamoru Manhwa channel (the
style this pipeline imitates): 237 WPM, ~12.8-word sentences, a reported-speech dialogue verb every ~32
words, near-zero first-person and near-zero slang, present tense. Several `config.yaml` values
(`script.target_wpm`, `genz_level`, `max_narrator_asides`, `video.min/max_panel_seconds`) and the wording
of `prompts/recap.txt` are traceable to those numbers — change them together, and re-measure rather than
guessing. `reference/profile_srt.py <file.srt>` regenerates the stats from a caption file;
`pip install -e ".[reference]"` pulls in yt-dlp for fetching one.

### Series-specific values baked into the code

Some Solo Leveling specifics are hardcoded and will need generalizing for other titles:
`resolve._MC_STRONG_SIGNALS` ("green backpack", "jin-woo"), `grounding.GROUNDING_KEYWORDS` (coffee /
food_truck / healer / portal), `bible.rebuild_bible_from_glossary` (Sung Jin-Woo profile),
`quest.set_protagonist_labels` ("the E-Rank hunter"), and the example names in `prompts/*.txt`.

## Tests

`tests/` runs entirely offline: fixtures `monkeypatch.setenv("LLM_PROVIDER", "mock")` /
`TTS_PROVIDER=mock` and blank the API keys. `test_pipeline.py` synthesizes a PDF with PyMuPDF and drives
the whole pipeline; `test_story_script.py` and `test_script_lint.py` cover the grounding/lint invariants;
`test_render_preview.py` and `test_camera.py` exercise ffmpeg paths.
