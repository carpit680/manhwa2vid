"""Rebuild a project's shot list from its PERSISTED raw claims — no first-pass calls.

The raw claims in debug/match_claims.json are the expensive artifact (one vision call
per 16-panel window over every block). Filter changes — co-claims, radius — do not
need them re-paid: this tool re-runs `filter_monotonic` over the persisted raw+second
claims, runs `_second_pass_claims` live for whatever gaps REMAIN (short-gap probes are
a handful of panels each), filters once more, and rewrites script.shotlist.json's
per-sentence panels in place. Everything else in the shotlist — sentence numbering,
beats, blocks, returns — is untouched, so TTS sidecars stay valid and only the
timeline needs rebuilding.

Usage: PYTHONPATH= .venv/bin/python tools/rebind_from_claims.py projects/<name> [--dry]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from manhwa2vid.config import load_config
from manhwa2vid.models import project_paths, save_json
from manhwa2vid.panels.filter import load_story_panels
from manhwa2vid.script.match import _second_pass_claims, filter_monotonic


def main() -> None:
    project = Path(sys.argv[1])
    dry = "--dry" in sys.argv
    paths = project_paths(project)
    config = load_config()
    debug_file = paths["debug"] / "match_claims.json"
    claims_doc = json.loads(debug_file.read_text(encoding="utf-8"))
    shotlist = json.loads(paths["script_shotlist_json"].read_text(encoding="utf-8"))
    sentences = shotlist["sentences"]
    by_id = {p.id: p for p in load_story_panels(paths)}

    claims_by_number: dict[int, list[str]] = {}
    for blk in claims_doc["blocks"]:
        panel_ids = blk["panels"]
        raw_all = [tuple(c) for c in blk["raw"]] + [tuple(c) for c in blk.get("second", [])]
        kept = filter_monotonic(raw_all, panel_ids)
        block_sents = [
            (s["number"], s["text"]) for s in sentences if s["number"] in set(blk["sentences"])
        ]
        panels = [by_id[pid] for pid in panel_ids if pid in by_id]
        second_new = []
        if not dry:
            second_new = _second_pass_claims(block_sents, panels, kept, paths, config)
            if second_new:
                kept = filter_monotonic(raw_all + second_new, panel_ids)
        print(
            f"block {blk['block']}: {len(raw_all)} raw -> {len(kept)} kept"
            + (f" (+{len(second_new)} new second-pass)" if second_new else "")
        )
        blk["second"] = blk.get("second", []) + [[n, p] for n, p in second_new]
        blk["kept"] = [[n, p] for n, p in kept]
        for number, pid in kept:
            claims_by_number.setdefault(number, []).append(pid)

    for sent in sentences:
        sent["panels"] = claims_by_number.get(sent["number"], [])
    scored = [s for s in sentences if not s.get("outro")]
    matched = sum(1 for s in scored if s["panels"])
    print(f"match rate: {matched}/{len(scored)} = {100 * matched / len(scored):.0f}%")
    if dry:
        print("(dry run — nothing written)")
        return
    save_json(paths["script_shotlist_json"], shotlist)
    debug_file.write_text(json.dumps(claims_doc, indent=1), encoding="utf-8")
    print(f"wrote {paths['script_shotlist_json']}")


if __name__ == "__main__":
    main()
