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


def plan_shots(
    shotlist: dict[str, Any],
    segments_by_beat: dict[int, list[dict[str, Any]]],
    *,
    floor: float = 1.0,
) -> dict[int, list[tuple[str, float]]] | None:
    """Join claims with measured sentence seconds into per-beat (panel, seconds) shots.

    Pure code, runs at timeline time when sidecars exist. Rules (user decisions):
    - a sentence's seconds split evenly across its claimed panels;
    - an unclaimed sentence HOLDS the current shot (its seconds extend it);
    - leading unclaimed sentences attach to the first claimed shot;
    - shots under `floor` merge into the previous shot;
    - a hold crossing a beat boundary re-opens the same panel in the next beat
      (cross-beat panel reuse is render-safe by construction).

    Returns None when the sidecar sentences do not line up with the shotlist — the
    caller then falls back to the weight path rather than guessing.
    """
    sentences = shotlist.get("sentences") or []
    plan: dict[int, list[tuple[str, float]]] = {}
    current_panel: str | None = None
    pending_lead = 0.0

    by_beat: dict[int, list[dict[str, Any]]] = {}
    for sent in sentences:
        by_beat.setdefault(int(sent["beat_id"]), []).append(sent)

    for beat_id, beat_sents in by_beat.items():
        segs = segments_by_beat.get(beat_id)
        if not segs or len(segs) != len(beat_sents):
            return None  # identity broken — do not guess
        shots: list[tuple[str, float]] = []
        for sent, seg in zip(beat_sents, segs):
            seconds = max(float(seg.get("seconds", 0.0)), 0.0)
            panels = [p for p in sent.get("panels") or []]
            if not panels:
                if shots:
                    pid, acc = shots[-1]
                    shots[-1] = (pid, acc + seconds)
                elif current_panel is not None:
                    shots.append((current_panel, seconds))
                else:
                    pending_lead += seconds
                continue
            share = seconds / len(panels)
            for pid in panels:
                if pending_lead:
                    share_first = share + pending_lead
                    pending_lead = 0.0
                    shots.append((pid, share_first))
                else:
                    shots.append((pid, share))
                current_panel = pid
        # Coalesce, preserving total seconds exactly. Two passes, each trivially
        # checkable: fold consecutive runs of the same panel, then absorb any shot
        # still under the floor into its neighbour.
        folded: list[list[Any]] = []
        for pid, sec in shots:
            if folded and folded[-1][0] == pid:
                folded[-1][1] += sec
            else:
                folded.append([pid, sec])

        merged: list[list[Any]] = []
        for pid, sec in folded:
            if sec < floor and merged:
                merged[-1][1] += sec          # too short: extend the previous shot
            else:
                merged.append([pid, sec])
        if len(merged) > 1 and merged[0][1] < floor:
            merged[1][1] += merged[0][1]      # a short FIRST shot has no previous
            merged = merged[1:]
        merged = [(pid, sec) for pid, sec in merged]

        if merged:
            plan[beat_id] = merged
    return plan or None
