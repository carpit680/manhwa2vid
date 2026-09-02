"""Match narration sentences to the panels that depict them — the shot list.

This is the piece the freeform pipeline was missing. Panels were apportioned to
paragraphs arithmetically, so nothing ever checked what a panel SHOWS against what the
sentence SAYS — sky under action, scenery under dialogue, drift past the narration. The
user's standard, and Mamoru's measured practice (median shot 2.9s ≈ one sentence of
airtime), is that the sentence is the shot: the screen shows what is being said, for as
long as it is being said.

Two halves, deliberately separated:

- **Matching** (vision calls, align stage): which panels literally depict each sentence.
  Windowed at 16 panels per call with interleaved id labels — the measured limit before
  id binding drifts (+3 shift at 59 images). Saved to `script.shotlist.json`.
- **Planning** (pure code, timeline stage): join the claims with the TTS sidecar's
  measured per-sentence seconds into explicit (panel, seconds) shots. Durations cannot
  exist at align time — sidecars are written at synthesis — so the artifact stores
  claims, not seconds.

Failure direction is chosen (user decision): a sentence with no surviving claim HOLDS
the previous shot rather than showing a weak candidate. A bad model claim degrades to a
longer hold, never to an unrelated image.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.models import Panel, save_json
from manhwa2vid.script.sentences import split_sentences

console = Console()

_SYSTEM = """You match narration sentences to the manhwa panels that DEPICT them.

You are given numbered sentences from a recap narration, then a batch of labeled
panels. For each sentence, name the panel(s) from THIS batch that literally show what
it says.

Return JSON only:
{"claims": [{"sentence": 7, "panels": ["p0005_02"]}, ...]}

Rules:
- Claim a panel only if it DEPICTS the sentence: the action happening, the speaker
  speaking, the place being described. A scenery sentence claiming a scenery panel is
  correct; an action sentence claiming a sky or empty-background panel is wrong.
- A sentence of pure narrator commentary ("which is probably smart when you're the
  weakest in the room") depicts nothing — claim nothing for it.
- At most 3 panels per sentence, in reading order. Panels may go unclaimed.
- Only use panel ids from this batch. Only use sentence numbers from the list.
- The narration tells this batch's part of the story roughly in order; wildly
  out-of-order matches are usually wrong."""


def _window(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _window_sentences(
    sentences: list[tuple[int, str]],
    batch: list[Panel],
    sentence_pages: dict[int, tuple[int, int]] | None,
    *,
    page_margin: int = 1,
) -> list[tuple[int, str]]:
    """The sentences plausibly depicted by THIS window's panels.

    Every window used to receive the ENTIRE block's sentence list — ~174 sentences
    against 16 panels on Solo Leveling's first block — so distant windows independently
    claimed the same sentences, and the monotonic filter then destroyed all but one of
    each set: ~30% of raw claims died this way, and every death was a sentence that
    reads as "unmatched" in the gate.

    The scope comes from the aligner's advisory paragraph->page map (each sentence
    inherits its paragraph's page range, pre-widened by ±1 paragraph upstream), further
    widened by `page_margin` here. The map is advisory and can collapse — a sentence
    with no entry is always included, and an empty scope falls back to the full list,
    which is exactly the old behaviour.
    """
    if not sentence_pages:
        return sentences
    pages = [p.page_num for p in batch]
    lo, hi = min(pages) - page_margin, max(pages) + page_margin
    scoped = [
        (n, t) for n, t in sentences
        if n not in sentence_pages
        or (sentence_pages[n][0] <= hi and sentence_pages[n][1] >= lo)
    ]
    return scoped or sentences


_MATCHER_PROVIDER: Any = None


def _matcher_provider(config: dict[str, Any]) -> Any:
    """One provider for the whole matching stage, so its usage totals are one number.

    `collect_claims` used to build a fresh provider per call — ~100 of them on a
    20-chapter range — which made "what did matching cost" unanswerable. Cached on the
    module for the process lifetime; tests that stub `collect_claims` never reach it.
    """
    global _MATCHER_PROVIDER
    if _MATCHER_PROVIDER is None:
        from manhwa2vid.llm.provider import get_llm_provider

        _MATCHER_PROVIDER = get_llm_provider(
            get_nested(config, "align", "provider", default=None), config
        )
    return _MATCHER_PROVIDER


def collect_claims(
    sentences: list[tuple[int, str]],
    panels: list[Panel],
    paths: dict[str, Path],
    config: dict[str, Any],
    sentence_pages: dict[int, tuple[int, int]] | None = None,
    system: str | None = None,
) -> list[tuple[int, str]]:
    """(sentence_number, panel_id) claims from windowed vision calls. Raw, unfiltered.

    `system` overrides the prompt — the second pass (`_second_pass_claims`) asks with a
    more willing framing than the conservative first pass."""
    provider = _matcher_provider(config)
    model = get_nested(config, "align", "match_model", default=None)
    if model:
        provider.vision_model = model
    provider.temperature = 0.0

    window_size = int(get_nested(config, "align", "match_window_panels", default=16))
    valid_ids = {p.id for p in panels}
    valid_numbers = {n for n, _ in sentences}

    claims: list[tuple[int, str]] = []
    truncated_windows = 0
    for batch in _window(panels, window_size):
        scoped = _window_sentences(sentences, batch, sentence_pages)
        numbered = "\n".join(f"[{n}] {t}" for n, t in scoped)
        raw = provider.describe_labeled_panels(
            [(f"[{p.id}]", paths["root"] / p.image_path) for p in batch],
            f"{system or _SYSTEM}\n\nSENTENCES:\n{numbered}",
        )
        # NOT raise_if_truncated: this loop makes one call per 16-panel window and a
        # truncated window is a partial loss, not a corrupt artifact — aborting would
        # throw away a hundred good calls over one. It must still be COUNTED, because
        # the symptom (a few sentences quietly unmatched) is invisible in the gates,
        # which only see a slightly lower match rate.
        if getattr(provider, "last_finish_reason", "") == "length":
            truncated_windows += 1
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            continue
        # The model sometimes returns the claims ARRAY bare instead of wrapped in
        # {"claims": [...]}. `data.get` then raised AttributeError, which escaped this
        # function entirely and was swallowed by align.py's blanket except — the run
        # continued with NO shotlist and the planner fell back to airtime weighting.
        # It happened twice on Solo Leveling before being traced. A bare list is
        # unambiguous here; accept it.
        if isinstance(data, list):
            data = {"claims": data}
        if not isinstance(data, dict):
            continue
        batch_ids = {p.id for p in batch}
        for claim in data.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            try:
                number = int(claim.get("sentence"))
            except (TypeError, ValueError):
                continue
            for pid in (claim.get("panels") or [])[:3]:
                if number in valid_numbers and pid in batch_ids and pid in valid_ids:
                    claims.append((number, str(pid)))
    if truncated_windows:
        console.print(
            f"[yellow]Matcher[/] — {truncated_windows} of "
            f"{len(_window(panels, window_size))} window(s) hit the output cap; their "
            f"claims are incomplete and those sentences will fall back to the fill"
        )
    return claims


#: How far BACK a claim, spare, or on-screen cut may legally step, in panels.
#: A recap's narration order and the page's panel order disagree at fine scale all the
#: time — the writer describes the close-up, then the establishing shot two panels
#: earlier, and the reference channel cuts exactly that way. Measured cost of zero
#: tolerance on Solo Leveling: s62 ("the party wanders over and stares into a dark,
#: winding tunnel") was correctly claimed to p0042_01 — literally the party staring
#: into a cave mouth — and dropped because another sentence had claimed a panel two
#: positions later. The fill then parked six sentences on a fireball for 16.5s, the
#: 2:43-2:57 stretch the user reported as "narration on unrelated frames".
#:
#: 8 panels ≈ one page: within a scene. The jumps the user originally reported were
#: 26-71 panels — other scenes entirely — and stay illegal. User decision 2026-08-30.
SCENE_RADIUS = 8


def filter_monotonic(
    claims: list[tuple[int, str]], panel_order: list[str]
) -> list[tuple[int, str]]:
    """Largest consistent claim set: sentence and panel order must agree TO SCENE SCALE.

    Chain constraint since 2026-08-30: each panel shown once, sentence numbers never
    decrease, and a later sentence's panel may sit up to SCENE_RADIUS panels BEHIND the
    chain's furthest point — the close-up-then-establishing-shot cut. Beyond that, a
    claim contradicts the story's forward motion and is dropped rather than negotiated
    with.

    The OBJECTIVE changed on 2026-08-28, measured from the persisted raw claims. The
    original longest-chain DP maximised total CLAIMS, so a sentence's second and third
    accent panels outcompeted another sentence's only panel: on Solo Leveling's first
    block the model claimed 136 distinct sentences and the longest chain kept 87 — 49
    sentences lost entirely, every one reading as "unmatched" in the gate while its
    panel budget went to someone's accent shot. The product counts sentences with a
    picture of their own, so the DP now maximises (distinct sentences, then total
    claims). Distinctness is a valid per-step increment because claims are sorted by
    sentence and the chain is non-decreasing in sentence, so all of a sentence's kept
    claims sit consecutively — whether claim i starts a new sentence depends only on
    the element before it. O(n^2), n is a block's claims (low hundreds), chosen over
    cleverer forms because it is obviously correct.
    """
    pos = {pid: i for i, pid in enumerate(panel_order)}
    items = sorted(
        {(number, pid) for number, pid in claims if pid in pos},
        key=lambda c: (c[0], pos[c[1]]),
    )
    if not items:
        return []
    # Phase 1 — the strict chain, exactly as before 2026-08-30: positions strictly
    # increase, so it is repeat-free by construction and the distinct-sentence
    # objective keeps its proof.
    # score = (distinct sentences in chain, total claims in chain)
    best = [(1, 1)] * len(items)
    parent = [-1] * len(items)
    for i, (sent_i, pid_i) in enumerate(items):
        for j in range(i):
            sent_j, pid_j = items[j]
            if sent_j <= sent_i and pos[pid_j] < pos[pid_i]:
                cand = (best[j][0] + (1 if sent_i != sent_j else 0), best[j][1] + 1)
                if cand > best[i]:
                    best[i] = cand
                    parent[i] = j
    end = max(range(len(items)), key=lambda i: best[i])
    chain: list[tuple[int, str]] = []
    while end != -1:
        chain.append(items[end])
        end = parent[end]
    chain.reverse()

    # Phase 2 — scene-radius recovery. A dropped claim rejoins when it steps backward
    # by at most SCENE_RADIUS from the chain's high-water position, onto a panel the
    # chain does not already use. Doing recovery as a separate pass (rather than
    # loosening the DP) keeps three properties at once: no repeats (a tolerant DP
    # happily chained p1, p2, back-to-p1, and a post-hoc dedup then gutted the chain),
    # no compounding (high-water comes from the strict chain, which an inserted
    # backward claim never raises), and the distinct-sentence objective untouched.
    chain_set = set(chain)
    used_pids = {pid for _n, pid in chain}
    recovered: list[tuple[int, str]] = []
    high = -1
    for item in items:
        number, pid = item
        if item in chain_set:
            recovered.append(item)
            high = max(high, pos[pid])
            continue
        if pid not in used_pids and high - SCENE_RADIUS <= pos[pid] < high:
            recovered.append(item)
            used_pids.add(pid)

    # Phase 3 — adjacent co-claims (2026-08-31). Measured on Solo Leveling: of the 70
    # sentences whose every claim the filter destroyed, 50 lost to PANEL CONTENTION
    # with a neighbouring sentence — two consecutive sentences describe one moment,
    # both claim its panel, the chain keeps one. On screen the loser inherited the
    # same picture anyway, as an unmatched HOLD; the honest description is that both
    # sentences depict that panel. So a dropped claim whose panel a NEIGHBOUR keeps
    # (|Δsentence| ≤ 2) rejoins as a co-claim of the same panel.
    #
    # Repeat-freedom is preserved by three conditions, each load-bearing:
    # - the co-claiming sentence must have NO kept claims of its own — this pass exists
    #   for total losers, and a sentence with its own panel plus a co-claim would put
    #   the shared panel out of sequence;
    # - the panel must sit on the FACING EDGE of the keeper's claims (last panel when
    #   the co-claimant follows, first when it precedes) — else the keeper's other
    #   panel plays between the two showings and the fold cannot merge them;
    # - no sentence strictly between the pair may hold a kept claim — an intervening
    #   claimed sentence's panel would likewise split the pair. Unclaimed sentences
    #   between are fine: the planner holds them on the previous shot, and the fill's
    #   anchor gap (same panel to same panel) is empty by construction.
    # Under these, the planner's fold pass collapses the pair into ONE shot carrying
    # both sentence numbers — the panel still appears exactly once.
    kept_set = set(recovered)
    claims_of: dict[int, list[str]] = {}
    for number, pid in recovered:                 # items order: pos-sorted per sentence
        claims_of.setdefault(number, []).append(pid)
    keepers_of: dict[str, list[int]] = {}
    for number, pid in recovered:
        keepers_of.setdefault(pid, []).append(number)
    co: list[tuple[int, str]] = []
    co_sentences: set[int] = set()
    for number, pid in items:
        if (number, pid) in kept_set or number in claims_of or number in co_sentences:
            continue
        for keeper in keepers_of.get(pid, []):
            if abs(number - keeper) > 2:
                continue
            edge = claims_of[keeper][-1] if number > keeper else claims_of[keeper][0]
            if edge != pid:
                continue
            lo_n, hi_n = min(number, keeper), max(number, keeper)
            if any(q in claims_of for q in range(lo_n + 1, hi_n)):
                continue
            co.append((number, pid))
            co_sentences.add(number)
            break
    if co:
        recovered = sorted(recovered + co, key=lambda c: (c[0], pos[c[1]]))
    return recovered



_SECOND_PASS_SYSTEM = """You are matching recap narration to manhwa panels — a
SECOND pass over sentences a first pass left without any panel. These sentences will
otherwise share one unrelated image for many seconds, so a defensible claim now is
worth more than silence: claim a panel whenever one plausibly DEPICTS the sentence's
moment — the character, the object, the action, or the place it describes. Do not
claim for pure narrator commentary with nothing to show.

Return JSON only: {"claims": [{"sentence": <number>, "panels": ["<panel id>"]}]}"""


#: Claims above this for ONE sentence mean the model found the sentence generic, not
#: depicted — see the drop in `_second_pass_claims`.
_SECOND_PASS_MAX_PER_SENTENCE = 3

#: A short (1-2 sentence) gap is probed only when its anchor window holds at most this
#: many unused panels — more means the window is not really anchored and a claim from
#: it would be a guess. Observed windows for real short gaps run 1-6 panels.
_SHORT_GAP_MAX_CANDIDATES = 8


def _second_pass_claims(
    block_sents: list[tuple[int, str]],
    panels: list[Panel],
    kept: list[tuple[int, str]],
    paths: dict[str, Path],
    config: dict[str, Any],
) -> list[tuple[int, str]]:
    """Re-ask the model about unclaimed runs, against unused panels.

    Measured need (Solo Leveling, 2:43-2:57): the first pass claimed nothing for six
    consecutive sentences — Jin-Woo's palm, the tiny core, the money — and the fill
    parked all of them on a fireball for 16.5 seconds. Match rate 48.6% means half the
    video rides on fill guesswork; the expensive stretches are exactly these runs.

    Bounded: runs of 3+ consecutive unclaimed sentences see the block's whole unused
    pool; SHORT gaps (1-2 sentences, added 2026-08-31) see only the unused panels
    strictly between their surrounding anchors, and only when that window holds
    1-`_SHORT_GAP_MAX_CANDIDATES` panels — a wide window means the model would be
    guessing, and the fill already handles it. Measured need for the short form:
    depictable one-liners ("This is Miss Ju-Hee", "Jun-Woo laughs") sat in 1-2-sentence
    gaps the 3+ rule never touched — a third of the never-matched bucket on all three
    titles. One vision call per run either way; output joins the RAW claims and re-runs
    through `filter_monotonic`, so a wild second-pass claim is subject to the same
    order discipline as everything else.
    """
    claimed_nums = {no for no, _pid in kept}
    used_pids = {pid for _no, pid in kept}
    runs: list[list[tuple[int, str]]] = []
    cur: list[tuple[int, str]] = []
    for no, text in block_sents:
        if no in claimed_nums:
            if cur:
                runs.append(cur)
            cur = []
        else:
            cur.append((no, text))
    if cur:
        runs.append(cur)
    if not runs:
        return []

    spare_panels = [p for p in panels if p.id not in used_pids]
    if not spare_panels:
        return []

    pos = {p.id: i for i, p in enumerate(panels)}
    out: list[tuple[int, str]] = []
    for run in runs:
        if len(run) >= 3:
            candidates = spare_panels
        else:
            first, last = run[0][0], run[-1][0]
            prev_pos = max(
                (pos[pid] for no, pid in kept if no < first and pid in pos), default=-1
            )
            next_pos = min(
                (pos[pid] for no, pid in kept if no > last and pid in pos),
                default=len(panels),
            )
            candidates = [
                p for p in spare_panels if prev_pos < pos[p.id] < next_pos
            ]
            if not 1 <= len(candidates) <= _SHORT_GAP_MAX_CANDIDATES:
                continue
        found = collect_claims(
            run, candidates, paths, config, None, system=_SECOND_PASS_SYSTEM
        )
        # A sentence the model matches to MANY panels matched none of them. The willing
        # framing makes generic narration attractive to everything: Solo Leveling's
        # "It is a miserable life" drew six claims spanning p0006 to p0100, and the two
        # that survived the order filter put a 10-panel rewind on screen. Real depiction
        # is specific, so more than _SECOND_PASS_MAX_PER_SENTENCE claims for one
        # sentence is a signal to drop that sentence's claims entirely and let it
        # inherit the picture — which is the honest outcome for commentary.
        by_sentence: dict[int, list[str]] = {}
        for number, pid in found:
            by_sentence.setdefault(number, []).append(pid)
        for number, pids in by_sentence.items():
            if len(pids) <= _SECOND_PASS_MAX_PER_SENTENCE:
                out.extend((number, pid) for pid in pids)
    return out


#: A candidate paragraph must be this starved at home before a return is even probed.
_RETURN_STARVED_MAX = 0.25
#: ...and the probe must claim at least this share of its sentences, and this many.
_RETURN_PROBE_MIN_FRAC = 0.50
_RETURN_PROBE_MIN_SENTENCES = 3


def _coverage(sent_numbers: list[int], claims: list[tuple[int, str]]) -> float:
    if not sent_numbers:
        return 1.0
    have = {no for no, _pid in claims} & set(sent_numbers)
    return len(have) / len(sent_numbers)


def resolve_returns(
    candidate_beats: set[int],
    numbered: list[tuple[int, str, int]],
    block_of_sentence: list[int],
    blocks_panels: list[list[Panel]],
    per_block: dict[int, dict[str, Any]],
    paths: dict[str, Path],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Move a starving announcing paragraph to the earlier block whose art it describes.

    Frozen Player tells chapter 1 out of page order — cold-open fight, "76 HOURS
    EARLIER" flashback, then RETURN to the fight — and `block_of` was monotonic by
    construction, so the returning paragraph was stranded in the flashback with zero
    claims. Eleven sentences describing a sword fight played over three panels of empty
    sky, and 18 of the fight block's 29 panels were never shown at all.

    Text nominates (`align.return_candidates`), evidence decides. The regex cannot tell
    a return from a departure — "seventy-six hours later" is either, depending where you
    stand — and cannot name a target block. So each candidate is probed against earlier
    blocks and accepted only on claims.

    Two details are load-bearing:

    - the probe passes `sentence_pages=None`. `_window_sentences` scopes windows by the
      aligner's advisory page map, and a returning paragraph's advisory pages point PAST
      the boundary — that misalignment is exactly why `clamp_to_time_blocks` cannot
      trust position. With scoping on, the probe would be filtered to nothing and the
      fix would fail silently in today's shape.
    - the probe sees only the target block's UNUSED panels, so an accepted return cannot
      replay the cold open; `no-repeated-panels` stays true by construction.

    Acceptance also requires the claims to survive `filter_monotonic` against the target
    block's existing chain — a willing model scatters claims, and the DP destroys the
    ones that fight the chain.
    """
    moves: list[dict[str, Any]] = []
    by_beat: dict[int, list[tuple[int, str]]] = {}
    for no, text, beat_id in numbered:
        by_beat.setdefault(beat_id, []).append((no, text))

    for beat_id in sorted(candidate_beats):
        sents = by_beat.get(beat_id) or []
        if not sents:
            continue
        nums = [no for no, _t in sents]
        home = block_of_sentence[nums[0] - 1]
        if home <= 0:
            continue
        home_cov = _coverage(nums, per_block.get(home, {}).get("kept", []))
        if home_cov > _RETURN_STARVED_MAX:
            continue

        for target in range(home - 1, -1, -1):
            entry = per_block.get(target)
            if not entry:
                continue
            panels = blocks_panels[target]
            used = {pid for _no, pid in entry["kept"]}
            spare = [p for p in panels if p.id not in used]
            if len(spare) < _RETURN_PROBE_MIN_SENTENCES:
                continue
            probe = collect_claims(sents, spare, paths, config, None)
            cov = _coverage(nums, probe)
            if cov < _RETURN_PROBE_MIN_FRAC or len({n for n, _ in probe}) < _RETURN_PROBE_MIN_SENTENCES:
                continue
            if cov <= home_cov:
                continue
            merged = filter_monotonic(
                entry["raw"] + probe, [p.id for p in panels]
            )
            if _coverage(nums, merged) < _RETURN_PROBE_MIN_FRAC:
                continue  # the chain destroyed them: scattered, not depicted
            entry["raw"] = entry["raw"] + probe
            entry["kept"] = merged
            for no in nums:
                block_of_sentence[no - 1] = target
            moves.append({
                "beat": beat_id, "from": home, "to": target,
                "sentences": nums, "home_coverage": round(home_cov, 3),
                "probe_coverage": round(cov, 3),
            })
            console.print(
                f"[dim]Match: beat {beat_id} returns to block {target} "
                f"({int(cov * 100)}% of its sentences claim its unused panels)[/]"
            )
            break
    return moves


def build_shotlist(
    beats_sentences: list[tuple[int, list[str]]],
    blocks_panels: list[list[Panel]],
    block_of_sentence: list[int],
    paths: dict[str, Path],
    config: dict[str, Any],
    sentence_pages: dict[int, tuple[int, int]] | None = None,
    return_candidate_beats: set[int] | None = None,
    boundary_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Match every block, save the claims artifact, return it.

    `beats_sentences`: (beat_id, sentences) in order. `block_of_sentence`: block index
    per GLOBAL sentence number (1-based order across all beats). Matching runs per
    block so a claim can never cross a printed time boundary by construction.
    """
    numbered: list[tuple[int, str, int]] = []  # (global_no, text, beat_id)
    n = 0
    for beat_id, sents in beats_sentences:
        for text in sents:
            n += 1
            numbered.append((n, text, beat_id))

    # PASS 1 — every block once, exactly as before. `filter_monotonic` runs ONCE per
    # block over that block's whole panel order, never once per visit: its strictly
    # increasing chain plus radius-recovery is what makes a block repeat-free, and two
    # independent filter calls for two visits of one block would reintroduce repeats.
    block_of_sentence = list(block_of_sentence)   # resolve_returns rewrites entries
    per_block: dict[int, dict[str, Any]] = {}
    for block_idx, panels in enumerate(blocks_panels):
        block_sents = [
            (no, text) for (no, text, _b) in numbered
            if block_of_sentence[no - 1] == block_idx
        ]
        if not block_sents or not panels:
            continue
        raw = collect_claims(block_sents, panels, paths, config, sentence_pages)
        kept = filter_monotonic(raw, [p.id for p in panels])
        console.print(
            f"[dim]Match: block {block_idx} — {len(raw)} claim(s), "
            f"{len(kept)} after monotonic filter[/]"
        )
        per_block[block_idx] = {"raw": raw, "kept": kept, "second": []}

    # RETURN RESOLUTION — before the second pass, deliberately: the second pass's
    # willing framing would otherwise scrape claims for a returning paragraph against
    # the WRONG block's panels and park it there permanently.
    moves = resolve_returns(
        return_candidate_beats or set(), numbered, block_of_sentence,
        blocks_panels, per_block, paths, config,
    )

    # PASS 2 — the willing re-ask for long unclaimed runs, with final membership.
    all_claims: list[tuple[int, str]] = []
    claims_debug: list[dict[str, Any]] = []
    for block_idx, panels in enumerate(blocks_panels):
        entry = per_block.get(block_idx)
        if not entry:
            continue
        block_sents = [
            (no, text) for (no, text, _b) in numbered
            if block_of_sentence[no - 1] == block_idx
        ]
        raw, kept = entry["raw"], entry["kept"]
        second = _second_pass_claims(block_sents, panels, kept, paths, config)
        if second:
            kept = filter_monotonic(raw + second, [p.id for p in panels])
            console.print(
                f"[dim]Match: block {block_idx} — second pass added "
                f"{len(second)} claim(s), {len(kept)} kept[/]"
            )
        claims_debug.append({
            "block": block_idx,
            "sentences": [no for no, _ in block_sents],
            "panels": [p.id for p in panels],
            "raw": [[no, pid] for no, pid in raw],
            "second": [[no, pid] for no, pid in second],
            "kept": [[no, pid] for no, pid in kept],
        })
        all_claims.extend(kept)

    # The raw claims are the only evidence of WHY a sentence went unmatched — whether the
    # model never claimed it or the monotonic filter destroyed the claim — and until this
    # file existed, answering that question meant re-paying every vision call.
    debug_dir = paths["debug"]
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / "match_claims.json").write_text(
        json.dumps({"blocks": claims_debug, "returns": moves}, indent=1), encoding="utf-8"
    )

    claims_by_number: dict[int, list[str]] = {}
    for number, pid in all_claims:
        claims_by_number.setdefault(number, []).append(pid)

    # The outro is the narrator talking to the VIEWER — deliberately not panel-grounded
    # (script/outro.py) — so its sentences are marked and excluded from the match-rate
    # denominator rather than counted as matcher misses. Same signature outro.py's own
    # idempotency guard uses.
    outro_beat = None
    if numbered:
        last_beat = numbered[-1][2]
        if any(
            "subscri" in text.lower()
            for (_no, text, beat_id) in numbered
            if beat_id == last_beat
        ):
            outro_beat = last_beat

    # Block identity crosses the STAGE boundary here. TTS/timeline is a separate process
    # invocation, so nothing in memory survives — the shotlist is the carrier, and the
    # planner and the reading-order gate both read it.
    #
    # Boundaries are persisted as panel IDS, never index ranges: align's `ordered_ids`,
    # engine's `fill_order` and the gate's panel list each apply DIFFERENT exclusions,
    # so an index-space block would silently mean three different things. Each consumer
    # resolves the ids against its own order.
    visits: list[int] = []
    for no, _t, _b in numbered:
        b = block_of_sentence[no - 1]
        if not visits or visits[-1] != b:
            visits.append(b)

    shotlist = {
        "sentences": [
            {
                "number": no,
                "beat_id": beat_id,
                "text": text,
                "panels": claims_by_number.get(no, []),
                "block": block_of_sentence[no - 1],
                **({"outro": True} if beat_id == outro_beat else {}),
            }
            for (no, text, beat_id) in numbered
        ],
        "time_blocks": {
            "boundaries": list(boundary_ids or []),
            "visits": visits,
            "returns": moves,
        },
    }
    # A sentence that recalls an earlier scene may put that earlier picture back on
    # screen (script/callbacks.py). Runs LAST, on sentences the matcher left unbound,
    # so it can never take a panel away from narration that describes what is actually
    # on the page. Every callback is recorded for review — a replayed shot is the one
    # edit that used to mean a bug.
    from manhwa2vid.script.callbacks import resolve_callbacks

    callbacks = resolve_callbacks(shotlist["sentences"])

    # ...and give the closing ask a picture of its own. Without this the outro rides
    # whatever the story ended on, which measured 19.1s and 18.3s of one frozen image
    # on the two titles that exceeded the hold limit.
    from manhwa2vid.script.callbacks import resolve_closing_coda

    last_block = max((int(s.get("block", 0)) for s in shotlist["sentences"]), default=0)
    coda = resolve_closing_coda(
        shotlist["sentences"],
        [p.id for p in (blocks_panels[last_block] if last_block < len(blocks_panels) else [])],
    )
    if coda:
        console.print(
            f"[cyan]Closing coda[/] — s{coda['number']} closes on {coda['panels'][0]} "
            f"instead of holding the final panel"
        )
    if callbacks:
        console.print(
            f"[cyan]Callbacks[/] — {len(callbacks)} sentence(s) replay an earlier shot: "
            + "; ".join(f"s{c['number']}->s{c['callback_of']}" for c in callbacks[:4])
        )

    save_json(paths["script_shotlist_json"], shotlist)
    if _MATCHER_PROVIDER is not None:
        console.print(f"[dim]{_MATCHER_PROVIDER.usage_line('Matcher')}[/]")
    matched = sum(1 for s in shotlist["sentences"] if s["panels"])
    console.print(
        f"[green]Shot list[/] — {matched}/{len(numbered)} sentence(s) matched, "
        f"{len({p for s in shotlist['sentences'] for p in s['panels']})} panel(s) claimed"
    )
    return shotlist


def _fill_run_panels(
    run_len: int,
    gap: list[str],
    seconds_per_sentence: list[float],
    floor: float,
) -> list[list[str]]:
    """Distribute the between-anchor panels across a run of unmatched sentences.

    Panels stay in reading order and split contiguously; a sentence is capped at the
    number of shots its airtime can carry at `floor` seconds each, and when the gap
    holds more panels than the run can carry, the gap is subsampled evenly so the walk
    still ARRIVES at the next anchor instead of stranding short of it.
    """
    out: list[list[str]] = []
    for i in range(run_len):
        lo = round(len(gap) * i / run_len)
        hi = round(len(gap) * (i + 1) / run_len)
        piece = gap[lo:hi]
        budget = max(1, int(seconds_per_sentence[i] // max(floor, 0.1)))
        if len(piece) > budget:
            step = len(piece) / budget
            piece = [piece[int(k * step)] for k in range(budget)]
        out.append(piece)
    return out


def plan_shots(
    shotlist: dict[str, Any],
    segments_by_beat: dict[int, list[dict[str, Any]]],
    *,
    floor: float = 1.0,
    panel_order: list[str] | None = None,
    accent_floor: float = 0.4,
    text_only: set[str] | None = None,
    max_shot: float = 0.0,
) -> dict[int, list[tuple[str, float]]] | None:
    """(panel, seconds) per beat. See `plan_shots_with_sentences` for the full result.

    Kept at two elements because ~25 assertions across tests/test_match.py pin exact
    tuples, and those assertions are the record of a dozen separately-earned invariants
    (A/V totals preserved, accent floors, burst caps). Widening the tuple would have meant
    rewriting all of them, which is how a suite quietly loses its teeth.
    """
    result = plan_shots_with_sentences(
        shotlist, segments_by_beat, floor=floor, panel_order=panel_order,
        accent_floor=accent_floor, text_only=text_only, max_shot=max_shot,
    )
    if result is None:
        return None
    return {beat: [(pid, sec) for pid, sec, _nums in shots] for beat, shots in result.items()}


def _bounds_for(block_bounds: dict[int, tuple[int, int]], block: int):
    """This block's panel range, or None when the shotlist carries no block metadata."""
    return block_bounds.get(block) if block_bounds else None


def _gap_spare(
    panel_order: list[str],
    order_pos: dict[str, int],
    prev_pid: str | None,
    next_pid: str | None,
    used: set[str],
    text_only: set[str] | None,
    bounds: tuple[int, int] | None = None,
) -> str | None:
    """The one panel a substitution may use: the first unused panel STRICTLY BETWEEN
    the panels shown before and after it in reading order. None if the gap is empty.

    This is the single ordering rule for every borrow, swap and substitution in this
    planner, and it exists because every one of them previously searched the WHOLE
    reading order for "the nearest unused panel", both directions. Measured on the
    2026-08-30 renders: 16 reading-order inversions on Frozen Player (jumps back by 7,
    8, 11, 26, 38 and 71 panels) and 11 on Solo Leveling — the viewer saw a frame from
    a different scene, then the timeline jumped back. Every large jump traced to a
    panel claimed by no sentence, i.e. inserted by one of these searches.

    The earlier "borrowing backwards is safe because the reader saw that art" comment
    was wrong in exactly the way a viewer notices: an earlier panel shown after a later
    one IS a rewind on screen, whatever the reader once saw on the page.

    An empty gap means KEEP WHAT YOU HAVE — hold the long shot, keep the text claim.
    A long dwell warns in QA; a wrong image is the defect the user reports.
    """
    lo = order_pos.get(prev_pid, -1) if prev_pid is not None else -1
    hi = order_pos.get(next_pid, len(panel_order)) if next_pid is not None else len(panel_order)
    # A substitution may never leave its TIME BLOCK. Without this the fill and every
    # borrow can walk across a printed skip and show the next era's art before its own
    # caption — the defect `clamp_to_time_blocks` exists to prevent, reachable here
    # because this function works in global reading-order positions.
    if bounds is not None:
        blo, bhi = bounds
        lo = max(lo, blo - 1)
        hi = min(hi, bhi)
    # Forward first — the natural continuation. Failing that, up to SCENE_RADIUS panels
    # behind the previous shown panel (2026-08-30, with the matcher and the gate):
    # unused same-scene art beats holding one image, and the radius keeps it a cut
    # within the scene rather than the cross-scene rewind the gate still fails.
    for pid in panel_order[lo + 1 : hi]:
        if pid not in used and pid not in (text_only or ()):
            return pid
    back_floor = max(0, lo - SCENE_RADIUS)
    if bounds is not None:
        back_floor = max(back_floor, bounds[0])
    for pid in reversed(panel_order[back_floor : lo + 1]):
        if pid not in used and pid not in (text_only or ()):
            return pid
    return None


def plan_shots_with_sentences(
    shotlist: dict[str, Any],
    segments_by_beat: dict[int, list[dict[str, Any]]],
    *,
    floor: float = 1.0,
    panel_order: list[str] | None = None,
    accent_floor: float = 0.4,
    text_only: set[str] | None = None,
    max_shot: float = 0.0,
) -> dict[int, list[tuple[str, float, list[int]]]] | None:
    """Join claims with measured sentence seconds into per-beat shots.

    Returns (panel, seconds, sentence numbers) per shot. The sentence numbers are what
    let the timeline record how much NARRATION a shot holds — counting entries instead
    understates a hold, because one entry can carry several sentences.

    Pure code, runs at timeline time when sidecars exist. Rules (user decisions,
    2026-08-26 revision):
    - a sentence's seconds split evenly across its claimed panels; an intra-sentence
      multi-panel split is an ACCENT — it survives below `floor` (down to
      `accent_floor`), restoring the short-shot class the reference channel uses for
      22% of its cuts and this pipeline produced 0-6% of;
    - an unclaimed sentence **walks the unclaimed panels between its surrounding
      matched anchors** (bounded fill — reading order, so it can never jump to an
      unrelated image). SL matched only 49% of sentences, so pure holding made half
      the picture stand still and played a 6-sentence action climax over two stills;
    - with no panels between anchors — or no anchor on one side — it HOLDS the current
      shot as before; leading unclaimed sentences attach to the first claimed shot;
    - non-accent shots under `floor` merge into the previous shot;
    - a hold crossing a beat boundary re-opens the same panel in the next beat
      (cross-beat panel reuse is render-safe by construction).

    Returns None when the sidecar sentences do not line up with the shotlist — the
    caller then falls back to the weight path rather than guessing.
    """
    sentences = shotlist.get("sentences") or []
    # Block ranges in THIS caller's panel_order coordinates. Resolved from panel IDS,
    # never persisted indices: align's ordered_ids, the engine's fill_order and the
    # gate's panel list apply different exclusions, so an index would mean three
    # different things. A boundary panel missing from this order (it may have been
    # filtered as text-dominant) falls to the next id that IS present.
    block_bounds: dict[int, tuple[int, int]] = {}
    if panel_order:
        meta = (shotlist.get("time_blocks") or {}) if isinstance(shotlist, dict) else {}
        pos_all = {pid: i for i, pid in enumerate(panel_order)}
        cuts = sorted({pos_all[b] for b in (meta.get("boundaries") or []) if b in pos_all})
        edges = [0, *cuts, len(panel_order)]
        for i in range(len(edges) - 1):
            block_bounds[i] = (edges[i], edges[i + 1])
    block_of_number: dict[int, int] = {
        int(sent.get("number", 0)): int(sent.get("block", 0)) for sent in sentences
    }
    by_beat: dict[int, list[dict[str, Any]]] = {}
    for sent in sentences:
        by_beat.setdefault(int(sent["beat_id"]), []).append(sent)

    # Identity check + global (sentence, beat, seconds, claimed panels) sequence.
    flat: list[dict[str, Any]] = []
    for beat_id, beat_sents in by_beat.items():
        segs = segments_by_beat.get(beat_id)
        if not segs or len(segs) != len(beat_sents):
            return None  # identity broken — do not guess
        for sent, seg in zip(beat_sents, segs):
            flat.append(
                {
                    "beat_id": beat_id,
                    # Carried so the timeline can record WHICH sentences a shot holds.
                    # Without it a hold's length can only be counted in entries, which
                    # understates it: one entry can carry several sentences.
                    "number": int(sent.get("number", 0)),
                    "seconds": max(float(seg.get("seconds", 0.0)), 0.0),
                    "panels": list(sent.get("panels") or []),
                    # The sentence's TIME BLOCK, so every substitution below can stay
                    # inside it. Absent (older shotlists) -> 0 -> one implicit block
                    # spanning everything -> today's behaviour exactly.
                    "block": int(sent.get("block", 0)),
                }
            )

    # A claimed panel that is nothing but a speech bubble becomes a wall of text on the
    # page background — the reference channel never shows one, and every bubble in its
    # frames sits WITH the art it belongs to. The matcher is right that the line lives
    # there, but our narrator is already speaking that line, so the screen should carry
    # the moment instead: swap in the nearest art panel in reading order.
    if text_only and panel_order:
        art_at = {pid: i for i, pid in enumerate(panel_order)}
        # Panels already on screen somewhere. A swap that lands on one of them does not
        # replace a shot, it DELETES one: the two entries fold into a single hold. That
        # is how removing FP's closing "WHAT?!" first made things worse rather than
        # better — both it and the shot before it swapped onto the same neighbour and
        # became one 30.6s hold, up from 18.6s.
        #
        # The replacement must come from the reading-order GAP around the claim —
        # see _gap_spare. The old "nearest unused art panel, searched both ways" was
        # one of the four unconstrained searches behind the 2026-08-30 inversions.
        # With an empty gap the text claim is KEPT: a wall of lettering for one shot
        # beats a frame from another scene, and the bare-bubble render gate reports it.
        taken = {pid for item in flat for pid in item["panels"] if pid not in text_only}
        # Reading-order neighbours: for each flat position, the panel shown before and
        # after it, taken from the ORIGINAL claims. Swaps stay inside their own gaps,
        # so using pre-swap neighbours cannot introduce an inversion.
        for idx, item in enumerate(flat):
            swapped: list[str] = []
            for k, pid in enumerate(item["panels"]):
                if pid not in text_only or pid not in art_at:
                    swapped.append(pid)
                    continue
                prev_pid = next(
                    (q for q in reversed(swapped) if q in art_at),
                    next((q for j in range(idx - 1, -1, -1)
                          for q in reversed(flat[j]["panels"]) if q in art_at), None),
                )
                next_pid = next(
                    (q for q in item["panels"][k + 1:] if q in art_at),
                    next((q for j in range(idx + 1, len(flat))
                          for q in flat[j]["panels"] if q in art_at), None),
                )
                pick = _gap_spare(
                    panel_order, art_at, prev_pid, next_pid, taken, text_only,
                    _bounds_for(block_bounds, item.get("block", 0)),
                )
                if pick is None:
                    swapped.append(pid)      # empty gap — keep the text claim
                else:
                    swapped.append(pick)
                    taken.add(pick)
            item["panels"] = swapped

    # Bounded fill: rewrite each unclaimed RUN's panels from the reading-order gap
    # between its surrounding anchors.
    if panel_order:
        pos = {pid: i for i, pid in enumerate(panel_order)}
        claimed = {pid for item in flat for pid in item["panels"]}
        i = 0
        while i < len(flat):
            if flat[i]["panels"]:
                i += 1
                continue
            j = i
            while j < len(flat) and not flat[j]["panels"]:
                j += 1
            prev_anchor = next(
                (p for k in range(i - 1, -1, -1) for p in reversed(flat[k]["panels"]) if p in pos),
                None,
            )
            next_anchor = next(
                (p for k in range(j, len(flat)) for p in flat[k]["panels"] if p in pos),
                None,
            )
            if prev_anchor is not None and next_anchor is not None:
                lo, hi = pos[prev_anchor], pos[next_anchor]
                # The gap intersects the RUN'S OWN BLOCK. Without this the fill can
                # reach across a printed time skip: Frozen Player's returning fight
                # narration sat beside the "25 YEARS LATER" seam and would be handed
                # sky panels from the next era.
                run_block = flat[i].get("block", 0)
                rb = _bounds_for(block_bounds, run_block)
                g_lo, g_hi = (lo + 1, hi)
                if rb is not None:
                    g_lo, g_hi = max(g_lo, rb[0]), min(g_hi, rb[1])
                gap = [
                    pid
                    for pid in panel_order[g_lo:g_hi]
                    if pid not in claimed and pid not in (text_only or ())
                ]
                # When the forward gap cannot cover the run, reach BACK up to
                # SCENE_RADIUS for unused art — the same tolerance every substitution
                # and the reading-order gate already use. Measured need: Solo Leveling
                # held p0100_02 for 25.1s across four sentences of narrator
                # introspection because the only panel between its anchors was a
                # lettering card ("THAT I KNEW VERY WELL."), while p0099_02 and
                # p0100_01 sat unused one and two panels behind it.
                #
                # Kept in reading order so the run plays forward within itself; the
                # step back happens once, at its head, inside the radius.
                need = j - i
                if len(gap) < need:
                    b_lo = max(0, lo - SCENE_RADIUS)
                    if rb is not None:
                        b_lo = max(b_lo, rb[0])
                    back = [
                        pid
                        for pid in panel_order[b_lo : lo + 1]
                        if pid not in claimed and pid not in (text_only or ())
                    ]
                    gap = back[-(need - len(gap)):] + gap if back else gap
                if gap:
                    assigned = _fill_run_panels(
                        j - i, gap, [flat[k]["seconds"] for k in range(i, j)], floor
                    )
                    for offset, panels in enumerate(assigned):
                        flat[i + offset]["panels"] = panels
                        # Fill assignments join `claimed` immediately. It was computed
                        # once before this loop and never updated, so two runs whose
                        # anchor gaps overlapped could receive the SAME panel — one of
                        # the sources of the non-adjacent repeats the 2026-08-30 gate
                        # caught (p0015_02 twice, 14.4s apart, claimed by no sentence).
                        claimed.update(panels)
            i = j

    # A beat that OPENS on the panel the previous beat CLOSED on schedules a cut the
    # viewer cannot see. Holding across a beat boundary is the deliberate safe fallback
    # for an unclaimed opening sentence — it beats cutting to something unrelated — but
    # the two entries then read as one long hold, and nothing downstream can tell:
    # the dwell limit and the burst guard both count PLANNED entries. Measured on FP
    # ch1-2: 6 such runs, turning 106 planned shots into 100 seen ones and a 16.7s
    # longest shot into 18.6s.
    #
    # Prefer the next unclaimed ART panel in reading order; keep the hold when there is
    # none, because an unrelated image is still worse than a long one.
    #
    # Reaching BACK for a callback when nothing unclaimed remains was tried and dropped
    # (2026-08-27). Panel reuse is render-safe and the reference channel does close on a
    # replayed image, but it contradicts the rule above, and the residual runs are the
    # ones where a beat simply has more narration than panels — a content shortage that
    # a camera trick hides rather than fixes. The `no-invisible-cuts` timeline gate
    # reports what is left instead.
    if panel_order:
        pos = {pid: i for i, pid in enumerate(panel_order)}
        claimed = {pid for item in flat for pid in item["panels"]}
        for item_idx, (prev_item, item) in enumerate(zip(flat, flat[1:]), start=1):
            if prev_item["beat_id"] == item["beat_id"]:
                continue
            if not prev_item["panels"] or not item["panels"]:
                continue
            last, first = prev_item["panels"][-1], item["panels"][0]
            if last != first or last not in pos:
                continue
            # Replacement from the reading-order gap only (_gap_spare): after `last`,
            # before whatever this item shows next (or the next item's first panel).
            # The old "nearest unused, searched both ways" was one of the four
            # unconstrained searches behind the 2026-08-30 inversions. An empty gap
            # keeps the hold — `no-invisible-cuts` reports it, and a long hold beats
            # a frame from another scene.
            after = next(
                (q for q in item["panels"][1:] if q in pos),
                next((q for later in flat[item_idx + 1:]
                      for q in later["panels"] if q in pos), None),
            )
            nxt = _gap_spare(
                panel_order, pos, last, after, claimed, text_only,
                _bounds_for(block_bounds, item.get("block", 0)),
            )
            if nxt is not None:
                item["panels"][0] = nxt
                claimed.add(nxt)

    # Sentences -> raw shots: (panel, seconds, accent, sentence numbers).
    # For the split pass: the first panel shown by each LATER beat, so a split at the
    # end of a beat can bound its gap by what the viewer sees next. Built from `flat`
    # after every substitution above, so it reflects the real sequence.
    next_first_by_beat: dict[int, str | None] = {}
    if panel_order:
        beat_seq: list[int] = []
        for item in flat:
            if not beat_seq or beat_seq[-1] != item["beat_id"]:
                beat_seq.append(item["beat_id"])
        first_panel_of_beat: dict[int, str] = {}
        for item in flat:
            if item["beat_id"] not in first_panel_of_beat and item["panels"]:
                first_panel_of_beat[item["beat_id"]] = item["panels"][0]
        for bi, b in enumerate(beat_seq):
            next_first_by_beat[b] = next(
                (first_panel_of_beat[lb] for lb in beat_seq[bi + 1:]
                 if lb in first_panel_of_beat), None,
            )

    plan: dict[int, list[tuple[str, float, list[int]]]] = {}
    current_panel: str | None = None
    pending_lead = 0.0
    shots_by_beat: dict[int, list[list[Any]]] = {}
    for item in flat:
        beat_id = item["beat_id"]
        shots = shots_by_beat.setdefault(beat_id, [])
        seconds = item["seconds"]
        panels = item["panels"]
        number = item["number"]
        if not panels:
            if shots:
                shots[-1][1] += seconds
                shots[-1][3].append(number)
            elif current_panel is not None:
                shots.append([current_panel, seconds, False, [number]])
            else:
                pending_lead += seconds
            continue
        share = seconds / len(panels)
        accent = len(panels) > 1
        for pid in panels:
            if pending_lead:
                shots.append([pid, share + pending_lead, accent, [number]])
                pending_lead = 0.0
            else:
                shots.append([pid, share, accent, [number]])
            current_panel = pid

    for beat_id, shots in shots_by_beat.items():
        # Coalesce, preserving total seconds exactly. Two passes, each trivially
        # checkable: fold consecutive runs of the same panel, then absorb any
        # non-accent shot still under the floor into its neighbour. Accent shots keep
        # their cut down to `accent_floor` — deleting them is how the pipeline ended
        # up with zero shots under 1.5s against the reference's 22%.
        folded: list[list[Any]] = []
        for pid, sec, accent, nums in shots:
            if folded and folded[-1][0] == pid:
                folded[-1][1] += sec
                folded[-1][2] = folded[-1][2] or accent
                folded[-1][3].extend(nums)
            else:
                folded.append([pid, sec, accent, list(nums)])

        merged: list[list[Any]] = []
        for pid, sec, accent, nums in folded:
            limit = accent_floor if accent else floor
            if sec < limit and merged:
                merged[-1][1] += sec          # too short: extend the previous shot
                merged[-1][3].extend(nums)
            else:
                merged.append([pid, sec, accent, list(nums)])
        if len(merged) > 1 and merged[0][1] < (accent_floor if merged[0][2] else floor):
            merged[1][1] += merged[0][1]      # a short FIRST shot has no previous
            merged[1][3] = merged[0][3] + merged[1][3]
            merged = merged[1:]

        # Burst guard: accent cuts are punctuation, not a texture. The reference channel
        # runs at most 3 consecutive sub-1.2s shots (one such run in 10 minutes); our
        # first cut of this ran bursts of 6, five times over, which reads as strobing
        # rather than emphasis. Past `max_burst` in a row, fold pairs together until the
        # run is legal — seconds are preserved, so A/V lock is untouched.
        burst_limit = 1.2
        max_burst = 3
        i = 0
        while i < len(merged):
            j = i
            while j < len(merged) and merged[j][1] < burst_limit:
                j += 1
            run = j - i
            while run > max_burst:
                # merge the two shortest adjacent shots inside the run
                k = min(range(i, i + run - 1), key=lambda x: merged[x][1] + merged[x + 1][1])
                merged[k][1] += merged[k + 1][1]
                merged[k][3].extend(merged[k + 1][3])
                merged.pop(k + 1)
                run -= 1
            i = max(j, i + 1)

        # Split a shot that holds one image too long. The reference channel's own longest
        # is 16.37s; Solo Leveling shipped 27.8s and Frozen Player 18.6s, both from a
        # beat carrying more narration than it has panels.
        #
        # The borrowed panel comes from the reading-order GAP between this shot and the
        # next one shown (_gap_spare) — never from a global nearest-unused search. Two
        # revisions of this pass are worth recording: the original stole panels LATER
        # sentences had claimed (premature reuse, fixed bb78858); the fix then excluded
        # every claimed panel, which shrank the pool so "nearest unused, both ways"
        # landed 26-100 panels away — the 2026-08-30 inversions, up to a 71-panel jump
        # back on Frozen Player. "Borrowing backwards is safe because the reader saw
        # that art" was wrong: an earlier panel after a later one is a rewind on
        # screen. An empty gap keeps the long dwell, which QA already reports.
        if panel_order and max_shot > 0:
            order_pos = {pid: idx for idx, pid in enumerate(panel_order)}
            # Every panel any sentence resolved to, in EVERY beat — not just the beats
            # already emitted into `plan` plus this one.
            #
            # `plan[beat_id]` is written at the end of each iteration, so a `used` built
            # from `plan` + `merged` is blind to every LATER beat, even though `flat`
            # resolved them before this loop began. The split then borrowed a panel a
            # later sentence claims, showed it early, and that sentence showed it again
            # when the narration actually arrived. Measured on Solo Leveling: p0134_02
            # (the hunter's leg) appeared at 605.2 s while its sentence speaks at
            # 627.3 s — 22.1 s early — and p0136_01 16.4 s early. Frozen Player had two
            # more. Toggling max_shot on/off isolated this pass as the sole cause.
            #
            # Worse than a duplicate: when the borrow lands adjacent to the real shot,
            # the final assembled pass rewrites the CLAIMING shot rather than the
            # borrow, so the sentence that earned the panel loses it.
            used = {pid for item in flat for pid in item["panels"]}
            used.update(row[0] for rows in plan.values() for row in rows)
            used.update(row[0] for row in merged)
            i = 0
            while i < len(merged):
                pid, sec, accent, nums = merged[i]
                if sec <= max_shot or pid not in order_pos or len(nums) < 2:
                    i += 1
                    continue
                shown_next = (
                    merged[i + 1][0] if i + 1 < len(merged)
                    else next_first_by_beat.get(beat_id)
                )
                lo = order_pos[pid]
                hi = (
                    order_pos.get(shown_next, len(panel_order))
                    if shown_next is not None else len(panel_order)
                )
                # The split's spares are the LAST substitution path that was still
                # unbounded: with the shot cap active it reached across a printed skip
                # and inserted p0013_09 — claimed by nobody, 8 panels behind — into
                # Frozen Player's aftermath, failing reading-order on the very run that
                # proved the return works. Same rule as every other substitution now.
                sb = _bounds_for(block_bounds, block_of_number.get(nums[0], 0))
                g_lo, g_hi = lo + 1, hi
                if sb is not None:
                    g_lo, g_hi = max(g_lo, sb[0]), min(g_hi, sb[1])
                gap = [
                    c for c in panel_order[g_lo:g_hi]
                    if c not in used and c not in (text_only or ())
                ]
                # One multi-way split, spares taken from the gap IN READING ORDER —
                # not the old recursive halving. Halving deadlocks under the gap rule:
                # its first spare lands adjacent to the shot, the re-examined first
                # half then has an empty gap, and a 12s hold survives a 10s cap.
                # Sizing: per-sentence seconds are ~sec/len(nums) here (sentence splits
                # were even upstream), so group size is what fits under the cap.
                per_sentence = sec / len(nums)
                fit = max(1, int(max_shot // per_sentence)) if per_sentence > 0 else len(nums)
                parts = -(-len(nums) // fit)                      # ceil
                parts = min(parts, len(nums), 1 + len(gap))
                if parts < 2:
                    i += 1                                        # empty gap: keep the dwell
                    continue
                base, extra = divmod(len(nums), parts)
                sizes = [base + (1 if k < extra else 0) for k in range(parts)]
                panels = [pid] + gap[: parts - 1]
                rows, start = [], 0
                for k in range(parts):
                    grp = nums[start : start + sizes[k]]
                    start += sizes[k]
                    rows.append([panels[k], sec * len(grp) / len(nums), accent, grp])
                merged[i : i + 1] = rows
                used.update(panels[1:])
                i += parts


        if merged:
            plan[beat_id] = [
                (pid, sec, sorted(set(nums))) for pid, sec, _accent, nums in merged
            ]
    # Final pass over the ASSEMBLED sequence. Everything above works inside one beat, so
    # a shot that is legal in beat N and legal in beat N+1 can still be one long hold on
    # screen: 7.2s + 7.2s on the same panel is 14.4s to a viewer. This is the only place
    # that sees the whole timeline, so it is the only place that can catch it.
    if plan and panel_order and max_shot > 0:
        order_pos = {pid: i for i, pid in enumerate(panel_order)}
        flat_shots = [(beat, idx) for beat in sorted(plan) for idx in range(len(plan[beat]))]
        used = {plan[b][i][0] for b, i in flat_shots}
        for k, ((pb, pi), (cb, ci)) in enumerate(zip(flat_shots, flat_shots[1:]), start=1):
            prev, cur = plan[pb][pi], plan[cb][ci]
            if prev[0] != cur[0] or prev[1] + cur[1] <= max_shot:
                continue
            # Substitute from the reading-order gap only: after the held panel, before
            # whatever the assembled sequence shows next. The global nearest-unused
            # search this replaces was one of the four behind the 2026-08-30
            # inversions. Empty gap -> keep the hold; a long shot beats a rewind.
            shown_next = (
                plan[flat_shots[k + 1][0]][flat_shots[k + 1][1]][0]
                if k + 1 < len(flat_shots) else None
            )
            cur_block = next(
                (block_of_number.get(n, 0) for n in cur[2]), 0
            )
            spare = _gap_spare(
                panel_order, order_pos, cur[0], shown_next, used, text_only,
                _bounds_for(block_bounds, cur_block),
            )
            if spare is None:
                continue  # an unrelated image is still worse than a long one
            plan[cb][ci] = (spare, cur[1], cur[2])
            used.add(spare)

    # J-cut: a row over the cap DONATES its trailing sentences forward to the next
    # row, so the following panel arrives while the previous thought is still being
    # spoken — which is what a human editor does with a long transition. Measured need:
    # Frozen Player's time-skip parked 38 seconds of narration on three panels of open
    # sky ("YOU GUYS...", "25 YEARS LATER", empty blue). They are DIFFERENT panels that
    # look identical on screen, so no camera treatment produces a visible cut, and the
    # scene detector read one 38.23s shot — a shot-max-duration FAIL. The museum the
    # narration was already describing sat one panel ahead.
    #
    # Sentence-aligned (never splits mid-sentence; a single over-long sentence stays),
    # forward-only (order untouched), and between EXISTING adjacent rows (no repeats,
    # no new panels). Seconds move with their sentences, proportionally. Runs after the
    # cross-beat pass so it sees the assembled sequence; before the stale-hold
    # normalization, which must see the final durations.
    if plan and panel_order and max_shot > 0:
        rows_seq = [(b, i) for b in sorted(plan) for i in range(len(plan[b]))]
        for k, (b, i) in enumerate(rows_seq[:-1]):
            pid_, sec_, nums_ = plan[b][i]
            nb, ni = rows_seq[k + 1]
            npid, nsec, nnums = plan[nb][ni]
            if npid == pid_:
                continue  # same-panel holds are the renderer's segmentation problem
            # Never donate across a time skip: that plays one era's narration over the
            # next era's art, which is the whole reason time blocks exist. Leave the
            # long row; `shot-max-duration` reports it honestly.
            if block_of_number.get(nums_[-1] if nums_ else 0, 0) != block_of_number.get(
                nnums[0] if nnums else 0, 0
            ):
                continue
            while sec_ > max_shot and len(nums_) > 1:
                share = sec_ / len(nums_)
                moved = nums_[-1]
                nums_ = nums_[:-1]
                sec_ -= share
                nnums = [moved] + nnums
                nsec += share
            plan[b][i] = (pid_, sec_, nums_)
            plan[nb][ni] = (npid, nsec, nnums)

    # Re-point stale HOLDS at the true last-shown panel. A hold is resolved early, in
    # the flat->shots build, by remembering `current_panel` — but the split pass runs
    # later and can insert rows after the hold's origin. Beat 18 then re-opens beat
    # 17's p0023_11 although p0024_01 (a split spare) now sits between them: a
    # non-adjacent repeat AND an inversion in one move, and the last one standing after
    # the gap rule (1 of FP's original 16). Re-pointing the hold at the actual
    # previous panel turns it back into the adjacent hold it was meant to be.
    #
    # Only UNCLAIMED rows are rewritten. A claimed row re-appearing would be a planner
    # bug, and hiding it here would blind the `no-repeated-panels` gate that exists to
    # catch exactly that — let it fail loudly instead.
    if plan and panel_order:
        sent_panels: dict[int, set[str]] = {}
        for item in flat:
            sent_panels[item["number"]] = set(item["panels"])
        seen: set[str] = set()
        prev_pid: str | None = None
        for b in sorted(plan):
            rows_out: list[tuple[str, float, list[int]]] = []
            for pid_, sec_, nums_ in plan[b]:
                is_hold = not any(pid_ in sent_panels.get(n, ()) for n in nums_)
                if pid_ in seen and pid_ != prev_pid and is_hold and prev_pid is not None:
                    pid_ = prev_pid
                rows_out.append((pid_, sec_, nums_))
                seen.add(pid_)
                prev_pid = pid_
            plan[b] = rows_out

    # Final invariant sweep: no UNCLAIMED row may rewind past the visit's high-water by
    # more than SCENE_RADIUS. Every substitution path is individually bounded now, but
    # they compose — a beat's fill can open behind where the previous beat's claims
    # ended (measured on Frozen Player: beat 9 closed on #102, beat 10's fill opened on
    # #94). Rather than chase each composition, enforce the property the gate checks.
    #
    # Only unclaimed rows are re-pointed, and only onto the previous panel — a hold,
    # which is always legal and always in-block. A CLAIMED row that rewinds is a real
    # binding problem and must reach the gate, not be hidden here.
    if plan and panel_order:
        order_pos_f = {pid: i for i, pid in enumerate(panel_order)}
        # From the SHOTLIST, not from `flat`. `flat` items have had fill assignments
        # written into their "panels" by this point, so reading it here made every
        # filled panel look claimed and exempt from the sweep — which is how an
        # unclaimed backward fill survived to the gate.
        claimed_pids = {
            pid for sent in sentences for pid in (sent.get("panels") or [])
        }
        cuts_f = sorted(
            {order_pos_f[b] for b in (
                ((shotlist.get("time_blocks") or {}).get("boundaries") or [])
                if isinstance(shotlist, dict) else []
            ) if b in order_pos_f}
        )
        block_at = lambda q: sum(1 for c in cuts_f if c <= q)
        high_f, prev_blk, prev_p = -1, None, None
        for b in sorted(plan):
            out_rows: list[tuple[str, float, list[int]]] = []
            for pid_, sec_, nums_ in plan[b]:
                q = order_pos_f.get(pid_)
                blk = block_at(q) if q is not None else 0
                if blk != prev_blk:
                    high_f = -1
                # Re-pointable: an unclaimed fill panel, or a LETTERING panel the
                # bare-bubble swap could not replace. A text-only panel is one the
                # planner would rather not show at all; if showing it also rewinds the
                # timeline, a hold is strictly better. A claimed ART panel that
                # rewinds is a genuine binding defect and still reaches the gate.
                movable = pid_ not in claimed_pids or pid_ in (text_only or ())
                if (
                    q is not None and blk == prev_blk and q < high_f - SCENE_RADIUS
                    and movable and prev_p is not None
                ):
                    pid_, q = prev_p, order_pos_f.get(prev_p)
                out_rows.append((pid_, sec_, nums_))
                if q is not None:
                    high_f = max(high_f, q)
                prev_blk, prev_p = blk, pid_
            plan[b] = out_rows

    return plan or None
