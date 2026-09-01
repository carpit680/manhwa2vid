"""Write one project's narration once per narrator persona, then score every arm.

Pipeline-faithful on purpose: it calls the real `freeform.write_freeform_script`, so
each arm gets the same model, temperature, page windowing, glossary block, quotable-line
block and continuation chaining that a real run gets. The only thing that differs
between arms is `script.persona`. A standalone re-implementation of the writer would
measure a writer we do not ship.

`paths["script_freeform"]` is redirected to `experiments/persona/<project>/<arm>.md`, so
running this never touches the project's real artifacts — the approved script, shot list
and audio are left exactly as they are.

Usage:
    PYTHONPATH= .venv/bin/python tools/persona_bakeoff.py projects/<slug> \
        [--arms current,writer_light,writer_medium,writer_bold] [--force]

Cost: one writer call per page-window per arm (3 windows on a 156-page range, 1 on a
20-page range). Everything else — read pass, audit, align, matching — is skipped.
"""

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from manhwa2vid.config import load_config
from manhwa2vid.measure.script_text import (
    dialogue_verb_density,
    narrator_address_rate,
    noun_repetition,
    quoted_span_rate,
    sentence_length_stats,
)
from manhwa2vid.models import ProjectMeta, project_paths
from manhwa2vid.script.freeform import write_freeform_script
from manhwa2vid.script.personas import PERSONAS
from manhwa2vid.script.read import glossary_names
from manhwa2vid.script.rhythm import opener_profile
from manhwa2vid.script.trim import first_person_rate, meta_aside_rate

#: Reference channel (reference/style_profile.md) and the hand-written gold script,
#: measured with these same counters on 2026-08-31. Shown beside every arm because the
#: two disagree — the gold is the approved quality bar and sits outside most of the
#: bands the pipeline enforces, which is the whole reason this bake-off exists.
YARDSTICKS = {
    "reference": {"verbs": 31.34, "quoted": 1.16, "mean": 12.8, "short": 21.5,
                  "addr": None, "first": 0.24},
    "gold": {"verbs": 20.8, "quoted": 0.0, "mean": 16.7, "short": 4.1,
             "addr": 0.0, "first": 0.0},
}


def score(text: str, names: set[str]) -> dict:
    verbs = dialogue_verb_density(text)
    quoted = quoted_span_rate(text)
    lengths = sentence_length_stats(text)
    addr = narrator_address_rate(text)
    openers = opener_profile(text)
    return {
        "words": len(text.split()),
        "verbs": verbs["per_1k"],
        "quoted": quoted["per_1k"],
        "mean": lengths["mean_words"],
        "short": lengths["under_8_pct"],
        "addr": addr["per_1k"],
        "first": first_person_rate(text)["per_1k"],
        "meta": meta_aside_rate(text)["per_1k"],
        "pron_open": openers["pronoun_open_pct"],
        "b2b": openers["b2b_pct"],
        "conn": openers["connector_pct"],
        "repeat": noun_repetition(text, exempt=names)["worst_count"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path)
    ap.add_argument("--arms", default=",".join(PERSONAS))
    ap.add_argument("--force", action="store_true", help="rewrite arms already on disk")
    args = ap.parse_args()

    paths = project_paths(args.project)
    config = load_config()
    meta = ProjectMeta.model_validate_json(
        (args.project / "project.json").read_text(encoding="utf-8")
    )
    names = glossary_names(paths)
    out_dir = Path("experiments/persona") / args.project.name
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: dict[str, dict] = {}
    for arm in [a.strip() for a in args.arms.split(",") if a.strip()]:
        target = out_dir / f"{arm}.md"
        if target.exists() and not args.force:
            print(f"[{arm}] cached")
        else:
            arm_config = copy.deepcopy(config)
            arm_config.setdefault("script", {})["persona"] = arm
            arm_paths = dict(paths)
            arm_paths["script_freeform"] = target
            print(f"[{arm}] writing…")
            write_freeform_script(meta, arm_paths, arm_config, force=True)
        rows[arm] = score(target.read_text(encoding="utf-8"), names)

    hdr = ("arm", "words", "verbs", "quoted", "mean", "short", "addr", "first",
           "meta", "pron_open", "b2b", "conn", "repeat")
    widths = [16] + [8] * (len(hdr) - 1)
    lines = ["".join(h.rjust(w) for h, w in zip(hdr, widths))]
    for label, y in YARDSTICKS.items():
        cells = [label.rjust(16)]
        for key, w in zip(hdr[1:], widths[1:]):
            v = y.get(key)
            cells.append(("-" if v is None else f"{v:g}").rjust(w))
        lines.append("".join(cells))
    lines.append("-" * sum(widths))
    for arm, s in rows.items():
        cells = [arm.rjust(16)] + [f"{s.get(k, '-'):g}".rjust(w)
                                   for k, w in zip(hdr[1:], widths[1:])]
        lines.append("".join(cells))

    table = "\n".join(lines)
    print("\n" + table)
    (out_dir / "scorecard.txt").write_text(table + "\n", encoding="utf-8")
    (out_dir / "scorecard.json").write_text(
        json.dumps({"arms": rows, "yardsticks": YARDSTICKS}, indent=1), encoding="utf-8"
    )
    print(f"\nwrote {out_dir}/scorecard.txt — now READ the arms, the numbers only "
          f"narrow the field")


if __name__ == "__main__":
    main()
