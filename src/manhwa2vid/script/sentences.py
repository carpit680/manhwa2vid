"""The one sentence splitter, shared by everything that must agree on it.

Three byte-identical copies of this regex used to live in timeline.py, align.py and
tts/engine.py. That was survivable while they were independent conveniences; it stops
being survivable now that sentence IDENTITY is load-bearing: the shot list matches
narration sentence i to a panel, and the TTS sidecar supplies sentence i's measured
seconds — verified exact across 54/54 real beats precisely BECAUSE the splitters agree.
An edit to one copy that missed the others would silently desynchronise picture from
sound.

Honorific-aware since 2026-08-28: the naive lookbehind-only split turned "Mr. Song
checks his watch" into "Mr." + "Song checks his watch" — Solo Leveling's shipped script
carried EIGHT phantom "Mr." sentences, each synthesized by Kokoro as its own utterance
with full terminal prosody (0.975s of "MISTER." followed by a pause, verified in
beat_004.segments.json), and each a permanent miss in the match-rate denominator. The
abbreviation list is fixed and short, mirroring lint's — every consumer imports THIS
pattern, so the writer's text and the TTS sidecar text move together and sentence
identity is preserved by construction. Each lookbehind is fixed-width, which is what
Python's re requires.
"""

from __future__ import annotations

import re

SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[.!?])(?<!Mr\.)(?<!Ms\.)(?<!Dr\.)(?<!St\.)(?<!Jr\.)(?<!Sr\.)(?<!Mrs\.)\s+"
)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT_RE.split((text or "").strip()) if s.strip()]
