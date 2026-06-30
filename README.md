# manhwa2vid

End-to-end pipeline to turn manhwa chapter PDFs into Mamoru-style recap videos.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[tts-chatterbox]"
cp .env.example .env  # add GROQ_API_KEY

# Create a project from a PDF
manhwa2vid init --pdf chapters.pdf --title "Solo Leveling" --chapters "1-10" --lang ko

# Or from scanlation-style image folders (one folder per chapter)
manhwa2vid init --images "/home/arpit/Downloads/0-82" --title "Solo Leveling" --chapters "1-10" --lang en

# Run pipeline (stops at script review)
manhwa2vid run all --project projects/solo-leveling-ch1-10

# Edit script, save as script.final.md, then continue
manhwa2vid review script --project projects/solo-leveling-ch1-10 --approve

# TTS + render
manhwa2vid run tts --project projects/solo-leveling-ch1-10
manhwa2vid run render --project projects/solo-leveling-ch1-10 --preview
manhwa2vid review preview --project projects/solo-leveling-ch1-10 --approve
manhwa2vid run render --project projects/solo-leveling-ch1-10 --final
```

## Requirements

- Python 3.11+
- ffmpeg on PATH
- **Groq API key** (default LLM/VLM) — set `GROQ_API_KEY` in `.env`
- **Chatterbox TTS** (default, local GPU) — `pip install -e ".[tts-chatterbox]"`

Optional: PaddleOCR (`pip install -e ".[ocr]"`), OpenAI TTS (`TTS_PROVIDER=openai`), Ollama for local vision.

## TTS (Chatterbox — local GPU)

Default narration uses [Chatterbox TTS](https://github.com/resemble-ai/chatterbox) on your GPU (RTX 5070 works great).

```bash
pip install -e ".[tts-chatterbox]"
pip install --pre torch torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128
```

**RTX 5070 / 5090 (Blackwell):** Stable PyTorch cu124 does not support sm_120 yet. Use the cu128 nightly line above for GPU, or set `tts.device: cpu` in config.yaml until then.

Configure in [`config.yaml`](config.yaml):

```yaml
tts:
  provider: chatterbox
  device: cuda
  model: standard       # standard | turbo | multilingual
  exaggeration: 0.75    # higher = more energetic recap voice
  cfg_weight: 0.45
  voice_prompt:         # optional WAV for voice cloning
```

Optional voice cloning: drop a 5–10 second WAV into `assets/voices/narrator.wav` and set `voice_prompt: assets/voices/narrator.wav`. Required for `model: turbo`.

Switch back to OpenAI TTS: set `TTS_PROVIDER=openai` and `OPENAI_API_KEY` in `.env`.

## LLM / VLM providers

Configure in `.env` or [`config.yaml`](config.yaml):

| Provider | Env | Script model | Vision (panels) model |
|----------|-----|--------------|------------------------|
| **groq** (default) | `GROQ_API_KEY` | `llama-3.3-70b-versatile` | `meta-llama/llama-4-scout-17b-16e-instruct` |
| openai | `OPENAI_API_KEY` | `gpt-4o-mini` | same or `gpt-4o` |
| ollama | local | `llama3.2-vision` | `llama3.2-vision` |
| mock | none | tests only | tests only |

```bash
# .env example for Groq
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
# OPENAI_API_KEY=sk-...   # only if TTS_PROVIDER=openai
```

Override models in `config.yaml` under `llm.groq`, `script.model`, and `scene.model`.

## Project layout

Each recap lives under `projects/<slug>/` with resumable JSON artifacts between stages.

## Image folder layout

Supports scanlation downloads where each chapter is a subfolder of PNG/JPG files:

```
0-82/
├── [Group]_Solo_Leveling_c01/
│   ├── 001.png
│   ├── 002.png
│   └── ...
├── [Group]_Solo_Leveling_c02/
└── ...
```

Each image file is treated as one panel (no vertical page splitting). Chapter folders are matched by `_c01`, `_c02`, etc. in the folder name. Use `--chapters "1-10"` to select which folders to include.

You can also point `--images` at a single chapter folder containing only image files.
