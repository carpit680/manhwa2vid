"""Recover already-paid matcher claims into the content-addressed cache.

`debug/match_claims.json` has always recorded every claim the matcher collected, but
write-only — nothing read it back. So a project that cost 3.3M prompt tokens could not
re-run a single deterministic downstream change without paying again.

The windowing is deterministic, so the cache keys can be reconstructed: walk each block's
panels in windows of `match_window_panels`, scope the sentences exactly as
`collect_claims` does, and attribute each recorded claim to the window that contained its
panel. If the reconstruction is right, a replay reproduces the existing shot list
exactly — which is the check `tools/replay.py --verify` performs, and the only reason to
trust this file.

    python tools/seed_claim_cache.py projects/<name>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from manhwa2vid.config import get_nested, load_config          # noqa: E402
from manhwa2vid.script import match as M                        # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    project = Path(sys.argv[1])
    claims_path = project / "debug" / "match_claims.json"
    if not claims_path.exists():
        print(f"no {claims_path} — nothing paid for to recover")
        return 1
    config = load_config()
    window = int(get_nested(config, "align", "match_window_panels", default=16))
    data = json.loads(claims_path.read_text(encoding="utf-8"))

    shotlist = json.loads((project / "script.shotlist.json").read_text(encoding="utf-8"))
    text_of = {int(s["number"]): s["text"] for s in shotlist["sentences"]}

    M.reset_claim_cache()
    cache = M._load_claim_cache({"debug": project / "debug"})
    seeded = skipped = 0

    for blk in data.get("blocks", []):
        texts = blk.get("sentence_texts") or {}
        numbers = [int(n) for n in blk.get("sentences") or []]
        sents = [(n, texts.get(str(n)) or text_of.get(n, "")) for n in numbers]
        if any(not t for _, t in sents):
            skipped += 1
            continue
        panel_ids = list(blk.get("panels") or [])
        # Claims are recorded per block; attribute each to the window holding its panel.
        by_panel: dict[str, list[list]] = {}
        for number, pid in blk.get("raw") or []:
            by_panel.setdefault(pid, []).append([int(number), str(pid)])

        for start in range(0, len(panel_ids), window):
            batch = panel_ids[start:start + window]
            scoped = M._window_sentences(sents, _fake_panels(batch), None)
            key = M._cache_key(M._SYSTEM, batch, scoped)
            claims: list[list] = []
            for pid in batch:
                claims.extend(by_panel.get(pid, []))
            cache[key] = claims
            seeded += 1

    M._CLAIM_CACHE_DIRTY = True
    M.save_claim_cache()
    print(f"seeded {seeded} window(s) into {project/'debug'/'matcher_cache.json'}"
          + (f"; skipped {skipped} block(s) with no sentence text" if skipped else ""))
    print("verify with: python tools/replay.py", project, "--verify")
    return 0


class _P:
    __slots__ = ("id",)

    def __init__(self, pid: str) -> None:
        self.id = pid


def _fake_panels(ids: list[str]) -> list[_P]:
    """`_window_sentences` only reads `.id`."""
    return [_P(i) for i in ids]


if __name__ == "__main__":
    raise SystemExit(main())
