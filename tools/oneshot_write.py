"""One-shot freeform chapter write — the 2x2 experiment's B/C arms.

Reproduces the recipe that produced the gold script (reference/ch1_gold_script.md):
hand ONE model the whole chapter as a human would read it — full pages in order,
with the OCR transcript as backup — and let it write the recap as a story. No beat
structure, no panel ids, no per-beat word budgets, no lint vocabulary: the point of
the experiment is to measure what the pipeline's constraint system costs, so none
of it may leak into this prompt.

Deliberately standalone: calls Gemini's OpenAI-compat endpoint directly instead of
going through llm/provider.py, whose _vision_call force-extracts a JSON object from
the response — correct for scene cards, destructive for prose.

Usage:
    PYTHONPATH= .venv/bin/python tools/oneshot_write.py \
        --project projects/return-of-the-frozen-player-ch1-2 \
        --model gemini-3.1-pro-preview \
        --out experiments/oneshot-fp-ch1-2/arm_b.md
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from openai import OpenAI

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

SYSTEM = """You are the narrator-writer for a manhwa recap YouTube channel in the
style of Mamoru Manhwa. You are handed the full pages of a chapter range in reading
order, plus an OCR transcript of the visible text. Read the WHOLE chapter first as a
story — who wants what, what changes, what the chapter is really about — and only
then write the recap narration.

You decide everything a storyteller decides: what to include, what to compress,
what to skip entirely, what to foreshadow, and where to dwell. You are NOT required
to mention every page or every panel. If the source repeats or re-explains something
the viewer already saw, fold it into a clause or drop it.

VOICE (measured from the reference channel — these are targets, not vibes):
- Present tense, third person. Past tense only for genuine backstory.
- Mean sentence length ~12 words; roughly 1 in 4 sentences under 7 words.
- Dialogue is narrated as reported speech ("he asks whether...", "she warns him
  that...") — a says/asks/tells/warns-class verb about every 32 words. Never quote
  lines verbatim, never read a speech bubble aloud.
- On-screen system messages (bracketed game-like text) are story events — deliver
  their content, they are usually the chapter's spine.
- Zero first person. Zero hype-adjective pileups. Dry, occasionally wry: the
  narrator may have a quiet read on events ("which is probably smart when you're
  the weakest in the room") but never mugs for the camera.
- Never describe artwork as artwork: no "panel", "scene", "we see", "the image
  shows", and no clothing/hair inventories unless the detail carries story weight.
- Refer to characters by their glossary names once introduced; use role epithets
  ("the healer") only before a name exists.

SHAPE:
- Cold open mid-tension: the first ~85 words must hook, not set up.
- End on the chapter's forward edge — the unresolved thing that makes the next
  chapter necessary. Never end on a summary.

Write the narration as plain prose paragraphs. No headings, no beat numbers, no
metadata — only the words the voice actor will read aloud."""


def build_user_content(project: Path, target_words: tuple[int, int]) -> list[dict]:
    glossary = json.loads((project / "glossary.json").read_text(encoding="utf-8"))
    ocr = json.loads((project / "ocr.json").read_text(encoding="utf-8"))

    # OCR transcript grouped by page, reading order. Panel ids look like p0007_02 —
    # the page number is the stem.
    by_page: dict[str, list[str]] = {}
    for entry in ocr:
        text = (entry.get("translated_text") or entry.get("full_text") or "").strip()
        if not text:
            continue
        page = entry["panel_id"].split("_")[0].lstrip("p")
        by_page.setdefault(page, []).append(text)
    transcript = "\n".join(
        f"page {page}: " + " / ".join(lines) for page, lines in sorted(by_page.items())
    )

    lo, hi = target_words
    preamble = (
        f"CHARACTER GLOSSARY (use these names):\n{json.dumps(glossary, indent=1)}\n\n"
        f"OCR TRANSCRIPT (backup for text you can't read in the images):\n{transcript}\n\n"
        f"TARGET LENGTH: {lo}-{hi} words total.\n\n"
        "The chapter pages follow in reading order. Read them all, then write the recap."
    )

    content: list[dict] = [{"type": "text", "text": preamble}]
    for page_path in sorted((project / "pages").glob("*.png")):
        data = base64.b64encode(page_path.read_bytes()).decode()
        content.append({"type": "text", "text": f"[page {page_path.stem}]"})
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}
        )
    return content


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, type=Path)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--temperature", type=float, default=0.9)
    ap.add_argument("--target-words", default="950-1100")
    args = ap.parse_args()

    lo, hi = (int(x) for x in args.target_words.split("-"))
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        # .env is not exported by default; read it directly.
        for line in (Path(__file__).resolve().parent.parent / ".env").read_text().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                key = line.split("=", 1)[1].strip()
                break
    if not key:
        sys.exit("no GEMINI_API_KEY")

    client = OpenAI(api_key=key, base_url=BASE_URL)
    content = build_user_content(args.project, (lo, hi))
    n_images = sum(1 for c in content if c["type"] == "image_url")
    print(f"model={args.model}  images={n_images}  temp={args.temperature}")

    resp = client.chat.completions.create(
        model=args.model,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": content},
        ],
        temperature=args.temperature,
        max_completion_tokens=32768,
    )
    print(f"finish_reason={resp.choices[0].finish_reason}")
    text = (resp.choices[0].message.content or "").strip()
    usage = resp.usage
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        f"# One-shot freeform write — {args.model}\n\n"
        f"<!-- project: {args.project} | temp: {args.temperature} | "
        f"tokens: {usage.prompt_tokens} in / {usage.completion_tokens} out -->\n\n"
        f"{text}\n",
        encoding="utf-8",
    )
    print(f"{len(text.split())} words -> {args.out}")
    print(f"tokens: {usage.prompt_tokens} in / {usage.completion_tokens} out")


if __name__ == "__main__":
    main()
