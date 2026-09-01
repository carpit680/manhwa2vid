"""Orchestrate the story-first script stage: read → write → audit → revise → align.

One function, five steps, no loops. Everything that generates or mutates prose happens
in `write` and the single `revise`; nothing downstream of that may touch a word. That
constraint is the architecture — see `audit.py` for why.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.models import ProjectMeta, ScriptDraft, save_json
from manhwa2vid.qa import QAReport, enforce, qa_forced
from manhwa2vid.script.align import align_script
from manhwa2vid.script.audit import audit_and_revise
from manhwa2vid.script.freeform import paragraphs, write_freeform_script
from manhwa2vid.script.outro import append_outro
from manhwa2vid.script.lint import PLACEHOLDER_PREFIXES, lint_broken_sentences, strip_placeholder_descriptors
from manhwa2vid.script.read import glossary_names, read_chapter_facts
from manhwa2vid.script.sentences import split_sentences

console = Console()

# Prose bands. Reference values measured 2026-08-28 from the Mamoru SRT with the counters
# in measure/script_text.py — see reports/render_audit_2026-08-28.md §3. Floors are a
# fraction of the reference, not the reference itself: this is a floor, not a target.
_REF_VERBS_PER_1K = 31.34
_REF_QUOTED_PER_1K = 1.16
_REF_SHORT_PCT = 21.5
_REF_MEAN_WORDS = 12.76
# Floor lives in script/density.py, which repairs against the same number — the pass
# and the gate can never disagree. 18/1k is the brief's number, justified against the
# reference's like-for-like 31.34.
from manhwa2vid.script.density import VERBS_MIN_PER_1K as _VERBS_MIN_PER_1K  # noqa: E402
_QUOTED_MIN_PER_1K = 0.5   # brief's number; reference 1.16 re-measured

#: Opener-rhythm bands (2026-08-31). Reference: pronoun-open 25.7%, back-to-back 4.6%,
#: connector-open ~15% ("Then" alone 7.5%). Pre-pass scripts measured 35.3-46.7% /
#: 11.0-25.0% / 1.1-3.7% with THESE counters (rhythm.opener_profile, prose only);
#: post-pass all three sit at ≤37.0 / ≤9.1 / ≥9.0. Bands wrap the measured post-pass
#: worst case with margin — a band no pass can reach is an alarm that never stops
#: ringing.
_PRONOUN_OPEN_MAX_PCT = 40.0
_B2B_OPEN_MAX_PCT = 10.0
_CONNECTOR_OPEN_MIN_PCT = 7.0
# The brief proposed 25%. The reference is 21.5%, so 25% would fail the channel being
# imitated -- and Solo Leveling at 23.7% would fail while being MORE reference-like than
# the reference. 18% sits below the reference with margin.
_SHORT_MIN_PCT = 18.0

#: Narrator-to-viewer address per 1000 words, from the competitor corpus (2026-08-29):
#: median 0.16, highest single video 1.01, ours FP 0.75 / SL 0.00. The floor catches a
#: script that never turns outward; the ceiling catches it becoming a tic. Deliberately
#: NOT set from a raw "you" count — that read 17.74 on the field's biggest video, almost
#: all of it quoted dialogue between characters rather than address.
_ADDRESS_MIN_PER_1K = 0.3
#: Re-derived 2026-09-01 from the writer-narrator arms, which turn outward through the
#: first person rather than through address frames: measured presence 1.85-2.64 per 1k
#: across four arms on two titles (address + first person), against 1.34 for the voice
#: that shipped before. The old 2.0 ceiling was set on address frames ALONE and would
#: fail the persona for doing exactly what it was asked to do. 4.0 leaves headroom and
#: still catches a script that has become a podcast about a manhwa.
_ADDRESS_MAX_PER_1K = 4.0

#: Writer asides per 1000 words — explaining a rule, comparing to life outside the book,
#: recalling an earlier scene, noting a translation, judging the writing or the art.
#: Measured across the four bake-off arms: 1.85, 2.42, 2.57, 3.37. The FLOOR matters
#: most: the first light and medium budgets read as prohibitions and produced zero, and
#: nothing in the pipeline noticed the persona had failed to show up.
_META_MIN_PER_1K = 0.8
_META_MAX_PER_1K = 5.0

#: Sentence-case words that open a sentence are not evidence of a name.
_CAPITALISED_RE = re.compile(r"\b([A-Z][a-z]+(?:[- ][A-Z][a-z]+)*)\b")
#: "E-Rank Hunter", "S-Class Gate" — a single-letter grade prefix does not match
#: [A-Z][a-z]+, so the scan starts at "Rank" and reports a name nobody wrote. The whole
#: grade token goes: stripping only the "E-" leaves "Rank Hunter", which still matches.
_GRADE_PREFIX_RE = re.compile(r"\b[A-Z]-[A-Z][a-z]+")


def unknown_names(text: str, allowed: set[str]) -> list[str]:
    """Proper-looking names in the narration that the glossary does not know.

    The identity gate. It replaces protagonist election, pronoun inference, alias
    scoring, descriptor consolidation and bible-pollution detection with one question:
    is this name one we actually know? A model that invents "Kang Min-Su" for an unnamed
    bystander gets caught here, and the fix is a one-line glossary edit rather than
    archaeology through a 174-descriptor profile.

    ADVISORY, NOT BLOCKING — and that is a measured conclusion, not a concession.
    Across three real runs on two titles this produced FIVE distinct false-positive
    classes and zero true positives:

      glossary articles/roles  "Player Association" vs "the Player Association president"
      real-world places        "Pacific Ocean", "Seoul History Museum", "Carthenon Temple"
      transcribed system text  caps runs lifted from bracketed windows
      merged proper nouns      "the modern Earth Jun-Ho sees" -> "Earth Jun-Ho"
      grade prefixes           "an E-Rank Hunter" -> "Rank Hunter"

    Each was individually fixable, and fixing three of them did not stop the fourth and
    fifth from appearing on the next title. Separating an invented PERSON from a
    correctly-named place, rank or organisation needs a tagger, not a longer regex, so
    the honest limit is recorded here rather than hidden behind another heuristic.

    The real defence against an invented character is the audit stage, which sees the
    pages and catches misattribution directly — it caught Jun-Ho touching the wrong
    teammate's ice block. This stays as a report worth reading before approving.
    """
    if not allowed:
        return []
    known = {a.lower() for a in allowed}
    # Individual words of a known name: "Jun-Ho" for "Seo Jun-Ho". Split on WHITESPACE
    # only — splitting hyphens too turned "Seo Jun-Ho" into {seo, jun, ho}, so the very
    # common "Jun-Ho" was never recognised as known.
    for name in list(allowed):
        for part in name.split():
            if len(part) > 2:
                known.add(part.lower())
    # Glossary entries carry articles and roles the narration naturally drops: the
    # glossary says "the Nest Attack Team" and "the Player Association president" while
    # the writing says "Nest Attack Team" and "Player Association". Exact matching flagged
    # both as invented on the first real run. A candidate contained inside a known entry
    # is known — a genuinely invented name is not a sub-phrase of anything we have.
    haystack = " || ".join(known)

    found: dict[str, int] = {}
    # Places are not characters. "Pacific Ocean", "Seoul History Museum" and
    # "Antarctica" are real, correct, and will never be in a CHARACTER glossary — the
    # gate exists to catch an invented PERSON, and flagging geography just teaches the
    # reader to ignore it. A name preceded by a locative preposition is a place.
    text = re.sub(
        r"\b(?:in|at|on|to|from|into|across|near|over|under|inside|outside|toward|towards)"
        r"\s+(?:the\s+)?[A-Z][\w'’-]*(?:[- ][A-Z][\w'’-]*)*",
        " ",
        text or "",
    )
    text = _GRADE_PREFIX_RE.sub("", text)
    for sentence in split_sentences(text):
        # Drop the sentence's FIRST WORD before scanning. Testing "does this candidate
        # start the sentence" does not work: the multi-word pattern is greedy, so
        # "Then Kang Min-Su interrupts" matched as the single candidate
        # "Then Kang Min-Su", which then looked sentence-initial and was skipped —
        # hiding exactly the invented name the gate exists to catch.
        body = sentence.strip().split(" ", 1)
        if len(body) < 2:
            continue
        for match in _CAPITALISED_RE.finditer(body[1]):
            candidate = match.group(1)
            lowered = candidate.lower()
            if lowered in known or lowered in haystack:
                continue
            # A single common word is far more likely sentence-case than a name.
            if " " not in candidate and "-" not in candidate:
                continue
            # Bracketed system text is transcribed in caps and is not a name.
            if candidate.isupper():
                continue
            # Two adjacent proper nouns from DIFFERENT noun phrases merge under a greedy
            # multi-word match: "the modern Earth Jun-Ho sees outside his window" yields
            # the candidate "Earth Jun-Ho". If any word-run inside the candidate is a
            # name we know, this is a merge artifact, not an invention — an invented
            # person contains no known name at all.
            parts = candidate.split()
            if len(parts) > 1 and any(
                " ".join(parts[i:j]).lower() in known
                for i in range(len(parts))
                for j in range(i + 1, len(parts) + 1)
                if (i, j) != (0, len(parts))
            ):
                continue
            found[candidate] = found.get(candidate, 0) + 1
    return sorted(found)


def _beats_markdown(draft: ScriptDraft) -> str:
    from manhwa2vid.script.beats import _beats_to_markdown

    return _beats_to_markdown(draft)


def generate_story_first_script(
    meta: ProjectMeta,
    paths: dict[str, Path],
    config: dict[str, Any],
    *,
    force: bool = False,
) -> ScriptDraft:
    if paths["script_draft"].exists() and not force:
        from manhwa2vid.script.beats import load_script_beats

        console.print(f"[dim]Using existing script draft[/] → {paths['script_draft']}")
        return load_script_beats(paths)

    if force:
        for key in ("chapter_facts_json", "script_freeform", "script_audit_json",
                    "script_alignment_json"):
            paths[key].unlink(missing_ok=True)

    facts = read_chapter_facts(meta, paths, config, force=force)
    text = write_freeform_script(meta, paths, config, force=force)

    if get_nested(config, "script", "audit_enabled", default=True):
        text, record = audit_and_revise(text, paths, config, facts)
        paths["script_freeform"].write_text(text + "\n", encoding="utf-8")
    else:
        record = {"audit": {"majors": [], "undelivered_system_messages": []},
                  "revision": {"revised": False, "reason": "disabled"}}

    # The closing ask, written as a continuation of the last thing said about the
    # story. Appended AFTER the audit so it sees the final sentence it must follow,
    # and so the audit never tries to ground it against panels.
    # Targeted dialogue-density repair: re-voice paragraphs that summarize instead of
    # letting people speak (script/density.py). Before the outro, so the closing ask is
    # never a rewrite target; guarded per paragraph, so the worst outcome is no change.
    from manhwa2vid.script.density import apply_density_pass

    text, _density_record = apply_density_pass(text, paths, config)

    # Subtractive trim: appearance the frame already shows, and narration stating its
    # own emotional register (script/trim.py). Deletions only. After density — density
    # rewrites paragraphs, and trimming first would give it less to work with — and
    # before rhythm, so rhythm merges the sentences that actually survive.
    from manhwa2vid.script.trim import apply_trim_pass

    text, _trim_record = apply_trim_pass(text, paths, config)

    # Opener-rhythm repair: fold same-subject reported-speech chains and break
    # back-to-back openers with "Then" (script/rhythm.py). Deterministic, function
    # words only. After density (it edits the sentences density may rewrite), before
    # the outro (the closing ask is not narration rhythm's business).
    from manhwa2vid.script.rhythm import apply_rhythm_pass

    text, _rhythm_record = apply_rhythm_pass(text, paths, config)

    text = append_outro(text, meta, paths, config)

    # Cast-labelling placeholders read aloud as prose ("the unnamed man in a cowboy
    # hat") are a data leak, not a wording preference, so they are removed in code
    # rather than asked for in the prompt. Runs after every LLM stage — including the
    # outro — and before alignment, so beats, shot list and TTS all see one text.
    text = strip_placeholder_descriptors(text)
    paths["script_freeform"].write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")

    beats, align_report = align_script(text, paths, config)

    draft = ScriptDraft(
        title=meta.title,
        chapters=meta.chapters,
        hook=paragraphs(text)[0][:200] if paragraphs(text) else "",
        beats=beats,
    )
    save_json(paths["script_json"], draft)
    paths["script_draft"].write_text(_beats_markdown(draft), encoding="utf-8")
    console.print(f"[green]Script draft written[/] → {paths['script_draft']}")

    report = QAReport(stage="script-story-first")
    for gate in align_report.gates:
        report.gates.append(gate)

    # Identity: every name in the narration must be one the glossary knows.
    # The SERIES TITLE is a legitimate proper noun in the narration — the closing ask
    # names it ("Where <title> goes from here...", script/outro.py) — but it lives in
    # meta, not in the glossary's characters or terms. Promoting this gate to blocking
    # surfaced that immediately: it flagged the title of the very project under test.
    allowed = glossary_names(paths) | {meta.title, *meta.title.split()}
    strangers = unknown_names(text, allowed)
    # ADVISORY, and back to advisory after a spell as a blocking gate. The promotion
    # rested on "false-positive rate driven to zero — passes both projects clean", which
    # confused a property of two FROZEN glossaries with a property of the detector: both
    # projects passed because their glossaries already happened to contain their place
    # names. Regenerating Solo Leveling's narration produced "South Korea" — the writer
    # completing "Seoul, South Korea", a country that appears nowhere in the source OCR —
    # and the gate blocked the whole script stage on it.
    #
    # That is the SIXTH false positive, in the second of the five classes `unknown_names`
    # already documents as unfixable without a POS tagger, against still zero true
    # positives in four runs across two titles. The one argument for blocking that did
    # not rest on the FP rate was the downstream audio one — a name spelled right and
    # spoken wrong — and it lapsed when the pronunciation lexicon was dropped after
    # A/B listening ("before is still better").
    #
    # The real defence against an invented character remains the audit stage, which sees
    # the pages. Keep reading this report before approving; do not let it stop a run.
    #
    # Note what it CANNOT see: the audio. "Carthenon Temple" and its own glossary alias
    # "Cartenon Temple" are both known names, so this passes — and the TTS then speaks
    # them differently (kˈɑɹθɛnən vs kˈɑɹtɛnən). One place, two spoken names. That is a
    # separate failure with a separate guard; see reports/render_audit_2026-08-28.md §8.
    report.add(
        "name-integrity",
        True if not strangers else "warn",
        f"narration uses name(s) absent from the glossary: {strangers} — either the "
        "writer invented them or the glossary is missing an alias; fix glossary.json",
        unknown=strangers,
    )

    # Names that collide on AUDIO. "Mr. Song" and "Mr. Sung" are one vowel apart and
    # the TTS renders them near-identically — the user's dictation of the vote scene
    # transcribed both as "Mr. Sung". Warn-only: the repair is wording (give one of
    # them their given name), and the source material is allowed to name two
    # characters a vowel apart.
    from manhwa2vid.script.lint import near_homophone_names

    homophones = near_homophone_names(text, glossary_names(paths))
    report.add(
        "name-homophones",
        True if not homophones else "warn",
        f"names nearly identical to the ear: {homophones} — prefer a given name or "
        "epithet for one of them" if homophones else "",
        pairs=homophones,
    )

    # A regression guard, not a discovery gate: `strip_placeholder_descriptors` runs
    # above, so this can only fire if narration reached the beats down a path that
    # skipped it.
    leaked = sorted({
        m.group(0).lower()
        for b in beats
        for m in re.finditer(
            r"\b(?:" + "|".join(PLACEHOLDER_PREFIXES) + r")\s+\w+", b.narration, re.I
        )
    })
    report.add(
        "placeholder-descriptors",
        not leaked,
        f"narration reads a cast label aloud: {leaked} — a glossary key holds a "
        "descriptor where a name belongs; fix glossary.json",
        leaked=leaked,
    )

    # Deterministic well-formedness — the absolute checks, no rewriting.
    broken = lint_broken_sentences(beats)
    report.add(
        "beats-wellformed",
        False if broken else True,
        "; ".join(f"beat {b}: {v[0]}" for b, v in sorted(broken.items())[:3]),
        broken=sorted(broken),
    )

    # --- prose texture vs the reference channel -----------------------------------------
    #
    # The brief ranks these highest, from ~950 comments across 16 videos and 6 channels:
    # viewers punish script errors roughly two orders of magnitude harder than voice
    # quality. All bands are measured with the SAME counters used on the reference SRT
    # (reference/profile_srt.py parity is pinned in tests/test_measure.py), because a
    # threshold derived from one counter and enforced by another is a mistake this project
    # has already made.
    from manhwa2vid.measure.script_text import (
        dialogue_verb_density,
        noun_repetition,
        quoted_span_rate,
        sentence_length_stats,
    )

    verbs = dialogue_verb_density(text)
    report.add(
        "dialogue-verb-density",
        True if verbs["per_1k"] >= _VERBS_MIN_PER_1K else "warn",
        f"{verbs['per_1k']} reporting verbs per 1000 words (floor {_VERBS_MIN_PER_1K}, "
        f"reference {_REF_VERBS_PER_1K}) — the reference lets people SPEAK",
        **verbs,
    )

    # Opener rhythm vs the reference: it opens 25.7% of sentences with a pronoun,
    # ~15% with a connector ("Then" alone 7.5%), and repeats an opener back-to-back
    # 4.6% of the time; we shipped 35.9-48.9% / 2.3-5.3% / 11.5-27.3%. Bands sit
    # between the two — reachable by the deterministic rhythm pass, still far from
    # the old monotony. Measured post-pass before pinning (docs/qa-gates.md).
    from manhwa2vid.script.rhythm import opener_profile

    openers = opener_profile(text)
    rhythm_ok = (
        openers["pronoun_open_pct"] <= _PRONOUN_OPEN_MAX_PCT
        and openers["b2b_pct"] <= _B2B_OPEN_MAX_PCT
        and openers["connector_pct"] >= _CONNECTOR_OPEN_MIN_PCT
    )
    report.add(
        "opener-rhythm",
        True if rhythm_ok else "warn",
        f"pronoun-open {openers['pronoun_open_pct']}% (max {_PRONOUN_OPEN_MAX_PCT}), "
        f"back-to-back {openers['b2b_pct']}% (max {_B2B_OPEN_MAX_PCT}), connectors "
        f"{openers['connector_pct']}% (min {_CONNECTOR_OPEN_MIN_PCT}) — reference "
        "25.7 / 4.6 / ~15",
        **openers,
    )

    quoted = quoted_span_rate(text)
    report.add(
        "quoted-dialogue",
        True if quoted["per_1k"] >= _QUOTED_MIN_PER_1K else "warn",
        f"{quoted['per_1k']} quoted spans per 1000 words (floor {_QUOTED_MIN_PER_1K}, "
        f"reference {_REF_QUOTED_PER_1K})",
        **quoted,
    )

    lengths = sentence_length_stats(text)
    report.add(
        "sentence-length",
        True if lengths["under_8_pct"] >= _SHORT_MIN_PCT else "warn",
        f"{lengths['under_8_pct']}% of sentences run under 8 words (floor "
        f"{_SHORT_MIN_PCT}%, reference {_REF_SHORT_PCT}%); mean {lengths['mean_words']}w "
        f"against the reference's {_REF_MEAN_WORDS}w",
        **lengths,
    )

    # The niche's second-most-liked craft complaint is a channel repeating a bare noun
    # where a pronoun belonged (78 likes for a viewer asking them to count it). Character
    # and place names are exempt — a recap MUST repeat its protagonist's name.
    repeats = noun_repetition(text, exempt=allowed)
    report.add(
        "noun-repetition",
        "warn" if repeats["findings"] else True,
        "; ".join(f"{f['word']} x{f['count']}" for f in repeats["findings"][:5])
        + f" in a {repeats['window_words']}-word window (limit {repeats['max_count']})"
        if repeats["findings"] else "",
        worst_count=repeats["worst_count"],
        findings=repeats["findings"][:10],
    )

    # Narrator-to-viewer address. Field-derived and deliberately two-sided: the corpus
    # median is ~0.16/1k and its highest video 1.01, so this catches a script that never
    # turns outward (SL measured 0.00 while FP measured 0.75 — an inconsistency between
    # our own scripts) AND one that turns outward so often it reads as a tic.
    #
    # Measured on ADDRESS FRAMES, not raw "you". A raw count put Mamoru's 5.2M video at
    # 17.74/1k and looked like a large gap; almost all of it is quoted dialogue between
    # characters. On address proper that video runs 1.01 and ours 0.78.
    from manhwa2vid.measure.script_text import narrator_address_rate

    from manhwa2vid.script.trim import first_person_rate, meta_aside_rate

    address = narrator_address_rate(text)
    first = first_person_rate(text)
    # Address frames and first person are two ways of doing ONE thing: the narrator
    # stepping out of the story to speak to you. The old gate counted only the frames,
    # so the writer-narrator — whose whole turn outward is "I should explain this" —
    # scored 0.0 and warned while being MORE present than any script before it.
    presence = round(address["per_1k"] + first["per_1k"], 2)
    report.add(
        "narrator-presence",
        True if _ADDRESS_MIN_PER_1K <= presence <= _ADDRESS_MAX_PER_1K else "warn",
        f"{presence} narrator turns outward per 1000 words "
        f"({address['per_1k']} address + {first['per_1k']} first person; want "
        f"{_ADDRESS_MIN_PER_1K}-{_ADDRESS_MAX_PER_1K}) — a recap that never turns "
        f"outward reads as a synopsis, one that always does reads as a podcast",
        presence_per_1k=presence, first_person_per_1k=first["per_1k"], **address,
    )

    # How much of the script is the writer talking about the work rather than telling
    # the story. A FLOOR as well as a ceiling, and the floor is the load-bearing half:
    # the first writer_light and writer_medium prompts produced ZERO asides because
    # their budgets were worded as prohibitions, and nothing in the pipeline noticed
    # that the persona had silently failed to appear.
    # NOT named `meta` — that is this function's ProjectMeta parameter, and shadowing
    # it broke record_part at the very end of the stage.
    asides = meta_aside_rate(text)
    report.add(
        "persona-voice",
        True if _META_MIN_PER_1K <= asides["per_1k"] <= _META_MAX_PER_1K else "warn",
        f"{asides['per_1k']} writer asides per 1000 words (want {_META_MIN_PER_1K}-"
        f"{_META_MAX_PER_1K}) — explaining, comparing, recalling, or judging the work",
        **asides,
    )

    residual = (record.get("revision") or {}).get("residual") or []
    report.add(
        "grounding",
        "warn" if residual else True,
        f"{len(residual)} finding(s) survived the single revision — read them in "
        "script.audit.json before approving",
        residual=len(residual),
    )

    # The style scorecard (qa.style.json) lived here. It was report-only — wrapped in a
    # try/except that printed "skipped" and changed nothing — and it was the story-first
    # path's ONLY use of the character bible, i.e. the last thing keeping the scout/quest
    # machinery attached to script generation. Removed with that machinery; narration
    # style is measured against the reference by hand when it matters.

    # Record what this range covered, so a LATER range can be written as a continuation
    # rather than a restart. Before enforce(), because a range whose script was produced
    # is a range the next part must not re-introduce — even if a gate then stops the run
    # for a reason unrelated to what the narration covers. Re-running a range replaces
    # its entry rather than appending a second one.
    from manhwa2vid.script.series import record_part, summarise_narration

    record_part(
        meta.series_slug,
        meta.chapters,
        summarise_narration(text),
        slug=getattr(meta, "slug", ""),
    )

    enforce(report, paths["root"], force=qa_forced(config))
    return draft


def _n_chapters(meta: ProjectMeta) -> int:
    spec = (meta.chapters or "").strip()
    if "-" in spec:
        first, _, last = spec.partition("-")
        try:
            return max(1, int(last) - int(first) + 1)
        except ValueError:
            return 1
    return 1
