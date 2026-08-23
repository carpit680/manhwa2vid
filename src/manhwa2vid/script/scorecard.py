"""Style scorecard: measures a finished script against the reference-channel profile.

Bands come from reference/style_profile.md (measured, not aspirational). The scorecard is
the operational definition of "close to the reference" — every metric prints PASS/WARN and
lands in qa.style.json, so drift is visible run over run. It never hard-fails by default:
style is steered, not gated (qa.style_blocking flips that).
"""

from __future__ import annotations

import re
from typing import Any

from manhwa2vid.config import get_nested
from manhwa2vid.models import ScriptBeat, SeriesBible
from manhwa2vid.qa import QAReport

# metric -> (min_ok, max_ok, reference_value); None = unbounded on that side
BANDS: dict[str, tuple[float | None, float | None, float | None]] = {
"sentence_len_mean": (8.0, 15.0, 11.9),
    "dialogue_verbs_per_1k": (18.0, None, 31.3),
    "first_person_per_1k": (None, 1.5, 0.24),
    "slang_per_1k": (None, 1.0, 0.07),
    "hedging_per_1k": (None, 4.0, 2.16),
    "past_ed_per_1k": (None, 35.0, 20.9),
    "anchor_gap_words": (40.0, 130.0, 80.0),
    "pronouns_per_anchor": (1.5, None, 6.4),
    "anonymous_agents_per_1k": (None, 8.0, None),
    # Voice bands, measured from the reference over the same two chapters. These exist
    # because the profile's "0.24 first-person per 1k" was once read as "no narrator
    # persona" and encoded as max_narrator_asides: 0 — the narrator never says "I", but
    # he interprets constantly, and suppressing that is what made our narration read like
    # a report. Floors, not ceilings: too FEW is the failure mode here.
    "similes_per_1k": (0.7, None, 2.0),
    "evaluative_asides_per_1k": (3.0, None, 8.2),
    "time_markers_per_1k": (4.0, None, 13.3),
    "short_sentence_fraction": (0.12, None, 0.23),
    "register_verbs_total": (None, 0.0, 0.0),
    "art_words_total": (None, 0.0, 0.0),
    # Spoken words per panel, mean over beats. Too high = long static dwells (a 25-word
    # single-panel beat sits on screen ~10s); too low = strobing.
    "words_per_panel": (6.0, 18.0, None),
    # Share of sentences opening with a bare pronoun. The gold script sits at 0.20 by
    # varying how sentences START ("Three towering guardians close in on him", "A voice
    # brands him the weakest hunter alive"), not by naming the protagonist more often —
    # so this is NOT fixable by tightening mc_anchor_every_beats, which would only trade
    # it for name spam. Warn-only and reported so the gap stays visible.
    # The acute form of this — long runs of "He ... He ... He" — is separately bounded by
    # rule 1 and currently matches the gold's max of 2 consecutive.
    "pronoun_start_fraction": (None, 0.30, 0.20),
}



_PRONOUN_START_RE = re.compile(r"^\s*(?:he|she|they|it)\b", re.I)


# Voice measures. Patterns are English constructions, never series vocabulary.
_SIMILE_RE = re.compile(r"\blike (?:a|an|the|he|she|they|somebody|someone)\b|\bas if\b", re.I)
_EVAL_RE = re.compile(
    r"\b(?:barely|almost|completely|hardly|just like|nothing but|not exactly|"
    r"in no hurry|for once|of course|somehow|apparently|the \w+est\b)", re.I
)
_TIME_MARK_RE = re.compile(
    r"\b\d+\s*(?:years?|hours?|days?|months?|weeks?|minutes?)\b"
    r"|\b(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|ten|twelve|fifteen)"
    r"[- ]?\w*\s*(?:years?|hours?|days?)\b"
    r"|\b(?:years?|hours?|days?|moments?)\s+(?:later|earlier|before|ago)\b"
    r"|\bback (?:then|when)\b|\bby then\b|\bthat night\b|\bthat morning\b", re.I
)


def _short_sentence_fraction(beats: list[ScriptBeat]) -> float:
    """Share of sentences under seven words — the reference runs 23%, we ran 7%.

    The punch comes from rhythm, not vocabulary: "He dodges by a hair." "Twenty years."
    A script of uniformly mid-length sentences reads as a report however good the words.
    """
    sentences = [
        s for beat in beats
        for s in re.split(r"(?<=[.!?])\s+", beat.narration.strip()) if s.strip()
    ]
    if not sentences:
        return 0.0
    return sum(1 for s in sentences if len(s.split()) <= 6) / len(sentences)


def _pronoun_start_fraction(beats) -> float:
    """Share of narration sentences that open with a bare pronoun."""
    sentences = [
        part
        for beat in beats
        for part in re.split(r"(?<=[.!?])\s+", beat.narration.strip())
        if part.strip()
    ]
    if not sentences:
        return 0.0
    return sum(1 for s in sentences if _PRONOUN_START_RE.match(s)) / len(sentences)

_DIALOGUE_VERBS = ("says", "asks", "tells", "replies", "answers", "explains", "admits",
                   "snaps", "mutters", "warns", "begs", "shouts", "whispers")
_SLANG = ("ngl", "lowkey", "highkey", "bro", "bruh", "sus", "vibe", "vibes")
_HEDGES = ("maybe", "probably", "possibly", "seems", "appears", "might")
_ANON = (r"\ba man\b", r"\banother man\b", r"\bsomeone\b", r"\btwo people\b",
         r"\ba woman\b", r"\ba group of people\b", r"\ba crowd\b", r"\ba person\b")
_NEGATORS = re.compile(r"\b(?:no|never|not|hadn'?t|didn'?t|without|isn'?t|wasn'?t)\b", re.I)
_NEG_STOP = frozenset({"even", "then", "just", "very", "been", "have", "that", "this", "with",
                       "them", "their", "there", "about", "because"})


def _rate(text: str, n_words: int, *terms: str) -> float:
    low = text.lower()
    count = sum(len(re.findall(rf"\b{re.escape(t)}\b", low)) for t in terms)
    return count / max(n_words, 1) * 1000


def _anchor_stats(text: str, bible: SeriesBible) -> tuple[float, float]:
    """(mean words between MC anchors, pronouns per anchor).

    An anchor is any name form the naming policy allows: full canonical name, a short
    alias ("Jin-Woo"), or "the protagonist". Counting only the full canonical name would
    penalize exactly the rotation the policy asks for (name once, then shorter forms).
    """
    mc_name = ""
    pronoun = "he"
    aliases: list[str] = []
    if bible.protagonist_id and bible.protagonist_id in bible.characters:
        mc = bible.characters[bible.protagonist_id]
        mc_name = mc.canonical_name.strip().lower()
        pronoun = (mc.pronoun or "he").lower()
        aliases = [a.strip().lower() for a in mc.aliases if a.strip()]
    if not mc_name:
        return 0.0, 0.0
    low = text.lower().replace("‑", "-")
    words = low.split()
    anchor_res = list(
        dict.fromkeys([mc_name, mc_name.replace("-", " "), "the protagonist", *aliases])
    )
    positions: list[int] = []
    joined = " ".join(words)
    for pat in anchor_res:
        for m in re.finditer(re.escape(pat), joined):
            positions.append(len(joined[: m.start()].split()))
    positions.sort()
    if len(positions) < 2:
        return float(len(words)), 0.0
    gaps = [b - a for a, b in zip(positions, positions[1:])]
    pron_forms = {pronoun, "him", "his"} if pronoun == "he" else {pronoun, "her", "hers"}
    pron_count = sum(1 for w in words if w.strip(".,!?;:'\"") in pron_forms)
    return sum(gaps) / len(gaps), pron_count / len(positions)


def _find_contradictions(beats: list[ScriptBeat]) -> list[str]:
    """Same content noun asserted and negated inside one beat (cheap heuristic, warn-only)."""
    hits: list[str] = []
    for beat in beats:
        words = [w.strip(".,!?;:'\"").lower() for w in beat.narration.split()]
        # word indices covered by a negation window (negator + following 3 words)
        neg_windows: set[int] = set()
        for i, w in enumerate(words):
            if _NEGATORS.fullmatch(w):
                neg_windows.update(range(i + 1, min(i + 4, len(words))))
        candidates = {
            words[i] for i in neg_windows
            if len(words[i]) >= 4 and words[i] not in _NEG_STOP and words[i].isalpha()
        }
        for noun in candidates:
            positions = [i for i, w in enumerate(words) if w == noun]
            inside = [i for i in positions if i in neg_windows]
            outside = [i for i in positions if i not in neg_windows]
            if inside and outside:
                hits.append(f"beat {beat.beat_id}: '{noun}' both asserted and negated")
    return hits


def score_script(
    beats: list[ScriptBeat],
    bible: SeriesBible,
    config: dict[str, Any],
) -> QAReport:
    from manhwa2vid.script.lint import _ART_RE, _REGISTER_RE  # shared definitions

    report = QAReport(stage="style")
    text = " ".join(b.narration for b in beats)
    n = len(text.split())
    if not n:
        report.add("non-empty", False, "script has no narration")
        return report

    sents = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    slens = [len(s.split()) for s in sents]
    anchor_gap, pron_per_anchor = _anchor_stats(text, bible)

    metrics: dict[str, float] = {
        "sentence_len_mean": sum(slens) / max(len(slens), 1),
        "dialogue_verbs_per_1k": _rate(text, n, *_DIALOGUE_VERBS),
        "first_person_per_1k": _rate(text, n, "i", "i'm", "me", "my"),
        "slang_per_1k": _rate(text, n, *_SLANG),
        "hedging_per_1k": _rate(text, n, *_HEDGES),
        "past_ed_per_1k": len(re.findall(r"\b\w+ed\b", text.lower())) / n * 1000,
        "anchor_gap_words": anchor_gap,
        "pronouns_per_anchor": pron_per_anchor,
        "anonymous_agents_per_1k": sum(len(re.findall(p, text.lower())) for p in _ANON) / n * 1000,
        "similes_per_1k": len(_SIMILE_RE.findall(text)) / n * 1000,
        "evaluative_asides_per_1k": len(_EVAL_RE.findall(text)) / n * 1000,
        "time_markers_per_1k": len(_TIME_MARK_RE.findall(text)) / n * 1000,
        "short_sentence_fraction": _short_sentence_fraction(beats),
        "register_verbs_total": float(len(_REGISTER_RE.findall(text))),
        "art_words_total": float(len(_ART_RE.findall(text))),
        "words_per_panel": sum(
            len(b.narration.split()) / max(len(b.panel_ids), 1) for b in beats
        ) / max(len(beats), 1),
        "pronoun_start_fraction": _pronoun_start_fraction(beats),
    }

    blocking = bool(get_nested(config, "qa", "style_blocking", default=False))
    for name, value in metrics.items():
        lo, hi, ref = BANDS[name]
        in_band = (lo is None or value >= lo) and (hi is None or value <= hi)
        status: bool | str = True if in_band else (False if blocking else "warn")
        ref_txt = f" (ref {ref})" if ref is not None else ""
        band_txt = f"band [{lo if lo is not None else '-'}..{hi if hi is not None else '-'}]"
        report.add(name, status, "" if in_band else f"{value:.1f} outside {band_txt}{ref_txt}",
                   value=round(value, 2), ref=ref, lo=lo, hi=hi)

    contradictions = _find_contradictions(beats)
    report.add("self-consistency", "warn" if contradictions else True,
               "; ".join(contradictions[:3]), hits=contradictions)

    # The mean above hides a single overloaded beat — flag individual offenders too.
    _, wpp_hi, _ = BANDS["words_per_panel"]
    outliers = [
        f"beat {b.beat_id}: {len(b.narration.split())}w / {max(len(b.panel_ids), 1)} panel(s)"
        for b in beats
        if len(b.narration.split()) / max(len(b.panel_ids), 1) > (wpp_hi or 18.0)
    ]
    report.add("words-per-panel-outliers", "warn" if outliers else True,
               "; ".join(outliers[:4]), outliers=outliers)
    per_chapter = int(get_nested(config, "script", "words_per_chapter", default=550))
    n_chapters = int(config.get("_n_chapters", 1)) if isinstance(config, dict) else 1
    target = per_chapter * max(1, n_chapters)
    in_band = 0.7 * target <= n <= 1.3 * target
    report.add(
        "total_words",
        True if in_band else "warn",
        "" if in_band else f"{n} words vs target {target} (band 70-130%)",
        value=n,
        beats=len(beats),
    )
    return report
