"""Check finished narration against the pages, and allow exactly one revision.

The one-shot writer is good but not audit-free: the best script in the 2x2 said
"humanity has only cleared the second floor" where the pages say humanity is *on* the
second floor — a one-word drift that contradicts the next sentence's premise. So a
grounding pass is required. What is NOT permitted is a loop.

Every previous quality push added another rewrite round, and the dominant defect class
of this project became "a later pass undoes an earlier pass's work" — seven-plus
documented instances, including a voice pass that stripped landed system messages and an
alignment audit that reverted 21 of 28 beats. The rule here is therefore structural:

    at most ONE revision, and it is accepted only if it strictly improves.

If the revision does not reduce findings, the ORIGINAL is kept and the residue is
reported to the human. That makes regression impossible by construction rather than by
vigilance, which is the whole reason this architecture exists.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.llm.vision_utils import page_max_width
from manhwa2vid.models import save_json

console = Console()

#: Output-token budget for this stage's one big JSON answer. The provider default
#: (4096) was sized for a 16-panel window; this stage answers about every page in
#: the range at once. See LLMProvider.set_json_budget.
_JSON_BUDGET_TOKENS = 16384


#: Distinctive words a system message needs before the recap is held to it.
_MIN_SPINE_WORDS = 3

_AUDIT_SYSTEM = """You are fact-checking a finished manhwa recap against the chapter's
actual pages. You do not rewrite anything — you report.

You are given the recap narration and then the pages in reading order.

Return JSON only:
{
  "findings": [
    {"severity": "major", "quote": "the exact sentence from the narration",
     "problem": "what the pages actually show", "page": "0012"}
  ]
}

severity is "major" only when the narration states something the pages contradict, or
attributes an action or line to the wrong character, or gets a number, rank, count or
time reference wrong. Everything else — compression, omission, an interpretive flourish,
a stylistic aside, casual or profane register — is NOT a finding. A recap is allowed to
leave things out, to editorialise, and to be crude; it is not allowed to be wrong.

The narrator may also step forward AS A WRITER and speak in the first person: explaining
a rule the chapter assumes, comparing something to life outside the book, reminding the
viewer of an earlier scene, remarking that a printed line reads awkwardly in translation,
saying the chapter rushes a beat, or judging the art. None of that is a finding either,
even when you disagree with the opinion. Judge only claims about WHAT HAPPENS on these
pages. An opinion cannot be factually wrong; a translation remark is about the lettering,
not the events.

Do not report a claim as unsupported merely because a detail is small or off-page-centre.
Report only what you can see is WRONG.

You may also be given CHAPTER FACTS: short statements a separate pass extracted from
these same pages before the recap was written. Use them as a CHECKLIST for who did what
— attributing one character's injury, kill, line or decision to another is the single
most common way this recap goes wrong, and artwork of a wounded figure rarely names its
owner. Where the narration and a chapter fact disagree about WHO, look at the pages and
report the one the pages support. The facts are corroboration, not scripture: if the
pages contradict a fact, trust the pages and do not raise a finding against the
narration for agreeing with them."""

_VERIFY_SYSTEM = """You are verifying ONE claimed error in a manhwa recap against the
page it cites. A previous pass read the whole chapter at once and reported this
finding; roughly half of such findings are wrong — inverted attributions, details the
page actually supports. Your job is to decide THIS one, from THESE pages only.

You are given the finding and the cited page with its neighbours.

Return JSON only:
{"observed": "what these pages actually show on the disputed point — who speaks which
line, what the art depicts — stated before any judgement",
 "verdict": "confirmed" | "refuted",
 "evidence": "the exact printed text (bubble, caption, system message) on these pages
that decides it — or, if no text decides it, the specific visual detail",
 "finding": "the error re-stated in one clean sentence, only if confirmed"}

Rules:
- Write "observed" FIRST and make the verdict follow from it — a verdict written
  before looking is exactly the failure you are correcting.
- confirmed means the finding's "problem" statement is EXACTLY what these pages show,
  AND the narration quote contradicts it. If the problem statement misdescribes the
  pages — even slightly, even if the narration has some other flaw — the verdict is
  refuted: a wrong correction is worse than a missed one, and anything else you notice
  is not your question. If the pages support the narration, or do not decide the
  question, the verdict is likewise refuted — a recap is only corrected on evidence,
  never on doubt.
- For WHO-did-what claims: confirm only if the page itself identifies the actor —
  a bubble tail, a printed name, or the flow of address. A line saying "YOU did X"
  is spoken BY the other character, ABOUT the one addressed; quoting such a line
  does not by itself tell you the speaker's name.
- For claims about what the ART shows (anatomy, direction, injuries): confirm only
  when the drawing is unambiguous. Gore, partial figures and motion smears are
  routinely misread — when you cannot be certain, the verdict is refuted.
- Quote evidence exactly as printed. Do not paraphrase printed text.
- Judge only the cited problem. Other flaws in the narration are not your question."""

_REVISE_SYSTEM = """You are correcting specific factual errors in a finished recap.

Change ONLY what the findings identify. Preserve every other sentence verbatim —
including voice, asides, casual register, profanity, paragraph breaks and the overall
shape. Do not reorder, do not tighten, do not improve anything you were not asked about.
Do not add new material.

Return the full corrected narration as plain prose paragraphs, nothing else."""


def _undelivered_spine(text: str, facts: dict[str, Any]) -> list[str]:
    """System messages the narration never delivered.

    Compared on content words rather than verbatim: a recap SHOULD paraphrase
    "[YOU HAVE COMPLETELY ABSORBED THE FROST QUEEN'S NUCLEUS.]" rather than read it out,
    so requiring the literal string would flag correct writing. Half the message's
    distinctive words appearing somewhere in the narration is the bar.
    """
    lowered = set(re.findall(r"[a-z']+", (text or "").lower()))
    missing: list[str] = []
    seen: set[str] = set()
    for message in facts.get("system_messages") or []:
        text_of = str(message).strip()
        key = text_of.lower()
        if key in seen:
            # A chapter prints the same message twice; asking for it twice made the
            # reviser paste it in twice.
            continue
        seen.add(key)
        words = [w for w in re.findall(r"[a-z']+", key) if len(w) > 3]
        # Ceremony with no story content is not spine. Requiring it drove the reviser to
        # paste bracketed text verbatim into the prose — which the writer's own brief
        # forbids, and which reads as a screen-reader rather than a narrator.
        #
        # Threshold measured against Frozen Player's 22 real messages, not guessed. At 3
        # distinctive words it drops exactly the ceremony ("[CONGRATULATIONS.]" 1,
        # "[2ND FLOOR]" 1, "[ABSORPTION RATE 100%.]" 2, "[AUTHENTICATION SUCCESSFUL.]" 2)
        # and keeps every plot-bearing one. Note "[INSUFFICIENT MAGIC STATS.]" sits
        # EXACTLY at 3 and is genuine spine — it is the cliffhanger's mechanism — so 3 is
        # the only workable value: 4 would discard the beat this gate most exists for.
        if len(set(words)) < _MIN_SPINE_WORDS:
            continue
        hits = sum(1 for w in set(words) if w in lowered)
        if hits < max(1, len(set(words)) // 2):
            missing.append(text_of)
    return missing


def _facts_block(facts: dict[str, Any] | None, chapters: int = 2) -> str:
    """The read pass's own account of these pages, as a who-did-what checklist.

    Keys are `plot_spine` and `cast`, not `spine` — `key_dialogue` and `cast` hold dicts,
    so they are formatted rather than str()-ed, which would have put Python repr into the
    prompt.

    Bounded deliberately: the spine, the cast notes and the printed lines are what carry
    attribution, and a wall of facts would drown the pages themselves in the prompt.
    """
    if not facts:
        return ""

    # Slices scale with the range. 30/15/15 is a checklist for two chapters and a
    # silent content drop for twenty, where the cast alone runs past fifteen.
    span = max(1, chapters)
    spine = [str(x).strip() for x in (facts.get("plot_spine") or []) if str(x).strip()][:15 * span]
    cast = [c for c in (facts.get("cast") or []) if isinstance(c, dict)][:8 * span]
    lines = [d for d in (facts.get("key_dialogue") or []) if isinstance(d, dict)][:8 * span]
    if not (spine or cast or lines):
        return ""

    out = ["\n\nCHAPTER FACTS (extracted from these pages before the recap was written):"]
    if cast:
        out.append("Who is who:")
        for c in cast:
            alias = ", ".join(str(a) for a in (c.get("aliases") or []))
            note = str(c.get("note") or "").strip()
            tail = " — ".join(x for x in (note, f"also called {alias}" if alias else "") if x)
            out.append(f"- {c.get('name', '?')}{': ' + tail if tail else ''}")
    if spine:
        out.append("What happens, in order:")
        out += [f"- {x}" for x in spine]
    if lines:
        out.append("Lines the pages actually print:")
        for d in lines:
            speaker = str(d.get("speaker") or "?").strip()
            line = str(d.get("line") or "").strip()
            if line:
                out.append(f'- {speaker}: "{line}"')
    return "\n".join(out)


def _chapter_span(paths: dict[str, Path]) -> int:
    """How many chapters this project covers, for the facts-block allowances.

    Read from project.json rather than threaded through every caller: the audit's
    signature is used in several tests and a required argument would rewrite them all
    to say the same thing. Absent or unreadable, two — the size this pass was tuned at.
    """
    try:
        from manhwa2vid.script.freeform import _chapter_count

        meta_path = Path(paths.get("root", ".")) / "project.json"
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
        return _chapter_count(type("_M", (), {"chapters": raw.get("chapters", "")})())
    except Exception:  # noqa: BLE001 — allowances, not correctness
        return 2


def audit_script(
    text: str,
    paths: dict[str, Path],
    config: dict[str, Any],
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Grounding findings plus undelivered spine items. Pure reporting."""
    from manhwa2vid.llm.provider import get_llm_provider

    pages = sorted(paths["pages"].glob("*.png"))
    provider = get_llm_provider(get_nested(config, "audit", "provider", default=None), config)
    model = get_nested(config, "audit", "model", default=None)
    if model:
        provider.vision_model = model
    provider.temperature = 0.0

    # The read pass already extracted what happens on these pages, and the auditor was
    # never shown it — `facts` reached only `_undelivered_spine`. That is how "He is
    # missing his right arm below the elbow" survived into Solo Leveling's opening line
    # while chapter_facts.json plainly said "Song Chi-Yul loses his arm in the initial
    # attack". Re-deriving from a drawing of a bloodied figure is exactly the judgement
    # the read pass already made, with more context than the auditor has.
    # Windowed since 2026-09-01, for the reason this file already documents about
    # itself: at 19-156 pages in one call, 5 of 8 findings checked by hand were false.
    # A 20-chapter range is 235 pages. The narration and the facts go to EVERY window —
    # a finding is a claim about the narration as a whole — while the pages are split,
    # so each call answers about a range it can actually attend to.
    from manhwa2vid.script.freeform import _page_windows

    max_pages = int(get_nested(config, "audit", "max_pages_per_call", default=60))
    windows = _page_windows(pages, max_pages)
    chapters = _chapter_span(paths)
    # A window sees a SLICE of the pages but the WHOLE narration, because a finding is a
    # claim about narration and we cannot know which pages a sentence refers to before
    # the aligner has run. Without saying so, the window does the obvious thing: it reads
    # narration about chapter 15, finds no page supporting it among chapters 1-5, and
    # reports an error. Measured on the first 20-chapter run: 119 majors against 1 for a
    # 2-chapter script — an inflation created entirely by windowing, and the reason this
    # note exists.
    slice_note = (
        "\n\nIMPORTANT — THESE PAGES ARE A SLICE. The narration below covers a longer "
        "chapter range than the pages you can see. Judge ONLY sentences describing what "
        "is on THESE pages. If a sentence describes events that are not here, it belongs "
        "to another slice: say nothing about it. The absence of a page is NEVER evidence "
        "that the narration is wrong."
        if len(windows) > 1 else ""
    )
    prompt = (
        f"{_AUDIT_SYSTEM}{slice_note}{_facts_block(facts, chapters)}"
        f"\n\nRECAP NARRATION:\n\n{text}"
    )
    findings: list[dict[str, Any]] = []
    for i, window in enumerate(windows, start=1):
        provider.set_json_budget(_JSON_BUDGET_TOKENS)
        raw = provider.describe_labeled_panels(
            [(f"[page {p.stem}]", p) for p in window],
            prompt,
            max_width=page_max_width(config),
        )
        # A truncated audit returns zero findings, which is indistinguishable from a
        # clean script — the most dangerous silent failure here, because it produces a
        # green grounding gate over narration nobody checked.
        provider.raise_if_truncated(f"audit pass (findings, window {i}/{len(windows)})")
        data = json.loads(raw) if isinstance(raw, str) else raw
        findings.extend(
            f for f in ((data or {}).get("findings") or []) if isinstance(f, dict)
        )
    # The same drift can be reported from two windows that both show the page; the
    # verification stage would then pay for it twice and the reviser would see it twice.
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for f in findings:
        key = (str(f.get("quote", "")).strip().lower(), str(f.get("page", "")).strip())
        if key not in seen:
            seen.add(key)
            deduped.append(f)
    findings = deduped
    majors = [f for f in findings if str(f.get("severity", "")).lower() == "major"]
    confirmed, unverified = verify_majors(majors, paths, config, provider=provider, facts=facts)
    return {
        "findings": findings,
        "majors": confirmed,
        "unverified": unverified,
        "undelivered_system_messages": _undelivered_spine(text, facts or {}),
    }


def _pages_for_finding(page_ref: Any, pages: list[Path]) -> list[Path]:
    """The cited page ±2, resolved leniently ("0012", "12", "page 12"), else [].

    ±2, not ±1: measured on the benchmark findings, the stage-1 auditor's citations
    run up to two pages early — the runner-bisection finding cited 0140 while the
    deciding art (severed lower legs, upper half gone) prints on 0142."""
    digits = re.sub(r"\D", "", str(page_ref or ""))
    if not digits:
        return []
    want = int(digits)
    for i, p in enumerate(pages):
        stem_digits = re.sub(r"\D", "", p.stem)
        if stem_digits and int(stem_digits) == want:
            return pages[max(0, i - 2) : i + 3]
    return []


def verify_majors(
    majors: list[dict[str, Any]],
    paths: dict[str, Path],
    config: dict[str, Any],
    provider: Any = None,
    facts: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(confirmed, unverified) — one single-page vision call per major finding.

    The stage-1 auditor holds 19-156 page images in one call and demonstrably does not
    re-examine the page it cites while writing a finding: of 8 findings checked against
    their pages by hand (2026-08-30), 5 were false — a vendor inversion, an arm read as
    a torso, a vertical bisection read as horizontal, two mis-attributions — and one
    contained leaked chain-of-thought ("...but wait, let me check"). Every one was
    decidable the moment the cited page was looked at ALONE, so that is what this stage
    does: the finding, the cited page ±1, confirm-or-refute with the deciding text
    quoted. Refuted or undecidable findings leave `majors` — `revise_once` acts only on
    verified errors — but are kept under `unverified` for the human.

    A finding that names no locatable page cannot be verified and is parked, not
    trusted: an unverifiable accusation against narration that survived the writer,
    the facts pass and the density pass is worth a human eye, never an automatic edit.
    A provider error parks the finding the same way rather than silently accepting it.
    """
    if not majors:
        return [], []
    if provider is None:
        from manhwa2vid.llm.provider import get_llm_provider

        provider = get_llm_provider(
            get_nested(config, "audit", "provider", default=None), config
        )
        model = get_nested(config, "audit", "model", default=None)
        if model:
            provider.vision_model = model
        provider.temperature = 0.0

    pages = sorted(paths["pages"].glob("*.png"))
    # Who-is-who from the read pass, for attribution findings: the Kim/Song core swap
    # is only decidable if the verifier knows Mr. Song is the orange-haired party
    # leader — the page shows the man, the glossary names him. Cast only, not the
    # spine: the spine narrates outcomes, and outcome text would prejudge the verdict.
    cast_lines: list[str] = []
    for c in (facts or {}).get("cast") or []:
        if isinstance(c, dict) and c.get("name"):
            note = str(c.get("note") or "").strip()
            cast_lines.append(f"- {c['name']}{': ' + note if note else ''}")
    cast_block = (
        "\n\nWHO IS WHO (from a separate read of this chapter):\n" + "\n".join(cast_lines)
        if cast_lines else ""
    )
    confirmed: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []
    for finding in majors:
        cited = _pages_for_finding(finding.get("page"), pages)
        if not cited:
            unverified.append({**finding, "verification": "no locatable page"})
            continue
        prompt = (
            f"{_VERIFY_SYSTEM}{cast_block}\n\nFINDING TO VERIFY:\n"
            f"- narration says: {finding.get('quote', '')!r}\n"
            f"- claimed problem: {finding.get('problem', '')}\n"
            f"- cited page: {finding.get('page', '?')}"
        )
        try:
            raw = provider.describe_labeled_panels(
                [(f"[page {p.stem}]", p) for p in cited],
                prompt,
                max_width=page_max_width(config),
            )
            data = json.loads(raw) if isinstance(raw, str) else raw
            verdict = str((data or {}).get("verdict", "")).lower().strip()
        except Exception as exc:  # noqa: BLE001 — park it, never auto-accept
            unverified.append({**finding, "verification": f"error: {exc}"})
            continue
        if verdict == "confirmed":
            restated = str(data.get("finding") or "").strip()
            confirmed.append({
                **finding,
                # The clean re-statement replaces the stage-1 problem text — this is
                # where leaked chain-of-thought dies instead of reaching the reviser.
                "problem": restated or finding.get("problem", ""),
                "verification": {"verdict": "confirmed",
                                 "evidence": str(data.get("evidence") or "")},
            })
        elif verdict == "refuted":
            unverified.append({
                **finding,
                "verification": {"verdict": "refuted",
                                 "evidence": str(data.get("evidence") or "")},
            })
        else:
            unverified.append({**finding, "verification": f"unparseable verdict: {verdict!r}"})
    if unverified:
        console.print(
            f"[yellow]Audit verification[/] — {len(confirmed)} confirmed, "
            f"{len(unverified)} refuted/unverifiable finding(s) parked"
        )
    return confirmed, unverified


def acceptance_failures(
    original: str,
    revised: str,
    majors: list[dict[str, Any]],
    glossary_names: set[str],
) -> list[str]:
    """Why a revision must be rejected; empty means acceptable.

    Replaces the finding-count comparison, which failed in BOTH directions in one day:
    it rejected a correct Mr. Kim -> Mr. Song fix because the re-audit's own noise went
    1 -> 2, and it accepted a text that went 8 -> 7 while replacing the correct name
    "Mr. Song" with "the hunter with orange hair" in four places — seven "wrong name"
    findings become zero findings if nobody is named. The count measures the auditor's
    noise floor, not the revision's quality, so it is no longer consulted at all (which
    also saves the re-audit vision call).

    Checks, all deterministic:
    - every targeted quote actually changed — an untouched quote means the finding was
      ignored, however good the rest looks;
    - TOTAL glossary-name occurrences do not decrease. Total, not per-name: a correct
      wrong-name fix lowers one name's count while raising another's, but a
      name -> descriptor swap lowers the total, which is exactly the regression that
      shipped;
    - no new placeholder descriptors (the `strip_placeholder_descriptors` class);
    - word count within ±15% — narration is audio-locked, so word count IS runtime.
    """
    import re as _re

    from manhwa2vid.script.lint import _PLACEHOLDER_ADJ_RE

    failures: list[str] = []

    for f in majors:
        quote = str(f.get("quote") or "").strip()
        if quote and quote in original and quote in revised:
            failures.append(f"finding ignored — quote unchanged: {quote[:60]!r}")

    def _name_total(text: str) -> int:
        return sum(
            len(_re.findall(rf"\b{_re.escape(n)}\b", text)) for n in glossary_names
        )

    if glossary_names:
        before_n, after_n = _name_total(original), _name_total(revised)
        if after_n < before_n:
            failures.append(
                f"glossary names dropped {before_n} -> {after_n} — a name was replaced "
                "with a description"
            )

    before_p = len(_PLACEHOLDER_ADJ_RE.findall(original))
    after_p = len(_PLACEHOLDER_ADJ_RE.findall(revised))
    if after_p > before_p:
        failures.append(f"placeholder descriptors grew {before_p} -> {after_p}")

    # ±15%, with a 40-word absolute grace: word count IS runtime, but a repair that
    # delivers five missing system messages legitimately ADDS sentences, and on a
    # short text a pure percentage rejects any real fix.
    wc_before, wc_after = len(original.split()), len(revised.split())
    if wc_before and abs(wc_after - wc_before) > max(0.15 * wc_before, 40):
        failures.append(f"length moved {wc_before} -> {wc_after} words (±15% budget)")

    return failures


def revise_once(
    text: str,
    audit: dict[str, Any],
    paths: dict[str, Path],
    config: dict[str, Any],
    facts: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """One corrective pass, kept only if it strictly improves. Returns (text, report)."""
    majors = audit.get("majors") or []
    missing = audit.get("undelivered_system_messages") or []
    if not majors and not missing:
        return text, {"revised": False, "reason": "clean", "before": 0, "after": 0}

    issues = [
        f"- WRONG: {f.get('quote', '')!r} — {f.get('problem', '')} (page {f.get('page', '?')})"
        for f in majors
    ]
    issues += [
        f"- MISSING: the narration never conveys what {m!r} SAYS. Work its meaning into "
        "the prose in your own words — do NOT quote the bracketed text."
        for m in missing
    ]

    from manhwa2vid.llm.provider import get_llm_provider

    provider = get_llm_provider(get_nested(config, "audit", "provider", default=None), config)
    model = get_nested(config, "audit", "model", default=None)
    if model:
        provider.vision_model = model
    provider.temperature = 0.0

    pages = sorted(paths["pages"].glob("*.png"))
    revised = provider.describe_labeled_panels_text(
        [(f"[page {p.stem}]", p) for p in pages],
        _REVISE_SYSTEM,
        "FINDINGS TO FIX:\n" + "\n".join(issues) + f"\n\nCURRENT NARRATION:\n\n{text}",
        max_width=page_max_width(config),
    ).strip()

    before = len(majors) + len(missing)
    if not revised:
        return text, {"revised": False, "reason": "empty revision", "before": before, "after": before}

    from manhwa2vid.script.read import glossary_names

    failures = acceptance_failures(text, revised, majors, glossary_names(paths))
    if failures:
        # Keeping a bad revision is how "a later pass undoes an earlier pass's work"
        # became this project's most repeated defect; the original stands and the
        # human is told exactly why.
        console.print(
            "[yellow]Revision rejected[/] — " + "; ".join(failures[:3])
        )
        return text, {
            "revised": False,
            "reason": "acceptance failed",
            "failures": failures,
            "before": before,
            "residual": majors + [{"missing": m} for m in missing],
        }

    console.print(f"[green]Revision accepted[/] — {before} finding(s) addressed")
    return revised, {
        "revised": True,
        "before": before,
        "failures": [],
        "residual": [],
    }


def audit_and_revise(
    text: str,
    paths: dict[str, Path],
    config: dict[str, Any],
    facts: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """The whole accountability step: audit, at most one revision, persist the record."""
    audit = audit_script(text, paths, config, facts)
    console.print(
        f"[cyan]Audit[/] — {len(audit['majors'])} major finding(s), "
        f"{len(audit['undelivered_system_messages'])} undelivered system message(s)"
    )
    final, revision = revise_once(text, audit, paths, config, facts)
    record = {"audit": audit, "revision": revision}
    save_json(paths["script_audit_json"], record)
    return final, record
