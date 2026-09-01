"""Let a sentence that recalls an earlier scene put that earlier picture back on screen.

The writer-narrator is asked to remember things for the viewer — "this is the same guy
from the food truck", "remember what the system told him two floors ago". Said over the
current art, that lands only as words; the natural edit is to show the shot being
recalled, which is what the reference channel does and what every human editor does.

Panel reuse was previously forbidden outright, and for a good reason: accidental reuse
looked exactly like a bug on screen (a hunter's leg close-up at 605.2s and again at
627.3s, 22 seconds before the line that earned it). So this is a NARROWING of that rule,
never a loosening:

    a panel may appear twice only if exactly one of the appearances belongs to a
    sentence marked `callback`, and the two are far enough apart to read as deliberate.

Everything else still fails the render. A sentence earns the mark two ways at once — it
must open with a recall frame AND resolve to a specific earlier sentence by content
overlap — so a passing use of the word "remember" cannot produce a repeat.

Resolution is deterministic and costs no model call: the recall sentence's content words
are matched against the content words of earlier sentences that own a panel, and the best
scoring one above `_MIN_OVERLAP` donates its panel. Below that threshold the sentence
stays a normal unmatched sentence and the callback is verbal only, which is the correct
failure direction — a wrong picture is worse than no picture.
"""

from __future__ import annotations

import re
from typing import Any

#: Frames that announce a recall. Deliberately narrow and anchored to the start of the
#: sentence or a clause: "he remembers his mother" is the STORY remembering, not the
#: narrator, and must never trigger a replay.
_RECALL_RE = re.compile(
    r"(?:^|[,;—-]\s*)(?:"
    # "\b" after the verb or "Remembering the weeks in hospital" — the CHARACTER
    # remembering — matched, which is the one thing this detector must never do.
    r"remember\b(?:\s+(?:when|what|that|the|how))?"
    r"|if you remember\b"
    r"|as you (?:may )?(?:remember|recall)\b"
    # "back when" is temporal recall; "back in the hospital room" is a scene
    # transition and one of the most common sentence openers in a recap. Only the
    # temporal form survives.
    r"|back when\b"
    r"|this is the same\b"
    r"|that(?:'s| is) the same\b"
    r"|the same (?:\w+\s+){0,2}(?:who|that|from)\b"
    r"|earlier[,\s]"
    r"|way back\b"
    r"|call(?:ing|s)? back to\b"
    r")",
    re.I,
)

#: Words that carry no identifying signal when matching a recall to its origin.
_STOP = {
    "the", "a", "an", "and", "or", "but", "of", "on", "in", "to", "with", "for", "at",
    "from", "his", "her", "their", "its", "this", "that", "these", "those", "is", "was",
    "are", "were", "be", "been", "it", "he", "she", "they", "him", "them", "you", "who",
    "same", "remember", "back", "earlier", "again", "still", "just", "now", "then",
    "one", "guy", "man", "woman", "thing", "way", "time", "when", "what", "how", "why",
}

#: Content-word overlap a candidate origin must reach before it may donate its panel.
#: Two shared distinctive words is the floor — one is coincidence at recap length.
_MIN_OVERLAP = 2

#: A callback must sit at least this many sentences after the shot it replays, or the
#: viewer reads it as a stutter rather than a return.
_MIN_DISTANCE = 12


def is_recall(sentence: str) -> bool:
    """Whether the sentence announces that it is recalling something already shown."""
    return bool(_RECALL_RE.search(sentence or ""))


def _content(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-z'’-]+", (text or "").lower())
        if len(w) > 2 and w not in _STOP
    }


def resolve_callbacks(sentences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark recall sentences and give them the panel of the scene they recall.

    Mutates and returns the shotlist's sentence rows. Only sentences with NO panel of
    their own are considered: a sentence the matcher already bound is describing
    something on the page in front of it, and overriding that to replay an old shot
    would trade a correct picture for a clever one.

    Returns the rows that became callbacks, for the record and for review.
    """
    made: list[dict[str, Any]] = []
    # (sentence row, its content words) for everything that owns a panel, in order.
    origins: list[tuple[dict[str, Any], set[str]]] = []
    for row in sentences:
        number = int(row.get("number", 0))
        panels = list(row.get("panels") or [])
        if panels:
            origins.append((row, _content(row.get("text", ""))))
            continue
        if row.get("outro") or not is_recall(row.get("text", "")):
            continue
        want = _content(row.get("text", ""))
        best, best_score = None, 0
        for origin_row, origin_words in origins:
            if number - int(origin_row.get("number", 0)) < _MIN_DISTANCE:
                continue
            # A callback may only reach back inside its own time block: replaying art
            # from across a printed time skip shows the wrong era.
            if int(origin_row.get("block", 0)) != int(row.get("block", 0)):
                continue
            score = len(want & origin_words)
            if score > best_score:
                best, best_score = origin_row, score
        if best is None or best_score < _MIN_OVERLAP:
            continue
        # The LAST panel the origin shows is the one the viewer remembers it by.
        row["panels"] = [list(best["panels"])[-1]]
        row["callback"] = True
        row["callback_of"] = int(best.get("number", 0))
        made.append(row)
    return made


def callback_panels(shotlist: dict[str, Any]) -> set[str]:
    """Panels a callback sentence deliberately replays — the only legal repeats."""
    return {
        pid
        for sent in (shotlist.get("sentences") or [])
        if sent.get("callback")
        for pid in (sent.get("panels") or [])
    }


#: A closing run this long (in sentences) with nothing new to show is a freeze, not a
#: held beat. Three is what Frozen Player ch3-4 produced: one matched sentence and then
#: the outro, 19.1 seconds on the chapter's final panel.
_CODA_MIN_SENTENCES = 2


def resolve_closing_coda(
    sentences: list[dict[str, Any]], ordered_panel_ids: list[str]
) -> dict[str, Any] | None:
    """Give the closing ask its own picture instead of freezing the last story panel.

    Measured on both titles whose renders exceeded the hold limit: the >18s holds are
    the FINAL run on the FINAL panel. The narration's last sentences — usually the outro,
    which is narrator-to-viewer and panel-grounded by nothing — inherit whatever the
    story ended on, and the planner cannot help, because `_gap_spare` looks forward into
    an empty range (there is nothing after the last panel) and backward only within
    SCENE_RADIUS, where everything is already shown.

    There IS material: ch3-4 had 11 unused panels in its last 40, the nearest 18
    positions back. Eighteen back is a rewind, which is why the planner refuses it and
    why this must be marked rather than smuggled in — a coda is a deliberate edit, the
    same category as a callback, and it rides the same gate exemption. Closing on
    earlier art over the sign-off is what the reference channel does.

    Prefers an unused panel (new art beats a repeat); falls back to replaying the beat's
    opening shot. Returns the row it changed, or None when the closing run is short
    enough to be a normal held beat.
    """
    scored = [s for s in sentences if not s.get("outro")]
    closing = [s for s in sentences if s.get("outro")]
    if not closing:
        # No marked outro: fall back to the trailing run of unbound sentences.
        trailing: list[dict[str, Any]] = []
        for row in reversed(sentences):
            if row.get("panels"):
                break
            trailing.append(row)
        closing = list(reversed(trailing))
    if len(closing) < _CODA_MIN_SENTENCES or any(c.get("panels") for c in closing):
        return None

    pos = {pid: i for i, pid in enumerate(ordered_panel_ids)}
    claimed = {pid for s in sentences for pid in (s.get("panels") or [])}
    last_shown = max((pos[p] for p in claimed if p in pos), default=None)
    if last_shown is None:
        return None

    unused = [p for p in ordered_panel_ids[:last_shown] if p not in claimed]
    pick = unused[-1] if unused else None
    if pick is None:
        first_claimed = min((pos[p] for p in claimed if p in pos), default=None)
        if first_claimed is None:
            return None
        pick = ordered_panel_ids[first_claimed]

    row = closing[0]
    row["panels"] = [pick]
    row["callback"] = True
    row["coda"] = True
    return row
