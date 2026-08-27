# manhwa2vid

Turns manhwa chapters into narrated recap videos, in the format of the Mamoru Manhwa
channel: a story-first narration written from the pages, cut to the panels that depict
each sentence.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[tts-kokoro,dev]"
cp .env.example .env          # add GEMINI_API_KEY

# Create a project from scanlation image folders (one folder per chapter)
manhwa2vid init --images /path/to/chapters --title "Solo Leveling" --chapters "1-10" --lang en
# ...or from a PDF
manhwa2vid init --pdf chapters.pdf --title "Solo Leveling" --chapters "1-10" --lang ko

# ingest → panels → ocr/scene → script, then pause for review
manhwa2vid run all --project projects/solo-leveling-ch1-10

# Read projects/<slug>/script.draft.md, edit if needed, then approve
manhwa2vid review script --project projects/solo-leveling-ch1-10 --approve

# Narration, then video
manhwa2vid run tts --project projects/solo-leveling-ch1-10
manhwa2vid run render --project projects/solo-leveling-ch1-10 --preview
manhwa2vid review preview --project projects/solo-leveling-ch1-10 --approve
manhwa2vid run render --project projects/solo-leveling-ch1-10 --final
manhwa2vid run export --project projects/solo-leveling-ch1-10     # SRT + thumbnail + metadata
```

`manhwa2vid status --project ...` shows which stages have completed. Any stage re-runs
with `--force`.

## Requirements

- Python 3.11+
- `ffmpeg` on PATH (required for TTS post-processing, render and export)
- **A Gemini API key** — the read/write/audit/align stages default to Gemini. Groq,
  OpenAI, Mistral and Ollama are also supported; see `config.yaml`.
- **Kokoro TTS** (local GPU) — `pip install -e ".[tts-kokoro]"`

Optional extras: `.[upscale]` for Real-ESRGAN 2× panel upscaling (worth it — source
scanlations are often only 720–800px wide), `.[ocr]` for PaddleOCR, `.[reference]` for
yt-dlp when fetching a reference video to measure against.

> A missing API key does **not** fail the run — it downgrades to a mock provider with a
> warning and writes a placeholder script. If a script looks nonsensical, check for that
> warning first.

## How it works

Narration is written first, from the pages; panels are bound to it afterwards.

```
ingest → panels → ocr/scene → script → [review] → tts → render → export
```

The script stage is five passes: **read** the pages for what they literally show →
**write** the narration as prose → **audit** it against the pages and allow one revision
→ append an **outro** that continues the last line into the subscribe ask → **align**
paragraphs to panels and **match** each sentence to the panels that depict it.

Editing decisions (which panel is on screen, for how long, how the camera moves) are all
downstream of the narration and are described in
[`docs/architecture.md`](docs/architecture.md).

Characters are tracked in a flat, human-editable `glossary.json` per project. If a name
comes out wrong, fix that one line and re-run the script stage.

## Voice

```yaml
tts:
  provider: kokoro
  kokoro_voice: am_adam
  kokoro_speed: 1.34      # paired with script.target_wpm — see the note below
```

`kokoro_speed` and `script.target_wpm` must be tuned together: panel dwell and total
runtime are planned from the target, so letting them drift apart desynchronises pacing.
The speed→WPM curve is steep and non-linear (1.33→204, 1.34→223, 1.35→228 measured), and
it shifts whenever the way text is fed to the model changes — re-measure, never
extrapolate. A QA gate fails the TTS stage when the delivered rate misses the target.

Background music goes in `assets/bgm/` (see its `ATTRIBUTION.md` — the bundled tracks are
CC-BY and require credit in the video description).

## Image folder layout

Scanlation downloads where each chapter is a subfolder:

```
0-82/
├── [Group]_Solo_Leveling_c01/
│   ├── 001.png
│   └── ...
├── [Group]_Solo_Leveling_c02/
└── ...
```

Chapter folders are matched by `_c01`, `_c02` … in the name; `--chapters "1-10"` selects
which to include. You can also point `--images` at a single chapter folder of images.

Pages are split into panels by gutter detection plus a 2D pass for collage layouts
(insets floating on a flat background) — a whole page is rarely one panel, and the
splitter does not assume a white background.

## Project layout

Each recap lives under `projects/<slug>/` as resumable JSON artifacts between stages, so
any stage can be re-run alone. `projects/` is gitignored.

## Development

```bash
PYTHONPATH= .venv/bin/python -m pytest -q     # ~8s, fully offline
```

Clearing `PYTHONPATH` is required if your shell sources ROS — its pytest plugins abort
collection. The suite makes no network calls; `tests/test_offline_guard.py` enforces
that.

See [`CLAUDE.md`](CLAUDE.md) for working context and the traps that have already cost
time, and [`docs/architecture.md`](docs/architecture.md) for the full design.
