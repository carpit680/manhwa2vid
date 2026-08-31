"""Apply the rhythm pass to an EXISTING project's approved script, in place.

The pass runs inside generate_story_first_script for fresh runs; existing projects
have approved, audited scripts that must not be regenerated. This applies the same
deterministic pass to each BEAT NARRATION of script.final.md/script.draft.md and
renumbers the persisted matcher artifacts by the merge map, so the first-pass vision
calls are never re-paid.

Numbering is over beat narrations ONLY — the same space as the shotlist and the
claims artifact. The first version of this tool numbered over the raw markdown
(headers and the hook counted as sentences) and corrupted all three projects'
shotlists; the repair rebuilt them from the TTS sidecars. `sentence_count_check`
below is the guard: the tool refuses to run when its own numbering disagrees with
the shotlist's.

Renumbering:
- debug/match_claims.json: sentence lists and claim numbers remapped,
- script.shotlist.json: absorbed rows fold into their keeper (panels appended in
  order), texts refreshed from the revised narration, numbers resequenced.

TTS audio and the timeline are NOT touched — narration changed, so the caller must
re-run TTS with --force and rebuild the timeline afterwards.

Usage: PYTHONPATH= .venv/bin/python tools/apply_rhythm.py projects/<name>
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from manhwa2vid.models import project_paths, save_json
from manhwa2vid.script.rhythm import _rhythm_paragraph, opener_profile
from manhwa2vid.script.sentences import split_sentences

_BEAT_SPLIT = r"(### Beat (\d+)\n)"


def _beats_of(markdown: str) -> dict[int, str]:
    parts = re.split(_BEAT_SPLIT, markdown)
    out = {}
    for i in range(1, len(parts), 3):
        num, body = int(parts[i + 1]), parts[i + 2]
        prefix = re.match(r"((?:<!--.*?-->\n)?\n?)", body, re.S).group(1)
        out[num] = body[len(prefix):].strip()
    return out


def _replace_beats(markdown: str, narrations: dict[int, str]) -> str:
    parts = re.split(_BEAT_SPLIT, markdown)
    out = [parts[0]]
    for i in range(1, len(parts), 3):
        header, num, body = parts[i], int(parts[i + 1]), parts[i + 2]
        prefix = re.match(r"((?:<!--.*?-->\n)?\n?)", body, re.S).group(1)
        tail = re.search(r"(\n*\Z)", body).group(1) or "\n"
        out += [header, prefix, narrations[num], tail]
    return "".join(out)


def main() -> None:
    project = Path(sys.argv[1])
    paths = project_paths(project)
    if (paths["debug"] / "rhythm_pass.json").exists():
        print("already applied — nothing to do")
        return
    final = paths["script_final"]
    text = final.read_text(encoding="utf-8")
    beats = _beats_of(text)

    sl_path = paths["script_shotlist_json"]
    shotlist = json.loads(sl_path.read_text(encoding="utf-8"))
    beat_order = []
    for row in shotlist["sentences"]:
        if not beat_order or beat_order[-1] != int(row["beat_id"]):
            beat_order.append(int(row["beat_id"]))

    # numbering guard: this tool's sentence space must BE the shotlist's
    counted = sum(len(split_sentences(beats[b])) for b in beat_order)
    if counted != len(shotlist["sentences"]):
        raise SystemExit(
            f"numbering mismatch: {counted} beat-narration sentences vs "
            f"{len(shotlist['sentences'])} shotlist rows — refusing to renumber"
        )

    old_prose = "\n\n".join(beats[b] for b in beat_order)
    merges: list[tuple[int, int]] = []
    insertions = 0
    revised: dict[int, str] = {}
    no = 1
    for b in beat_order:
        narr = beats[b]
        n_sents = len(split_sentences(narr))
        if "subscri" in narr.lower():
            revised[b] = narr
        else:
            new_narr, beat_merges, edits = _rhythm_paragraph(narr, no)
            revised[b] = new_narr
            merges.extend(beat_merges)
            insertions += edits - len(beat_merges)
        no += n_sents

    absorbed = {b for _a, b in merges}
    keeper_of = {b: a for a, b in merges}
    remap: dict[int, int] = {}
    new_no = 0
    for old in range(1, len(shotlist["sentences"]) + 1):
        if old in absorbed:
            remap[old] = remap[keeper_of[old]]
        else:
            new_no += 1
            remap[old] = new_no

    new_md = _replace_beats(text, revised)
    final.write_text(new_md, encoding="utf-8")
    draft = paths["script_draft"]
    if draft.exists():
        draft.write_text(_replace_beats(draft.read_text(encoding="utf-8"), revised),
                         encoding="utf-8")

    # shotlist: fold absorbed rows into keepers, refresh texts, renumber
    new_texts = [s for b in beat_order for s in split_sentences(revised[b])]
    rows: dict[int, dict] = {}
    order: list[int] = []
    for sent in shotlist["sentences"]:
        old = int(sent["number"])
        tgt = remap[old]
        if tgt in rows:
            for pid in sent.get("panels") or []:
                if pid not in rows[tgt]["panels"]:
                    rows[tgt]["panels"].append(pid)
        else:
            sent["number"] = tgt
            sent["text"] = new_texts[tgt - 1]
            rows[tgt] = sent
            order.append(tgt)
    shotlist["sentences"] = [rows[n] for n in order]
    save_json(sl_path, shotlist)

    # claims artifact
    dbg = paths["debug"] / "match_claims.json"
    doc = json.loads(dbg.read_text(encoding="utf-8"))
    for blk in doc["blocks"]:
        blk["sentences"] = sorted({remap[n] for n in blk["sentences"]})
        for key in ("raw", "second", "kept"):
            blk[key] = [[remap[n], pid] for n, pid in blk.get(key, [])]
    dbg.write_text(json.dumps(doc, indent=1), encoding="utf-8")

    new_prose = "\n\n".join(revised[b] for b in beat_order)
    record = {
        "before": opener_profile(old_prose), "after": opener_profile(new_prose),
        "merges": merges, "insertions": insertions, "violations": [],
        "applied_by": "tools/apply_rhythm.py",
    }
    (paths["debug"] / "rhythm_pass.json").write_text(
        json.dumps(record, indent=1), encoding="utf-8"
    )
    b, a = record["before"], record["after"]
    print(f"applied: {len(merges)} merge(s), {insertions} insertion(s); "
          f"{len(shotlist['sentences']) + len(absorbed)} -> {new_no} sentences")
    print(f"openers: pron {b['pronoun_open_pct']}->{a['pronoun_open_pct']}  "
          f"b2b {b['b2b_pct']}->{a['b2b_pct']}  conn {b['connector_pct']}->{a['connector_pct']}")


if __name__ == "__main__":
    main()
