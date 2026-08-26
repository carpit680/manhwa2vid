"""The one sentence splitter, shared by everything that must agree on it.

Three byte-identical copies of this regex used to live in timeline.py, align.py and
tts/engine.py. That was survivable while they were independent conveniences; it stops
being survivable now that sentence IDENTITY is load-bearing: the shot list matches
narration sentence i to a panel, and the TTS sidecar supplies sentence i's measured
seconds — verified exact across 54/54 real beats precisely BECAUSE the splitters agree.
An edit to one copy that missed the others would silently desynchronise picture from
sound.

Deliberately not honorific-aware (this is NOT lint._SENTENCE_SPLIT_RE): the TTS sidecar
text comes back from Kokoro, and both sides of the sentence-identity contract must split
the same way. Changing the pattern means changing it for the writer's text and the
sidecar text together, and re-verifying the 54-beat identity check.
"""

from __future__ import annotations

import re

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT_RE.split((text or "").strip()) if s.strip()]
