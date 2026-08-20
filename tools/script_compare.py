"""Side-by-side + metric comparison of a generated script against a reference.

The lesson that forced this tool: every recent "fix" improved a measured gate while the
video got WORSE — nothing measured storytelling. This harness makes the gap visible three
ways: the full text side by side for human reading, style metrics computed identically on
both texts, and CONTENT metrics (fact coverage, story order) so "did it tell the same
story" is a number, not an impression.

References can be:
  - a beat-markdown gold script (## Beat N / ### Beat N sections)
  - a project script.json
  - a plain-text transcript (e.g. a reference channel's narration for the same chapters)

    python tools/script_compare.py --candidate projects/<p>/script.json \
        --reference reference/frozen_player/mamoru_ch1-2.txt --out /tmp/cmp.md
    # legacy spelling still works:
    python tools/script_compare.py --project projects/solo-leveling-ch1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

CAPTION_PATTERNS = [
    r"\bis visible\b", r"\bare visible\b", r"\bcan be seen\b",
    r"\bin the (?:foreground|background)\b",
    r"\bwith an? \w+ expression\b",
    r"\bsits? on the\b", r"\bstands? (?:nearby|in the)\b",
    r"\bwearing an? \b",
    r"\bthe (?:scene|image|view|shot|close-up)\b",
    r"\b(?:left|right) side of\b",
    r"\bnext to (?:him|her|them) (?:is|are|sits|stands)\b",
    r"\bappears? to\b", r"\bis shown\b",
]
CAPTION_RE = re.compile("|".join(CAPTION_PATTERNS), re.I)

SPEECH_VERBS_RE = re.compile(
    r"\b(?:says|asks|tells|replies|answers|admits|snaps|mutters|shouts|yells|calls|"
    r"warns|adds|explains|wonders|thinks|realizes|notices|remembers|swears|promises|"
    r"jokes|laughs about|brands|declares|insists|begs)\b",
    re.I,
)

CONNECTIVES_RE = re.compile(
    r"\b(?:but|because|so|then|still|even|instead|already|finally|until|while|"
    r"before|after|once|never|only|again)\b",
    re.I,
)

PRONOUN_START_RE = re.compile(r"^(?:He|She|They|His|Her|Their)\b")

# ---------------------------------------------------------------------------- loading

def beats_from_markdown(path: Path) -> list[tuple[str, str]]:
    """[(panel_comment, narration), ...] from a beat-markdown file (## or ### headers)."""
    text = path.read_text(encoding="utf-8")
    beats: list[tuple[str, str]] = []
    for block in re.split(r"^#{2,3} Beat \d+\s*$", text, flags=re.M)[1:]:
        panels = ""
        m = re.search(r"<!--\s*panels:\s*(.*?)\s*-->", block)
        if m:
            panels = m.group(1)
        narration = re.sub(r"<!--.*?-->", "", block, flags=re.S).strip()
        narration = narration.split("\n---")[0].strip()
        # a gold file may hold chapter sub-headers between beats; drop leading header lines
        narration = re.sub(r"^#{1,3} .*$", "", narration, flags=re.M).strip()
        if narration:
            beats.append((panels, narration))
    return beats


def beats_from_script_json(path: Path) -> list[tuple[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [(", ".join(b.get("panel_ids", [])), b.get("narration", "")) for b in data.get("beats", [])]


def beats_from_plaintext(path: Path, sentences_per_beat: int = 4) -> list[tuple[str, str]]:
    """A transcript has no beats; group sentences so side-by-side stays readable."""
    text = re.sub(r"\s+", " ", path.read_text(encoding="utf-8")).strip()
    sents = sentences(text)
    return [
        ("", " ".join(sents[i : i + sentences_per_beat]))
        for i in range(0, len(sents), sentences_per_beat)
    ]


def load_any(path: Path) -> list[tuple[str, str]]:
    if path.suffix == ".json":
        return beats_from_script_json(path)
    if path.suffix in (".md", ".markdown"):
        beats = beats_from_markdown(path)
        if beats:
            return beats
    return beats_from_plaintext(path)

# ---------------------------------------------------------------------------- metrics

def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def metrics(beats: list[tuple[str, str]]) -> dict[str, float]:
    full = " ".join(n for _p, n in beats)
    words = max(1, len(full.split()))
    sents = [s for _p, n in beats for s in sentences(n)]

    max_run = 0
    for _p, n in beats:
        run = 0
        for s in sentences(n):
            run = run + 1 if PRONOUN_START_RE.match(s) else 0
            max_run = max(max_run, run)

    return {
        "beats": len(beats),
        "words": words,
        "avg_sentence_words": round(sum(len(s.split()) for s in sents) / max(1, len(sents)), 1),
        "caption_markers_per_100w": round(100 * len(CAPTION_RE.findall(full)) / words, 2),
        "speech_verbs_per_100w": round(100 * len(SPEECH_VERBS_RE.findall(full)) / words, 2),
        "connectives_per_100w": round(100 * len(CONNECTIVES_RE.findall(full)) / words, 2),
        "max_consecutive_pronoun_starts": max_run,
        "pronoun_start_fraction": round(
            sum(1 for s in sents if PRONOUN_START_RE.match(s)) / max(1, len(sents)), 2
        ),
    }

# ------------------------------------------------------------------- content metrics

# Words too common to identify a story moment. Deliberately small and generic — salience
# comes from the reference text itself (rarity + capitalization + numbers), never from a
# per-series list.
_COMMON = frozenset("""
the a an and or but so of to in on at for with from into onto by as is are was were be
been being has have had do does did will would should could can may might must not no
his her their its him she he they them this that these those there here then than when
while before after because if though although one two first last next now just still
even only also very really about over under up down out off all some any more most
man men woman women guy person people thing things way back time year years day says
said asks asked tells told goes going gets got comes came takes took makes made looks
looked knows knew sees saw wants wanted starts started ends ended keeps kept eyes face
hand hands head body voice moment
""".split())


def salient_terms(beats: list[tuple[str, str]]) -> list[str]:
    """Ordered distinctive terms: names (capitalized mid-sentence), number phrases, and
    rare content words. Order = first occurrence, for the order-correlation metric."""
    text = " ".join(n for _p, n in beats)
    seen: dict[str, int] = {}
    pos = 0
    # number phrases ("25 years", "10 floors", "76 hours", "100%")
    for m in re.finditer(r"\b\d+(?:\.\d+)?%?(?:\s+[a-z]+)?\b", text.lower()):
        term = m.group(0).strip()
        if term not in seen and not term.isdigit():
            seen[term] = m.start()
    # capitalized names not at sentence start
    for m in re.finditer(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]+(?:[- ][A-Z][a-z]+)*)\b", text):
        term = m.group(1).lower()
        if len(term) > 2 and term not in _COMMON and term not in seen:
            seen[term] = m.start()
    # rare content words
    words = re.findall(r"[a-z][a-z'-]{3,}", text.lower())
    from collections import Counter
    counts = Counter(words)
    for m in re.finditer(r"[a-z][a-z'-]{3,}", text.lower()):
        w = m.group(0)
        if w in _COMMON or w in seen:
            continue
        if counts[w] <= 3:  # rare in the reference = likely story-specific
            seen[w] = m.start()
    return [t for t, _ in sorted(seen.items(), key=lambda kv: kv[1])]


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s", "'s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def content_metrics(ref: list[tuple[str, str]], cand: list[tuple[str, str]]) -> dict[str, float]:
    """How much of the reference's STORY is in the candidate, and in what order."""
    ref_terms = salient_terms(ref)
    cand_text = " ".join(n for _p, n in cand).lower()
    cand_stems = {_stem(w) for w in re.findall(r"[a-z][a-z'-]{2,}", cand_text)}

    def present(term: str) -> bool:
        parts = term.split()
        return all(_stem(p) in cand_stems or p in cand_text for p in parts)

    hits = [t for t in ref_terms if present(t)]
    coverage = len(hits) / max(1, len(ref_terms))

    # order correlation over shared terms (first occurrence in each text)
    def first_pos(text: str, term: str) -> int:
        i = text.find(term.split()[0])
        return i if i >= 0 else 1 << 30

    ref_text = " ".join(n for _p, n in ref).lower()
    shared = [t for t in hits if first_pos(cand_text, t) < (1 << 30)]
    ref_order = sorted(shared, key=lambda t: first_pos(ref_text, t))
    cand_order = sorted(shared, key=lambda t: first_pos(cand_text, t))
    rank = {t: i for i, t in enumerate(cand_order)}
    concordant = discordant = 0
    for i in range(len(ref_order)):
        for j in range(i + 1, len(ref_order)):
            a, b = rank[ref_order[i]], rank[ref_order[j]]
            if a < b:
                concordant += 1
            elif a > b:
                discordant += 1
    pairs = concordant + discordant
    tau = (concordant - discordant) / pairs if pairs else 1.0

    missing = [t for t in ref_terms if t not in hits]
    return {
        "fact_coverage": round(coverage, 2),
        "order_tau": round(tau, 2),
        "_missing_terms": missing[:25],
        "_term_count": len(ref_terms),
    }

# ---------------------------------------------------------------------------- report

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=None, help="script.json / .md / .txt")
    ap.add_argument("--reference", default=None, help="gold .md / script.json / transcript .txt")
    ap.add_argument("--out", default=None)
    # legacy spelling
    ap.add_argument("--project", default=None)
    ap.add_argument("--gold", default="reference/ch1_gold_script.md")
    args = ap.parse_args()

    if args.candidate is None and args.project:
        args.candidate = str(Path(args.project) / "script.json")
    if args.reference is None:
        args.reference = args.gold
    if args.candidate is None:
        args.candidate = "projects/solo-leveling-ch1/script.json"
    out_path = REPO / (args.out or "reference/script_compare.md")

    ref_path, cand_path = REPO / args.reference, REPO / args.candidate
    ref, cand = load_any(ref_path), load_any(cand_path)

    rm, cm = metrics(ref), metrics(cand)
    content = content_metrics(ref, cand)

    lines = [
        "# Script comparison — reference vs generated",
        "",
        f"Reference: `{args.reference}` · Candidate: `{args.candidate}`",
        "",
        "## Content (does it tell the same story?)",
        "",
        f"- fact_coverage: **{content['fact_coverage']}** of {content['_term_count']} salient reference terms",
        f"- order_tau: **{content['order_tau']}** (1.0 = same story order, 0 = unrelated, <0 = reversed)",
        f"- missing (first 25): {', '.join(content['_missing_terms']) or '(none)'}",
        "",
        "## Style (identical computation on both texts)",
        "",
        "| metric | reference | candidate |",
        "|---|---|---|",
    ]
    for key in rm:
        flag = ""
        if key == "caption_markers_per_100w" and cm[key] > rm[key] * 2 + 0.5:
            flag = " ⚠"
        if key == "speech_verbs_per_100w" and cm[key] < rm[key] * 0.6:
            flag = " ⚠"
        if key == "max_consecutive_pronoun_starts" and cm[key] > max(2, rm[key]):
            flag = " ⚠"
        lines.append(f"| {key} | {rm[key]} | {cm[key]}{flag} |")

    lines += ["", "## Side by side", ""]
    n = max(len(ref), len(cand))
    for i in range(n):
        rp, rn = ref[i] if i < len(ref) else ("", "(no reference beat)")
        cp, cn = cand[i] if i < len(cand) else ("", "(no candidate beat)")
        lines += [
            f"### Beat {i + 1}",
            "",
            f"**reference** {f'`{rp}`' if rp else ''}",
            "",
            rn,
            "",
            f"**candidate** {f'`{cp}`' if cp else ''}",
            "",
            cn,
            "",
        ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    try:
        shown = out_path.relative_to(REPO)
    except ValueError:
        shown = out_path
    print(f"wrote {shown}")
    print(f"\nCONTENT  fact_coverage={content['fact_coverage']}  order_tau={content['order_tau']}")
    print("\nSTYLE  (reference | candidate)")
    for key in rm:
        print(f"  {key:34} {rm[key]:>7} | {cm[key]}")


if __name__ == "__main__":
    main()
