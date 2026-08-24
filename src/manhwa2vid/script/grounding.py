"""Deterministic panel↔plot grounding for story-first outlines."""

from __future__ import annotations

import re

from manhwa2vid.models import ChapterSynopsis, SceneCard, ScriptOutlineBeat, SeriesBible

_STOP = frozenset(
    {
        "a", "an", "the", "and", "or", "to", "of", "in", "on", "at", "for", "with", "his", "her",
        "he", "she", "they", "them", "is", "are", "was", "were", "be", "as", "by", "from", "that",
        "this", "it", "into", "about", "after", "before", "while", "when", "who", "whom", "their",
    }
)

# Location / event keywords used for grounding lint and fact matching.
# These defaults are Solo Leveling ch.1 specifics; override per series/chapter via
# config script.grounding_keywords: {key: [phrase, ...]} — the adversarial frame audit
# (script/verify.py) is the general mechanism, this list is just a fast pre-filter.
# Concrete nouns whose presence in narration must be backed by panel evidence. This is a
# fast PRE-FILTER only; the adversarial VLM pass (script/verify.py) is the general
# mechanism and does not depend on it.
#
# There is no built-in list, because any list is a list about ONE series: the defaults
# here used to be coffee / food truck / healer / portal, which are Solo Leveling's props
# and meaningless for another title. The terms come from the project's own
# glossary.json ("terms": {"E-Rank": ["E Rank"], ...}) — human-editable, per-series — or
# from script.grounding_keywords in config. With neither, the pre-filter is empty and
# grounding rests entirely on the verifier, which is the correct fallback rather than
# flagging another series' narration against this one's furniture.
GROUNDING_KEYWORDS: dict[str, tuple[str, ...]] = {}


def configure_grounding_keywords(config: dict, glossary: dict | None = None) -> None:
    """Set the keyword pre-filter from config, else from the project glossary's terms."""
    GROUNDING_KEYWORDS.clear()

    override = None
    if isinstance(config, dict):
        override = (config.get("script") or {}).get("grounding_keywords")
    if isinstance(override, dict) and override:
        for key, phrases in override.items():
            if isinstance(phrases, (list, tuple)) and phrases:
                GROUNDING_KEYWORDS[str(key)] = tuple(str(p) for p in phrases)
        return

    terms = (glossary or {}).get("terms") if isinstance(glossary, dict) else None
    if isinstance(terms, dict):
        for key, aliases in terms.items():
            key = str(key).strip()
            if not key:
                continue
            phrases = {key.lower()}
            if isinstance(aliases, (list, tuple)):
                phrases.update(str(a).lower() for a in aliases if str(a).strip())
            GROUNDING_KEYWORDS[key.lower().replace(" ", "_")] = tuple(sorted(phrases))


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP and len(t) > 2}


def panel_evidence_blob(card: SceneCard) -> str:
    parts = [
        " ".join(card.panel_ids),
        " ".join(card.speakers),
        card.action,
        card.dialogue_summary,
        " ".join(card.key_terms),
        " ".join(p.name_used or p.descriptor or "" for p in card.people),
    ]
    return " ".join(p for p in parts if p)


def card_by_panel(cards: list[SceneCard]) -> dict[str, SceneCard]:
    mapping: dict[str, SceneCard] = {}
    for card in cards:
        for pid in card.panel_ids:
            mapping[pid] = card
    return mapping


_UTTERANCE_RE = re.compile(r"^(?P<who>[^:]{1,120}?):\s*(?P<text>.+)$", re.S)


def split_utterances(source_text: str) -> tuple[list[str], list[str], list[str]]:
    """Split a card's transcribed text into (addressed, monologue, unattributed).

    The panel text of a manhwa mixes three devices that must be narrated differently —
    speech bubbles, inner monologue / caption boxes, and ownerless text — and the vision
    schema already records which is which: an ADDRESSED line carries "Speaker -> Listener",
    a monologue line carries a speaker and no listener, and a caption carries neither.

    This used to be left to the writer. Every line went out under one "SPOKEN (convert to
    reported speech)" header, with a prompt rule asking the model to notice the exception
    — and it read Solo Leveling's opening monologue ("MY NAME IS SUNG JIN-WOO." / "E-RANK
    HUNTER.") as dialogue, narrating that a man bleeding to death alone was "introducing
    himself". 27 of that chapter's 78 lines are ownerless or listener-less, so the
    exception is a third of the evidence, not an edge case. The arrow is data; deciding
    it here is free and leaves the writer only the judgement it is actually good at.
    """
    addressed: list[str] = []
    monologue: list[str] = []
    unattributed: list[str] = []
    for raw in (source_text or "").split(" / "):
        line = raw.strip()
        if not line:
            continue
        m = _UTTERANCE_RE.match(line)
        if not m or m.group("who").strip().startswith(('"', "'", "\u201c")):
            unattributed.append(line)
        elif "->" in m.group("who"):
            addressed.append(line)
        else:
            monologue.append(line)
    return addressed, monologue, unattributed


def evidence_for_panels(panel_ids: list[str], cards: list[SceneCard]) -> str:
    by_panel = card_by_panel(cards)
    lines: list[str] = []
    seen: set[str] = set()
    for pid in panel_ids:
        card = by_panel.get(pid)
        if not card:
            continue
        key = ",".join(card.panel_ids)
        if key in seen:
            continue
        seen.add(key)
        # The writer gets ATTRIBUTED verbatim lines, not a paraphrase. Sending only
        # `dialogue_summary` cost us both attribution and register: the summary drops who
        # said what (one man's "MY sick mother's medical bills" became a crowd's
        # motivation) and, being itself an abstraction, invited a second one on top
        # ("questions the reckless pride of hunters"). With the real words present, the
        # writer converts verbatim -> reported speech ONCE, and vocatives plus
        # first-person pronouns make the owner of each line decidable.
        who = ", ".join(
            dict.fromkeys(
                p.name_used or p.descriptor or p.ref
                for p in card.people
                if (p.name_used or p.descriptor or p.ref)
            )
        )
        addressed, monologue, unattributed = split_utterances(card.source_text)
        parts = [
            f"{','.join(card.panel_ids)} | who={who or '(nobody)'} | action={card.action}"
        ]
        if addressed:
            parts.append(
                "\n    SAYS ALOUD (convert to reported speech, keep speaker AND listener): "
                + " / ".join(addressed)
            )
        if monologue:
            parts.append(
                "\n    THINKS (inner monologue or caption — voice it as this person's own "
                "thought; NEVER as something said to anyone, and never name the device): "
                + " / ".join(monologue)
            )
        if unattributed:
            parts.append(
                "\n    UNOWNED TEXT (no speaker shown — narrate the content without "
                "assigning an owner): " + " / ".join(unattributed)
            )
        if card.key_terms:
            parts.append(f"\n    terms={card.key_terms}")
        lines.append("".join(parts))
    return "\n".join(lines) or "(no scene evidence)"


def compact_panel_evidence(cards: list[SceneCard], bible: SeriesBible) -> str:
    """Per-panel evidence for outline: cast + action + dialogue."""
    lines: list[str] = []
    for card in cards:
        if not card.is_story:
            continue
        cast_parts: list[str] = []
        for person in card.people:
            mc_tag = " [MC]" if person.ref == bible.protagonist_id else ""
            label = person.name_used or person.descriptor or person.ref
            if person.ref in bible.characters:
                profile = bible.characters[person.ref]
                if not profile.canonical_name.lower().startswith(("guy ", "man ", "woman ", "blonde ")):
                    label = profile.canonical_name
            cast_parts.append(f"{label}{mc_tag}")
        lines.append(
            f"{','.join(card.panel_ids)} | cast={'; '.join(cast_parts) or '(none)'} | "
            f"action={card.action} | dialogue={card.dialogue_summary} | terms={card.key_terms}"
        )
    return "\n".join(lines)


def score_fact_against_card(fact: str, card: SceneCard) -> float:
    ft = _tokenize(fact)
    if not ft:
        return 0.0
    blob = _tokenize(panel_evidence_blob(card))
    if not blob:
        return 0.0
    overlap = len(ft & blob) / len(ft)
    # Boost exact phrase hits for known locations
    lower_blob = panel_evidence_blob(card).lower()
    lower_fact = fact.lower()
    bonus = 0.0
    for _key, phrases in GROUNDING_KEYWORDS.items():
        if any(p in lower_fact for p in phrases) and any(p in lower_blob for p in phrases):
            bonus += 0.35
    return overlap + bonus


def preassign_outline_from_facts(
    synopsis: ChapterSynopsis,
    cards: list[SceneCard],
    bible: SeriesBible,
    *,
    max_beats: int = 18,
) -> list[ScriptOutlineBeat]:
    """
    Seed outline beats by matching plot_facts to best panel clusters, then fill gaps.
    Preserves chronological panel order.
    """
    story_cards = [c for c in cards if c.is_story and c.panel_ids]
    if not story_cards:
        return []

    all_panel_ids = sorted({pid for c in story_cards for pid in c.panel_ids}, key=_panel_sort_key_local)
    assigned_panels: set[str] = set()
    unbound_facts: list[str] = []
    seeded: list[tuple[int, list[str], str, list[str]]] = []  # sort_key, panels, plot, char_ids

    for fact in synopsis.plot_facts:
        if not fact.strip():
            continue
        scored = [(score_fact_against_card(fact, card), card) for card in story_cards]
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_card = scored[0]
        if best_score < 0.15:
            # No panel carries this fact well enough to seed a beat — but the fact is
            # still true and often load-bearing. Dropping it here is how Frozen Player's
            # two payoff facts (the third floor needs the nucleus; Frost EX can melt the
            # seals) vanished before narration ever saw them. Keep it for placement.
            unbound_facts.append(fact.strip())
            continue
        panels = [pid for pid in best_card.panel_ids if pid not in assigned_panels]
        if not panels:
            # Allow reuse of already-assigned only if fact uniquely needs them — skip
            continue
        # Optionally merge adjacent unused panels from neighboring cards with weak score
        char_ids = [p.ref for p in best_card.people if p.ref and p.ref != "new"]
        if bible.protagonist_id and any(
            p.ref == bible.protagonist_id for p in best_card.people
        ):
            if bible.protagonist_id not in char_ids:
                char_ids.insert(0, bible.protagonist_id)
        sort_key = min(_panel_sort_key_local(pid) for pid in panels)
        seeded.append((sort_key[0] * 1000 + sort_key[1], panels, fact.strip(), char_ids))
        assigned_panels.update(panels)

    seeded.sort(key=lambda x: x[0])

    # Fill uncovered panels as continuity beats (adjacent groups)
    uncovered = [pid for pid in all_panel_ids if pid not in assigned_panels]
    fill_beats: list[tuple[int, list[str], str, list[str]]] = []
    if uncovered:
        by_panel = card_by_panel(story_cards)
        chunk: list[str] = []
        for pid in uncovered:
            if not chunk:
                chunk = [pid]
                continue
            prev = chunk[-1]
            # same page or consecutive — keep grouping small
            if _panel_sort_key_local(pid)[0] == _panel_sort_key_local(prev)[0] and len(chunk) < 3:
                chunk.append(pid)
            elif abs(_panel_sort_key_local(pid)[0] - _panel_sort_key_local(prev)[0]) <= 1 and len(chunk) < 2:
                chunk.append(pid)
            else:
                fill_beats.append(_continuity_seed(chunk, by_panel, bible))
                chunk = [pid]
        if chunk:
            fill_beats.append(_continuity_seed(chunk, by_panel, bible))

    combined = sorted([*seeded, *fill_beats], key=lambda x: x[0])

    # Soft-cap: merge adjacent tiny beats if over max_beats — but NEVER across a scene
    # boundary. A beat spanning distant pages forces the narration model to invent a
    # bridge between unrelated scenes; that invention was the dominant failure of the
    # first automated runs. max_beats is soft, so when no same-scene merge exists we
    # simply keep more beats.
    def _beat_page_range(panels: list[str]) -> tuple[int, int]:
        pages = [_panel_sort_key_local(pid)[0] for pid in panels]
        return min(pages), max(pages)

    while len(combined) > max_beats and len(combined) >= 2:
        best_i = -1
        best_size = 10**9
        for i in range(len(combined) - 1):
            _, a_hi = _beat_page_range(combined[i][1])
            b_lo, _ = _beat_page_range(combined[i + 1][1])
            if b_lo - a_hi > 1:
                continue  # different scene neighborhood — never merge
            size = len(combined[i][1]) + len(combined[i + 1][1])
            if size < best_size:
                best_size = size
                best_i = i
        if best_i < 0:
            break  # nothing mergeable within scene bounds; accept more beats
        a = combined[best_i]
        b = combined[best_i + 1]
        merged = (
            a[0],
            list(dict.fromkeys([*a[1], *b[1]])),
            f"{a[2]} / {b[2]}",
            list(dict.fromkeys([*a[3], *b[3]])),
        )
        combined = [*combined[:best_i], merged, *combined[best_i + 2 :]]

    # Place each unbound fact on the beat whose panels score best for it — the beat where
    # the writer is most likely to be able to land it — spreading them so one beat is not
    # asked to carry the whole synopsis.
    fact_context: dict[int, list[str]] = {}
    if unbound_facts:
        by_panel_card = card_by_panel(story_cards)
        for fact in unbound_facts:
            best_i, best = 0, -1.0
            for i, (_sk, panels, _plot, _cids) in enumerate(combined):
                score = max(
                    (score_fact_against_card(fact, by_panel_card[pid])
                     for pid in panels if pid in by_panel_card),
                    default=0.0,
                )
                score -= 0.05 * len(fact_context.get(i, []))
                if score > best:
                    best_i, best = i, score
            fact_context.setdefault(best_i, []).append(fact)

    outline: list[ScriptOutlineBeat] = []
    for idx, (_sk, panels, plot, char_ids) in enumerate(combined, start=1):
        panels = sorted(panels, key=_panel_sort_key_local)
        outline.append(
            ScriptOutlineBeat(
                beat_id=idx,
                panel_ids=panels,
                character_ids=char_ids,
                required_context=fact_context.get(idx - 1, []),
                plot_beat=plot[:400],
            )
        )
    return outline


def _continuity_seed(
    panels: list[str],
    by_panel: dict[str, SceneCard],
    bible: SeriesBible,
) -> tuple[int, list[str], str, list[str]]:
    card = by_panel.get(panels[0])
    action = (card.action if card else "") or "continues"
    dialogue = (card.dialogue_summary if card else "")[:120]
    plot = action if action else dialogue or "Story continues"
    char_ids = [p.ref for p in (card.people if card else []) if p.ref and p.ref != "new"]
    sort_key = min(_panel_sort_key_local(pid) for pid in panels)
    return (sort_key[0] * 1000 + sort_key[1], panels, plot[:400], char_ids)


def _panel_sort_key_local(panel_id: str) -> tuple[int, int, str]:
    match = re.match(r"p(\d+)_(\d+)", panel_id, re.I)
    if match:
        return int(match.group(1)), int(match.group(2)), panel_id
    return 9999, 9999, panel_id


def format_seeded_outline_for_prompt(beats: list[ScriptOutlineBeat], cards: list[SceneCard]) -> str:
    lines: list[str] = []
    for beat in beats:
        evid = evidence_for_panels(beat.panel_ids, cards)
        lines.append(
            f"SEED Beat {beat.beat_id} panels={beat.panel_ids} "
            f"chars={beat.character_ids}\n"
            f"  locked_plot={beat.plot_beat}\n"
            f"  evidence:\n{evid}"
        )
    return "\n".join(lines)


def narration_grounding_keywords(text: str) -> set[str]:
    lower = text.lower()
    hits: set[str] = set()
    for key, phrases in GROUNDING_KEYWORDS.items():
        if any(p in lower for p in phrases):
            hits.add(key)
    return hits


def evidence_supports_keywords(panel_ids: list[str], cards: list[SceneCard], keys: set[str]) -> set[str]:
    blob = evidence_for_panels(panel_ids, cards).lower()
    supported: set[str] = set()
    for key in keys:
        phrases = GROUNDING_KEYWORDS.get(key, ())
        if any(p in blob for p in phrases):
            supported.add(key)
    return supported


def unsupported_grounding_keywords(panel_ids: list[str], cards: list[SceneCard], narration: str) -> list[str]:
    claimed = narration_grounding_keywords(narration)
    if not claimed:
        return []
    supported = evidence_supports_keywords(panel_ids, cards, claimed)
    return sorted(claimed - supported)


# Transition captions the ART itself prints. Manhwa marks its own time skips on the page
# — Frozen Player's panels literally read "25 YEARS AGO" and "25 YEARS LATER" — and the
# vision pass has always captured them into scene cards, where nothing ever read them.
# English/manhwa-generic: no title's vocabulary appears here.
_TRANSITION_CAPTION_RE = re.compile(
    r"\b\d+\s*(?:years?|months?|weeks?|days?|hours?|minutes?)\s*"
    r"(?:later|ago|earlier|before|after)\b"
    r"|\b(?:meanwhile|present[- ]day|time\s*skip|flash\s*back|flashback|flash\s*forward"
    r"|flashforward|the next (?:day|morning|night)|that (?:night|morning|evening)"
    r"|(?:years?|months?|days?|hours?) (?:later|earlier|ago|before))\b",
    re.I,
)


def transition_captions(cards: list[SceneCard]) -> dict[str, str]:
    """panel_id -> the transition text the artwork prints on that panel.

    The strongest transition signal available and the one nothing consumed: page-number
    gaps find nothing on a densely-paginated chapter (Frozen Player's beat-to-beat gaps
    are all <= 1), and `last_flashforward_panel` is empty on that title. Meanwhile the
    panels say "25 YEARS LATER" in as many words.

    Reads `source_text` first: a caption box is transcribed there, and matching it in
    `action` too catches the vision pass paraphrasing it ("A time skip to the present day
    is shown"). Returns the matched words themselves so a fix hint can quote the manhwa.
    """
    out: dict[str, str] = {}
    for card in cards:
        blob = f"{card.source_text or ''} {card.action or ''}"
        match = _TRANSITION_CAPTION_RE.search(blob)
        if not match:
            continue
        for pid in card.panel_ids:
            out[pid] = " ".join(match.group(0).split())
    return out


def scene_boundaries(
    beats: list[ScriptOutlineBeat],
    cards: list[SceneCard] | None = None,
    *,
    flashforward_panel: str = "",
    min_page_gap: int = 2,
) -> dict[int, str]:
    """Beats that OPEN a new scene or time frame, with the reason — the storyboard's cuts.

    Both reported transition failures ("the past->museum jump plays as a continuation",
    "the fight->heroes cut is unmarked") are beats that begin a new block while the
    narration says nothing. This makes the cut list a first-class artifact: the story
    reviewer's checklist and the transition-coverage gate's denominator.

    Three signals in priority order, strongest first:
      1. a TRANSITION CAPTION in one of the beat's panels — the art told us outright, and
         its words go into the reason so a hint can quote them;
      2. the FLASHFORWARD anchor — the first beat after `last_flashforward_panel`;
      3. a PAGE GAP >= min_page_gap, the weak fallback. It finds nothing on a dense
         chapter, which is exactly why it cannot be the only signal.
    """
    out: dict[int, str] = {}
    if not beats:
        return out
    captions = transition_captions(cards or [])
    ff_page = _panel_sort_key_local(flashforward_panel)[0] if flashforward_panel else None
    prev_last_page: int | None = None
    ff_marked = False
    for beat in beats:
        pages = [_panel_sort_key_local(pid)[0] for pid in beat.panel_ids]
        if not pages:
            continue
        first_page, last_page = min(pages), max(pages)
        # Prefer the caption that names an INTERVAL over a bare "flashback": one beat can
        # carry both, and "25 YEARS LATER" is quotable in a fix hint while "flashback" is
        # only a label. Reading order breaks remaining ties.
        found = [captions[pid] for pid in beat.panel_ids if pid in captions]
        caption = next((c for c in found if any(ch.isdigit() for c2 in [c] for ch in c2)), "")
        caption = caption or (found[0] if found else "")
        if caption:
            out[beat.beat_id] = f'the art prints "{caption}" here'
        elif prev_last_page is not None:
            if (
                ff_page is not None
                and not ff_marked
                and prev_last_page <= ff_page < first_page
            ):
                out[beat.beat_id] = "time jump: first beat after the flashforward"
                ff_marked = True
            elif first_page - prev_last_page >= min_page_gap:
                out[beat.beat_id] = (
                    f"new scene: panels jump from page {prev_last_page} to {first_page}"
                )
        prev_last_page = max(prev_last_page or 0, last_page)
    return out


def refresh_plot_for_span(
    beats: list[ScriptOutlineBeat],
    cards: list[SceneCard],
    *,
    tail_fraction: float = 2 / 3,
) -> list[ScriptOutlineBeat]:
    """Make each beat's plot_beat describe its WHOLE panel span, not just its seed.

    `preassign_outline_from_facts` seeds a beat from ONE scene card, then
    `enforce_reading_order` repartitions — and it does exactly what it documents: "beat N
    owns everything from its own anchor up to the next beat's." A beat can therefore end
    up holding panels its plot_beat never mentioned, and nothing refreshed the plot_beat
    afterwards. On Solo Leveling ch1, 4 of 13 beats had a plot_beat whose best-matching
    panel sat at the very END of its own span.

    That was harmless while plot_beat was metadata on a crowded prompt line. It stopped
    being harmless when plot_beat became the MUST COVER spine of the beat block: the
    writer leads with it, so a plot describing the tail produced narration that started at
    the end. Beat 12 shipped its five panels in exactly reversed order. The same gap
    produced beat 14's nameless "He replies quickly to reassure her" — the panels its
    plot ignored got compressed into a pronoun.

    Only ever PREPENDS, and only for a beat whose plot demonstrably describes its tail.
    The added clause is built the way `_continuity_seed` builds one (the leading panel's
    card action) and joined with " / " the way the merge loop in
    `preassign_outline_from_facts` already joins two plots, so no new prose shape enters
    the outline. Panels are never reordered or dropped here.
    """
    from manhwa2vid.script.lint import _stemmed_words

    by_panel = card_by_panel(cards)
    out: list[ScriptOutlineBeat] = []
    for beat in beats:
        plot = (beat.plot_beat or "").split("/ CLOSER")[0].strip()
        panels = beat.panel_ids
        if not plot or len(panels) < 2:
            out.append(beat)
            continue
        plot_tokens = _stemmed_words(plot)
        if not plot_tokens:
            out.append(beat)
            continue
        scores: list[float] = []
        for pid in panels:
            card = by_panel.get(pid)
            text = f"{card.source_text or ''} {card.action or ''}" if card else ""
            tokens = _stemmed_words(text)
            scores.append(len(plot_tokens & tokens) / len(tokens) if tokens else 0.0)
        best = max(range(len(scores)), key=lambda i: scores[i])
        if scores[best] <= 0.0 or best < tail_fraction * (len(panels) - 1):
            out.append(beat)
            continue
        # The plot describes the tail. Describe the head too, from the first panel that
        # the plot does not already cover.
        lead_card = by_panel.get(panels[0])
        lead = ((lead_card.action if lead_card else "") or "").strip()
        if not lead or _stemmed_words(lead) <= plot_tokens:
            out.append(beat)
            continue
        out.append(beat.model_copy(update={"plot_beat": f"{lead[:200]} / {beat.plot_beat}"}))
    return out


def enforce_reading_order(beats: list[ScriptOutlineBeat]) -> list[ScriptOutlineBeat]:
    """Make every beat a CONTIGUOUS run of panels in reading order.

    `preassign_outline_from_facts` scores each plot_fact against its best-matching scene
    card, and continuity beats mop up whatever is left. Neither step constrains the shape
    of the result, so a beat could hold panels that straddle another beat's panels:

        beat 10: p0017_01, p0018_02, p0018_03
        beat 11: p0017_02, p0018_04

    Reading order is p0017_01, p0017_02, p0018_02, p0018_03, p0018_04 — so beat 11
    narrated Jin-Woo ASKING for coffee after beat 10 had already walked him away from the
    stall, and both beats narrated the refusal. That is the reported "order of narration
    is a little messed up" and a large share of the cross-beat repetition: two beats given
    overlapping stretches of one moment will both tell it, however the prompt is worded.

    The repair keeps every beat and every panel — only the cut points move. Each beat is
    anchored at its earliest panel; beats are then ordered by anchor and the panel
    sequence is partitioned at those anchors, so beat N owns everything from its own
    anchor up to the next beat's.
    """
    if len(beats) < 2:
        return beats

    ordered_panels = sorted(
        {pid for beat in beats for pid in beat.panel_ids}, key=_panel_sort_key_local
    )
    # Fewer panels than beats makes a one-panel-per-beat partition impossible; the
    # original bindings at least keep every beat non-empty, which conservation requires.
    if not ordered_panels or len(beats) > len(ordered_panels):
        return beats
    index = {pid: i for i, pid in enumerate(ordered_panels)}

    anchored = sorted(
        beats,
        key=lambda b: (
            min((index[p] for p in b.panel_ids), default=len(ordered_panels)),
            b.beat_id,
        ),
    )

    # Anchors must be strictly increasing, or a later beat would be handed nothing.
    anchors: list[int] = []
    for beat in anchored:
        start = min((index[p] for p in beat.panel_ids), default=len(ordered_panels))
        floor = anchors[-1] + 1 if anchors else 0
        anchors.append(max(start, floor))
    # A beat pushed past the end of the sequence would be emptied; pull the run back so
    # every beat keeps at least one panel. Both bounds are strictly increasing in i, so
    # their elementwise minimum stays strictly increasing and no beat collapses.
    for i in range(len(anchors) - 1, -1, -1):
        anchors[i] = min(anchors[i], len(ordered_panels) - (len(anchors) - i))

    out: list[ScriptOutlineBeat] = []
    for pos, beat in enumerate(anchored):
        start = anchors[pos]
        end = anchors[pos + 1] if pos + 1 < len(anchors) else len(ordered_panels)
        run = ordered_panels[start:end]
        out.append(beat.model_copy(update={"panel_ids": run}) if run != beat.panel_ids else beat)

    # Restore the caller's beat_id ordering: only the panel bindings were being repaired.
    return sorted(out, key=lambda b: b.beat_id)


def inject_closer_evidence(
    beats: list[ScriptOutlineBeat],
    cards: list[SceneCard],
    max_chars: int = 420,
    tail_panels: int = 6,
) -> list[ScriptOutlineBeat]:
    """Pin the chapter's final on-panel content to the closer beat's plot_beat.

    The synopsis is a lossy channel: on the second title tested, the last panels carried
    the chapter's entire point — a system message revealing the frozen team CAN be freed
    — and plot_facts compressed it into its negative ("unable to free his comrades").
    Every layer downstream then told the wrong ending, while the scene cards held the
    reveal verbatim. Reveals are positional, not series-specific: whatever the final
    story panels SAY is what the chapter chose to end on, so it is quoted into the
    closer's plot line deterministically instead of trusted to prose compression.
    """
    if not beats or not cards:
        return beats
    by_panel: dict[str, SceneCard] = {}
    for card in cards:
        for pid in card.panel_ids:
            by_panel[pid] = card
    ordered = sorted(by_panel, key=_panel_sort_key_local)
    lines: list[str] = []
    for pid in ordered[-tail_panels:]:
        text = " ".join((by_panel[pid].source_text or "").split())
        if text and text not in lines:
            lines.append(text)
    evidence = " / ".join(lines)[:max_chars]
    if not evidence:
        return beats
    closer = next((b for b in beats if b.is_closer), beats[-1])
    if evidence.lower()[:60] in closer.plot_beat.lower():
        return beats
    updated = closer.model_copy(
        update={
            "plot_beat": (
                f"{closer.plot_beat} / CLOSER EVIDENCE — the chapter deliberately ENDS "
                f"on this; the final beat must land its content: {evidence}"
            )
        }
    )
    return [updated if b.beat_id == closer.beat_id else b for b in beats]
