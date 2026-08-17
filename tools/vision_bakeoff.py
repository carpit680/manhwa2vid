"""Compare vision providers on panels whose ground truth we established by eye.

Model availability and naming are key-dependent (llama-4-scout vanished from a fresh Groq
key), so this verifies each provider's configured vision model against its live model list
before spending anything.

    python tools/vision_bakeoff.py --list                 # what can each key actually reach?
    python tools/vision_bakeoff.py                        # score every configured provider
    python tools/vision_bakeoff.py --providers gemini     # just one

Scoring uses the failure modes that actually shipped bad scripts:
  hallucinated_mc   named the protagonist in a panel he is absent from  (the worst one)
  missed_mc         failed to see him where he IS present
  bubbles           transcribed the visible dialogue
  speaker_grounded  every speaker is also listed as a visible person
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

PROJECT = REPO / "projects" / "solo-leveling-ch1"

# Ground truth established by reading these panels directly (see the chapter-1 critique).
CASES: list[dict] = [
    {
        "panel": "p0024_01",
        "mc_present": False,
        "expect_bubble_words": ["highest", "ranked", "trust"],
        "note": "three men, none is the protagonist; Groq's model invented him speaking here",
    },
    {
        "panel": "p0016_01",
        "mc_present": True,
        "expect_bubble_words": ["weakest", "strongest"],
        "note": "back-turned MC with green backpack at a construction site",
    },
    {
        "panel": "p0017_01",
        "mc_present": False,
        "expect_bubble_words": ["hearing", "geezers"],
        "note": "coffee cup visible but NO barista — source of the invented barista scene",
    },
]

PROMPT = (
    "Transcribe this manhwa panel, then infer. Return JSON with keys:\n"
    '  "bubbles": verbatim text of every speech bubble,\n'
    '  "people": [{"descriptor": "what you can SEE of each visible person"}],\n'
    '  "speakers": [descriptor of whoever speaks a bubble — must be one of people],\n'
    '  "named_characters": [any character you can identify by name, empty if none]\n'
    "Only describe people actually visible in this image."
)

MC_MARKERS = ("jin-woo", "jin woo", "sung jin", "protagonist", "green backpack")


def score_case(case: dict, data: dict) -> dict:
    people = " ".join(
        str(p.get("descriptor", "")) if isinstance(p, dict) else str(p)
        for p in data.get("people", [])
    ).lower()
    named = " ".join(str(n) for n in data.get("named_characters", [])).lower()
    bubbles = " ".join(str(b) for b in data.get("bubbles", [])).lower()
    speakers = [str(s).lower() for s in data.get("speakers", [])]

    claims_mc = any(m in named for m in MC_MARKERS) or "jin" in people
    hallucinated_mc = claims_mc and not case["mc_present"]
    missed_mc = case["mc_present"] and not (claims_mc or "backpack" in people)

    found = sum(1 for w in case["expect_bubble_words"] if w in bubbles)
    bubble_recall = found / len(case["expect_bubble_words"])

    # every speaker should correspond to someone listed as visible
    grounded = all(
        any(tok and tok in people for tok in s.split() if len(tok) > 3) for s in speakers
    ) if speakers else True

    return {
        "hallucinated_mc": hallucinated_mc,
        "missed_mc": missed_mc,
        "bubble_recall": bubble_recall,
        "speaker_grounded": grounded,
        "n_people": len(data.get("people", [])),
    }


def run_provider(name: str, cases: list[dict]) -> None:
    from manhwa2vid.config import load_config
    from manhwa2vid.llm.provider import get_llm_provider

    config = load_config()
    os.environ["LLM_PROVIDER"] = name
    provider = get_llm_provider(name, config=config)
    if type(provider).__name__ == "MockLLMProvider":
        print(f"\n=== {name}: SKIPPED (no API key set)")
        return

    available = getattr(provider, "available_models", lambda: [])()
    # Gemini lists ids as "models/gemini-..." while requests use the bare id — normalize.
    available = [m.removeprefix("models/") for m in available]
    model = getattr(provider, "vision_model", "?")
    if available and model not in available:
        print(f"\n=== {name}: configured vision model {model!r} NOT in this key's model list")
        vision_like = [m for m in available if any(t in m.lower() for t in ("vision", "pixtral", "flash", "vl", "qwen", "gemini"))]
        print(f"    candidates: {', '.join(vision_like[:8]) or '(none look multimodal)'}")
        return

    print(f"\n=== {name}  (vision model: {model})")
    totals = {"hallucinated_mc": 0, "missed_mc": 0, "bubble_recall": 0.0, "speaker_grounded": 0}
    elapsed = 0.0
    for case in cases:
        path = PROJECT / "panels" / f"{case['panel']}.png"
        if not path.exists():
            print(f"  {case['panel']}: missing image, skipped")
            continue
        start = time.time()
        try:
            raw = provider.describe_panels([path], PROMPT)
            data = json.loads(raw)
        except Exception as exc:
            print(f"  {case['panel']}: FAILED — {type(exc).__name__}: {str(exc)[:110]}")
            continue
        took = time.time() - start
        elapsed += took
        s = score_case(case, data)
        totals["hallucinated_mc"] += int(s["hallucinated_mc"])
        totals["missed_mc"] += int(s["missed_mc"])
        totals["bubble_recall"] += s["bubble_recall"]
        totals["speaker_grounded"] += int(s["speaker_grounded"])
        flags = []
        if s["hallucinated_mc"]:
            flags.append("HALLUCINATED-MC")
        if s["missed_mc"]:
            flags.append("missed-MC")
        if not s["speaker_grounded"]:
            flags.append("ungrounded-speaker")
        print(
            f"  {case['panel']}: bubbles {s['bubble_recall']:.0%}  people={s['n_people']}  "
            f"{took:4.1f}s  {' '.join(flags) or 'clean'}"
        )
    n = len(cases)
    print(
        f"  TOTAL: hallucinated_mc={totals['hallucinated_mc']}/{n}  "
        f"missed_mc={totals['missed_mc']}/{n}  "
        f"bubble_recall={totals['bubble_recall'] / max(n, 1):.0%}  "
        f"speaker_grounded={totals['speaker_grounded']}/{n}  {elapsed:.0f}s total"
    )


def list_models() -> None:
    from manhwa2vid.llm.provider import GeminiProvider, GroqProvider, MistralProvider

    for name, cls, envs in (
        ("groq", GroqProvider, GroqProvider.API_KEY_ENVS),
        ("gemini", GeminiProvider, GeminiProvider.API_KEY_ENVS),
        ("mistral", MistralProvider, MistralProvider.API_KEY_ENVS),
    ):
        if not any(os.getenv(e) for e in envs):
            print(f"{name}: no key set ({' or '.join(envs)})")
            continue
        models = cls().available_models()
        print(f"\n{name}: {len(models)} model(s)")
        for m in models:
            print(f"  {m}")


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(REPO / ".env", override=True)

    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", default="groq,gemini,mistral")
    ap.add_argument("--list", action="store_true", help="just list reachable models per key")
    args = ap.parse_args()

    if args.list:
        list_models()
        return

    for name in [p.strip() for p in args.providers.split(",") if p.strip()]:
        try:
            run_provider(name, CASES)
        except Exception as exc:
            print(f"\n=== {name}: ERROR — {type(exc).__name__}: {str(exc)[:160]}")

    print("\nGround truth for reference:")
    for c in CASES:
        print(f"  {c['panel']}: mc_present={c['mc_present']} — {c['note']}")


if __name__ == "__main__":
    main()
