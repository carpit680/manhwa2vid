# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Tests — MUST clear PYTHONPATH: the login shell sources ROS (/opt/ros/jazzy),
# whose pytest plugins (launch_testing) fail to import and abort collection.
PYTHONPATH= .venv/bin/python -m pytest -q
PYTHONPATH= .venv/bin/python -m pytest tests/test_match.py -q
PYTHONPATH= .venv/bin/python -m pytest tests/test_match.py::test_name -q

# Install (editable + local GPU TTS)
pip install -e ".[tts-kokoro,dev]"          # add ,upscale for Real-ESRGAN

# Full run for one project
manhwa2vid init --images /path/to/chapters --title "Solo Leveling" --chapters "1-10" --lang en
manhwa2vid run all --project projects/solo-leveling-ch1-10       # ingest→panels→ocr→script
manhwa2vid review script --project ... --lint                    # report banned wording per beat
manhwa2vid review script --project ... --approve                 # draft → final, unblocks TTS
manhwa2vid run tts --project ...
manhwa2vid run render --project ... --preview
manhwa2vid review preview --project ... --approve
manhwa2vid run render --project ... --final
manhwa2vid run export --project ...                              # SRT + thumbnail + metadata
manhwa2vid status --project ...

# Any single stage, re-running a cached one:
manhwa2vid run <ingest|panels|ocr|script|tts|render|export> --project ... --force
```

There is no linter or formatter configured. `ffmpeg` must be on PATH for TTS
post-processing, render, and export.

## Architecture

**`docs/architecture.md` is the reference document** — stages, the artifact contract, the
editing layer, QA gates, providers. Read it before changing pipeline structure. What
follows is the working context that is easy to get wrong.

### The shape of the thing

Narration is written FIRST, from the pages; panels are bound to it afterwards. Reversing
that (write per-panel, assemble later) is what the deleted `classic` pipeline did, and it
produced panel captions instead of a story. Anything that pushes panel structure back
upstream into the writing is moving in the wrong direction.

Stages communicate only through files on disk. `models.project_paths()` is the single
source of truth for every path — add one there, not inline. Each stage caches on its own
artifact and must delete anything downstream its output would falsify.

### Identity is `glossary.json`

A flat, human-editable `name -> aliases` map, seeded empty at init and extended by the
read pass, which never overwrites a human edit. It replaced an accumulating
scout/quest/link identity machine that drifted badly enough to elect a protagonist called
"large orange demon". If a name is wrong, fix one line of the glossary — do not add state.

### Where the rules live

**Prompts set voice and judgment; code enforces invariants.** Every rule the model
declined twice lives in `script/lint.py` and runs after ALL LLM stages. Nothing may
generate text after it. Two habits matter: a defect in the polish pass ships on EVERY
run, so read its output rather than trusting the diff; and where a check cannot be made
precise, say so in the docstring and pin the limit with a test rather than lowering a
threshold until it fires.

### Verification that actually catches things

Every real defect in this project was found by **looking at the output**, not by gates
passing. Contact sheets, individual frames, reading the narration aloud. Numbers can
agree while the video is unwatchable — and twice a metric has been wrong in a way that
looked like a code bug (a "black band" that was deliberate padding; a motion measurement
taken on pure noise, where phase correlation returns garbage at 0.04 confidence).

When cleaning up or refactoring: **the proof is a re-rendered video, not a green suite.**
Rebuild a timeline from the changed tree and diff it against the previous one — it should
be byte-identical unless you intended otherwise.

### Traps that have already cost time

- **`LLM_PROVIDER=mock` does not force the mock.** `get_llm_provider` takes an explicit
  argument first, and every stage passes its own `<stage>.provider` from config. Tests go
  offline by blanking API keys (`tests/conftest.py`); `tests/test_offline_guard.py` pins
  it. Ollama has no key and would escape — no stage may select it.
- **A later pass undoing an earlier pass's work** is the dominant defect class here. The
  shot plan's seconds must reach the timeline unclamped; polish must not re-break what a
  rewrite fixed. When something "doesn't take", look for the pass that runs after it.
- **Vision page calls need `read.page_max_width`.** `scene.vision_max_side` (512) is for
  panel crops; on an 800×10000 page a longest-side cap yields a 40px sliver.
- **ffmpeg audio**: `alimiter` defaults to `level=1` and re-normalizes to 0 dBFS after
  limiting, undoing loudnorm's headroom; default mono AAC bitrate overshoots ~1.5 dB.
  See `docs/architecture.md` §4.
- **Config defaults must match `config.yaml`.** Keys are read where used, so a default
  that differs from the file changes behaviour silently the moment the key is absent.
- **`MockLLMProvider.complete` branches on substrings of the system prompt** — editing
  prompt text can break tests silently. Keep the phrases or update the mock alongside.

### Series-specific values still in the code

`grounding.GROUNDING_KEYWORDS` (coffee / food_truck / healer / portal) and some example
names in prompts are Solo Leveling / Frozen Player specific and will need generalizing
for other titles. `tests/test_series_agnostic.py` guards two things: no development
series name may appear in any shipped prompt (it AST-scans `src/` for prompt constants),
and nothing in `src/` may read `reference/` at runtime.

## Tests

`tests/` runs entirely offline and fast (~8s). `test_pipeline.py::test_freeform_pipeline_mock`
drives the whole pipeline on a synthesized PDF; `test_match.py` and `test_align.py` cover
the editing invariants; `test_camera.py`, `test_regions.py` and `test_render_preview.py`
cover framing and ffmpeg paths; `test_qa_gates.py` holds one fixture per observed bug.

`reference/` holds development yardsticks (the gold script, the measured style and shot
profiles). They are for comparing by hand — runtime code must never read them.
