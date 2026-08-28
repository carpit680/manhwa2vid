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


def collect_claims(
    sentences: list[tuple[int, str]],
    panels: list[Panel],
    paths: dict[str, Path],
    config: dict[str, Any],
) -> list[tuple[int, str]]:
    """(sentence_number, panel_id) claims from windowed vision calls. Raw, unfiltered."""
    from manhwa2vid.llm.provider import get_llm_provider

    provider = get_llm_provider(get_nested(config, "align", "provider", default=None), config)
    model = get_nested(config, "align", "match_model", default=None)
    if model:
        provider.vision_model = model
    provider.temperature = 0.0

    window_size = int(get_nested(config, "align", "match_window_panels", default=16))
    numbered = "\n".join(f"[{n}] {t}" for n, t in sentences)
    valid_ids = {p.id for p in panels}
    valid_numbers = {n for n, _ in sentences}

    claims: list[tuple[int, str]] = []
    for batch in _window(panels, window_size):
        raw = provider.describe_labeled_panels(
            [(f"[{p.id}]", paths["root"] / p.image_path) for p in batch],
            f"{_SYSTEM}\n\nSENTENCES:\n{numbered}",
        )
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            continue
        batch_ids = {p.id for p in batch}
        for claim in data.get("claims") or []:
            try:
                number = int(claim.get("sentence"))
            except (TypeError, ValueError):
                continue
            for pid in (claim.get("panels") or [])[:3]:
                if number in valid_numbers and pid in batch_ids and pid in valid_ids:
                    claims.append((number, str(pid)))
    return claims


def filter_monotonic(
    claims: list[tuple[int, str]], panel_order: list[str]
) -> list[tuple[int, str]]:
    """Largest consistent claim set: sentence order and panel order must agree.

    Longest-increasing-subsequence over (sentence, panel_position): panel positions
    strictly increase (each panel shown once), sentence numbers never decrease. A claim
    that contradicts the story's forward motion — the model matching a late panel to an
    early sentence — is dropped rather than negotiated with. O(n^2), n is a block's
    claims (tens), chosen over the O(n log n) version because it is obviously correct.
    """
    pos = {pid: i for i, pid in enumerate(panel_order)}
    items = sorted(
        {(number, pid) for number, pid in claims if pid in pos},
        key=lambda c: (c[0], pos[c[1]]),
    )
    if not items:
        return []
    best_len = [1] * len(items)
    parent = [-1] * len(items)
    for i, (sent_i, pid_i) in enumerate(items):
        for j in range(i):
            sent_j, pid_j = items[j]
            if sent_j <= sent_i and pos[pid_j] < pos[pid_i] and best_len[j] + 1 > best_len[i]:
                best_len[i] = best_len[j] + 1
                parent[i] = j
    end = max(range(len(items)), key=lambda i: best_len[i])
    chain: list[tuple[int, str]] = []
    while end != -1:
        chain.append(items[end])
        end = parent[end]
    return list(reversed(chain))


def build_shotlist(
    beats_sentences: list[tuple[int, list[str]]],
    blocks_panels: list[list[Panel]],
    block_of_sentence: list[int],
    paths: dict[str, Path],
    config: dict[str, Any],
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

    all_claims: list[tuple[int, str]] = []
    for block_idx, panels in enumerate(blocks_panels):
        block_sents = [
            (no, text) for (no, text, _b) in numbered
            if block_of_sentence[no - 1] == block_idx
        ]
        if not block_sents or not panels:
            continue
        raw = collect_claims(block_sents, panels, paths, config)
        kept = filter_monotonic(raw, [p.id for p in panels])
        console.print(
            f"[dim]Match: block {block_idx} — {len(raw)} claim(s), "
            f"{len(kept)} after monotonic filter[/]"
        )
        all_claims.extend(kept)

    claims_by_number: dict[int, list[str]] = {}
    for number, pid in all_claims:
        claims_by_number.setdefault(number, []).append(pid)

    shotlist = {
        "sentences": [
            {
                "number": no,
                "beat_id": beat_id,
                "text": text,
                "panels": claims_by_number.get(no, []),
            }
            for (no, text, beat_id) in numbered
        ]
    }
    save_json(paths["script_shotlist_json"], shotlist)
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
                }
            )

    # A claimed panel that is nothing but a speech bubble becomes a wall of text on the
    # page background — the reference channel never shows one, and every bubble in its
    # frames sits WITH the art it belongs to. The matcher is right that the line lives
    # there, but our narrator is already speaking that line, so the screen should carry
    # the moment instead: swap in the nearest art panel in reading order.
    if text_only and panel_order:
        art_at = {pid: i for i, pid in enumerate(panel_order)}
        art_seq = [pid for pid in panel_order if pid not in text_only]
        # Panels already on screen somewhere. A swap that lands on one of them does not
        # replace a shot, it DELETES one: the two entries fold into a single hold. That
        # is how removing FP's closing "WHAT?!" first made things worse rather than
        # better — both it and the shot before it swapped onto the same neighbour and
        # became one 30.6s hold, up from 18.6s. Take the nearest UNUSED art panel.
        taken = {pid for item in flat for pid in item["panels"] if pid not in text_only}
        for item in flat:
            swapped: list[str] = []
            for pid in item["panels"]:
                if pid not in text_only or pid not in art_at:
                    swapped.append(pid)
                    continue
                here = art_at[pid]
                nearby = sorted(art_seq, key=lambda a: abs(art_at[a] - here))
                pick = next((a for a in nearby if a not in taken and a not in swapped), None)
                if pick is None:
                    # every art panel is already showing: fall back to the nearest one
                    # not in THIS sentence, and only then keep the text claim.
                    pick = next((a for a in nearby if a not in swapped), None)
                if pick is None:
                    swapped.append(pid)      # nothing but text anywhere — keep the claim
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
                gap = [
                    pid
                    for pid in panel_order[lo + 1 : hi]
                    if pid not in claimed and pid not in (text_only or ())
                ]
                if gap:
                    assigned = _fill_run_panels(
                        j - i, gap, [flat[k]["seconds"] for k in range(i, j)], floor
                    )
                    for offset, panels in enumerate(assigned):
                        flat[i + offset]["panels"] = panels
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
        for prev_item, item in zip(flat, flat[1:]):
            if prev_item["beat_id"] == item["beat_id"]:
                continue
            if not prev_item["panels"] or not item["panels"]:
                continue
            last, first = prev_item["panels"][-1], item["panels"][0]
            if last != first or last not in pos:
                continue
            nxt = next(
                (
                    pid
                    for pid in panel_order[pos[last] + 1 :]
                    if pid not in claimed and pid not in (text_only or ())
                ),
                None,
            )
            if nxt is not None:
                item["panels"][0] = nxt
                claimed.add(nxt)

    # Sentences -> raw shots: (panel, seconds, accent, sentence numbers).
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
        # The panel it borrows is the nearest UNUSED one in reading order, searched both
        # ways. Searching only forward is why the earlier cross-beat fix could not help
        # these: they sit at the end of their chapter with nothing after them. Borrowing
        # backwards is safe because an unused panel is art the reader saw on the same
        # pages — and 41% (FP) / 28% (SL) of story panels never reach the screen at all,
        # so this pays the same debt twice.
        if panel_order and max_shot > 0:
            order_pos = {pid: idx for idx, pid in enumerate(panel_order)}
            used = {row[0] for rows in plan.values() for row in rows}
            used.update(row[0] for row in merged)
            i = 0
            while i < len(merged):
                pid, sec, accent, nums = merged[i]
                if sec <= max_shot or pid not in order_pos or len(nums) < 2:
                    i += 1
                    continue
                here = order_pos[pid]
                spare = min(
                    (
                        cand for cand in panel_order
                        if cand not in used and cand not in (text_only or ())
                    ),
                    key=lambda cand: abs(order_pos[cand] - here),
                    default=None,
                )
                if spare is None:
                    i += 1
                    continue
                # Split the narration, not just the clock: the second half of the
                # sentences moves to the borrowed panel, so the cut lands on a sentence
                # boundary rather than mid-thought.
                half = len(nums) // 2
                share = sec * (len(nums) - half) / len(nums)
                merged[i] = [pid, sec - share, accent, nums[:half]]
                merged.insert(i + 1, [spare, share, accent, nums[half:]])
                used.add(spare)
                # Do NOT advance: the first half may still be over the cap. Termination is
                # guaranteed because a split halves the sentence count and the `< 2` guard
                # stops at one sentence.

        if merged:
            plan[beat_id] = [
                (pid, sec, sorted(set(nums))) for pid, sec, _accent, nums in merged
            ]
    return plan or None
