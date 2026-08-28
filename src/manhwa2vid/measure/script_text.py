"""Deterministic measurements of the narration text.

The brief ranks these highest, from a comment-mining pass over ~950 comments across 16
videos and 6 channels: viewers punish script errors roughly two orders of magnitude
harder than voice quality. The top craft complaint in the niche is a name-consistency
failure ("From Rowan to Robert to Ramen to Ron to Roen to Rowen", 634 likes); second is
noun repetition (a channel saying "apothecary" instead of using pronouns, 78 likes for a
viewer asking for a counter). Complaints about robotic TTS timbre drew 0-2 likes.

Counter parity matters more than the absolute numbers. `reference/style_profile.md`'s
rates came from `reference/profile_srt.py`, so the lexicons here are deliberately the
SAME lists that script uses — a threshold derived from one counter and enforced by
another is the exact mistake this project has already made once.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from manhwa2vid.script.sentences import split_sentences

# Same list as reference/profile_srt.py's "dialogue verbs (says/asks/tells)" so the
# reference rate and ours are the same measurement. `script/lint.py` separately BANS the
# report-register verbs (expresses, converses, ...); this only counts the good ones.
DIALOGUE_VERBS = ("says", "asks", "tells", "replies", "answers", "explains", "admits")

# `DIALOGUE_VERBS` is fixed to the reference counter's exact list and must not grow — it
# defines a RATE compared against the reference's own. These are the other inflections and
# near-synonyms of the same act, needed only to exempt them from `noun_repetition`.
_REPORTING_INFLECTIONS = (
    "said", "say", "ask", "asked", "tell", "told", "warns", "warned", "warn",
    "adds", "added", "add", "notes", "noted", "points", "pointed", "yells", "yelled",
    "mutters", "muttered", "shouts", "shouted", "snaps", "snapped", "insists",
    "demands", "demanded", "whispers", "whispered", "replied", "reply", "explained",
    "admitted", "admit", "answered", "answer", "states", "stated",
)

_WORD_RE = re.compile(r"[A-Za-z']+")
# DOUBLE quotes only, straight or curly. The ASCII apostrophe is excluded deliberately:
# including it matched every contraction in the corpus and reported the reference channel
# at 1.62 "quoted spans" per 1000 words, when the real spans it found were fragments like
# "re nothing" out of "they're nothing". That number nearly rewrote the writer's prompt.
_QUOTE_RE = re.compile(r"[\"“]([^\"“”]{3,}?)[\"”]")

# Words that carry no story weight, so repeating them is not the defect the gate is for.
_STOPWORDS = frozenset("""
a an the and or but if then than that this these those of to in on at by for with from
into over under after before while as is are was were be been being am do does did done
has have had having will would can could shall should may might must not no nor so such
he she it they them his her its their him you your i me my we us our who whom which what
when where why how all any both each few more most other some only own same too very
just now here there back out up down off again once still even also about
""".split())


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def dialogue_verb_density(text: str) -> dict[str, Any]:
    """Reporting verbs per 1000 words — how often the narration lets people SPEAK."""
    low = text.lower()
    n = max(len(_words(text)), 1)
    count = sum(len(re.findall(rf"\b{re.escape(v)}\b", low)) for v in DIALOGUE_VERBS)
    return {"words": n, "dialogue_verbs": count, "per_1k": round(1000.0 * count / n, 2)}


def quoted_span_rate(text: str) -> dict[str, Any]:
    """Quoted spans per 1000 words — actual lines of dialogue delivered as dialogue."""
    n = max(len(_words(text)), 1)
    spans = _QUOTE_RE.findall(text)
    return {"words": n, "quoted_spans": len(spans), "per_1k": round(1000.0 * len(spans) / n, 2)}


def sentence_length_stats(text: str) -> dict[str, Any]:
    """Sentence length distribution. Short sentences are the reference's main rhythm tool."""
    sents = [s for s in split_sentences(text) if s.strip()]
    lens = [len(_words(s)) for s in sents]
    if not lens:
        return {"sentences": 0, "mean_words": 0.0, "under_8_pct": 0.0}
    import numpy as np

    return {
        "sentences": len(lens),
        "mean_words": round(float(np.mean(lens)), 2),
        "median_words": int(np.median(lens)),
        "under_8_pct": round(100.0 * sum(x < 8 for x in lens) / len(lens), 1),
        "over_25_pct": round(100.0 * sum(x > 25 for x in lens) / len(lens), 1),
    }


def _stem(word: str) -> str:
    """Crudest defensible stemmer: fold plurals so 'apothecary'/'apothecaries' are one."""
    for suffix in ("ies", "es", "s"):
        if len(word) > 4 and word.endswith(suffix):
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def noun_repetition(
    text: str, *, window_words: int = 200, max_count: int = 4, exempt: set[str] | None = None
) -> dict[str, Any]:
    """Content words repeated more than `max_count` times in any rolling window.

    Deliberately not POS-tagged: a tagger is a dependency and a second opinion to keep in
    sync, and the defect viewers actually complain about is a bare repeated noun that a
    pronoun should have replaced. Character and place names are `exempt` — a recap must
    repeat the protagonist's name, and the reference channel does.

    Reporting verbs are exempt for the same reason, measured rather than assumed: across
    the reference SRTs the worst 200-word window holds "says" NINE times, against this
    gate's limit of four, and every other overflow there is a name. Repeating a speech
    verb is what the register sounds like — `dialogue_verb_density` exists to DEMAND
    these — so counting them here would have the two gates pulling against each other,
    and the writer's prompt was changed to ask for more of exactly this word.
    """
    exempt_stems = {_stem(w.lower()) for w in (exempt or set())}
    exempt_stems.update(_stem(v) for v in DIALOGUE_VERBS)
    exempt_stems.update(_stem(v) for v in _REPORTING_INFLECTIONS)
    for name in list(exempt or set()):
        for part in re.split(r"[\s\-]+", name.lower()):
            if part:
                exempt_stems.add(_stem(part))

    words = _words(text)
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for start in range(0, max(len(words) - window_words + 1, 1), window_words // 4 or 1):
        window = words[start : start + window_words]
        counts = Counter(
            _stem(w) for w in window
            if len(w) > 3 and w not in _STOPWORDS and _stem(w) not in exempt_stems
        )
        for stem, count in counts.items():
            if count > max_count and (stem, count) not in seen:
                seen.add((stem, count))
                findings.append({"word": stem, "count": count, "window_start_word": start})
    worst = max((f["count"] for f in findings), default=0)
    # One finding per word: the worst window it appears in.
    best_per_word: dict[str, dict[str, Any]] = {}
    for f in findings:
        if f["word"] not in best_per_word or f["count"] > best_per_word[f["word"]]["count"]:
            best_per_word[f["word"]] = f
    return {
        "window_words": window_words,
        "max_count": max_count,
        "worst_count": worst,
        "findings": sorted(best_per_word.values(), key=lambda f: -f["count"]),
    }
