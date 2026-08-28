"""QA on the RENDERED video — the final surface, not what upstream intended.

Every detector here is lifted from the 2026-08-26 audit that measured the defects
shipping: 19s of speech bubbles on black opening SL, 46% of frames with edge-clipped
text, 62-68% mean dead width, +0.3 dBTP clipping. Nothing upstream can prove those
absent; only the pixels and samples of the finished file can.

Thresholds are pinned by tests against the audit's measured values (tune the
threshold, never the metric). The shot-length comparison bands are CONSTANTS measured
once from the reference channel with tools/profile_shots.py — runtime code must not
read reference/ (tests/test_series_agnostic.py enforces that).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.measure.audio import measure_audio
from manhwa2vid.measure.frames import (
    FRAME_FPS,
    FRAME_H,
    FRAME_W,
    bubble_stats,
    dead_width,
    iter_frames,
    lettering_masks,
)
from manhwa2vid.measure.shots import detect_cuts, shot_lengths
from manhwa2vid.qa import QAReport, enforce, qa_forced

console = Console()

# The primitives live in `manhwa2vid.measure` so the gate that blocks a render and the
# tool that profiles the reference channel cannot drift apart. These aliases keep the
# historical names working for tests and callers.
_W, _H, _FPS = FRAME_W, FRAME_H, FRAME_FPS
_iter_frames = iter_frames
_bubble_stats = bubble_stats
_dead_width = dead_width

# Measured from the reference channel (see reference/mamoru_shot_profile.md):
# median 2.87s, 22% of shots under 1.5s, 16.3 cuts/min. Report-only bands.
_REF_MEDIAN_S = 2.87
_REF_UNDER_1_5_PCT = 22.0
# Same-content baseline (reference channel's OWN edit of the same opening chapters,
# run through these exact detectors, 2026-08-26): bubble-over-20% 21.9%, clipped-text
# 43.9%. Dialogue-heavy openings simply carry more bubbles — bands must not punish the
# source material. NOTE: 21.9 is measured with the same imprecise bubble detector as our
# own number, so it is inflated by pale artwork too — both sides of that comparison are
# report-only. See the bubble-dominance note in `enforce_render_qa`.
_REF_BUBBLE_PCT = 21.9
_REF_CLIPPED_PCT = 43.9

# Audio bands — docs/audio-quality-spec.md §6, reconciled in
# reports/render_audit_2026-08-28.md. Loudness has no constant here on purpose: it is
# judged against `export.loudness_target` so the gate cannot codify the current undershoot.
_TRUE_PEAK_MAX_DBTP = -1.0
_BED_FLOOR_MIN_DBFS = -40.0
_BED_TONALITY_MIN = 5.0
_DUCK_MIN_DB, _DUCK_MAX_DB = 12.0, 15.0
_LRA_MIN_LU, _LRA_MAX_LU = 5.0, 9.0

# Rhythm bands. Derived from the reference channel measured with THIS scene detector over
# three windows (reference/mamoru_metrics_2026-08-28.json), not from the hardening brief's
# proposals — four of those would have failed the reference itself. Justifications live in
# reports/render_audit_2026-08-28.md §5.
_MEDIAN_MIN_S, _MEDIAN_MAX_S = 2.0, 3.5
_ACCENT_MIN_PCT = 15.0
_CADENCE_MIN, _CADENCE_MAX = 12.0, 22.0     # brief said 12-20; reference W1 is 20.08
_SHOT_MAX_WARN_S, _SHOT_MAX_FAIL_S = 12.0, 18.0   # brief said fail at 12; reference is 16.37
_LONGTAIL_WARN_PCT, _LONGTAIL_FAIL_PCT = 18.0, 25.0  # brief said 15; reference reaches 22.2

# Opening. A viewer decides in ten seconds, so the window is 15, not 4 — Solo Leveling's
# bubble-on-black opener sits at t=6s and a 4s window could not see it. The art floors are
# measured: the reference's own per-second minimum over the first 15s is 26.2% (W2) and
# 45.7% (W1), so the brief's proposed 50% floor would fail the reference.
_OPENING_SECONDS = 15.0
# Re-derived 2026-08-28 against BOTH sides, which the first version never had. It was set
# to 0.15 from the reference's per-second window minimum (26.2% W2, 45.7% W1) — a value
# with no negative example behind it, and it then failed a legitimate frame: Frozen
# Player's Frost Queen crown against a dark ground measures 0.13, and it is a strong
# atmospheric shot, not a defect. The actual defect — Solo Leveling opening on a bubble on
# black — measured 0.054. The floor now sits between the two, with the warn band still
# well under the reference.
_OPENING_ART_FAIL, _OPENING_ART_WARN = 0.09, 0.20


def measure_video(video: Path) -> dict[str, Any]:
    """Whole-runtime frame metrics + audio true peak + shot-length stats."""
    bubble_fracs: list[float] = []
    clipped_flags: list[bool] = []
    dead: list[float] = []
    lumas: list[float] = []
    lettering: list[float] = []
    art: list[float] = []
    opening_frames: list[np.ndarray] = []
    # 15 seconds, not 4: a viewer decides in the first ten, and Solo Leveling's
    # bubble-on-black opener sits at t=6s — outside a 4s window entirely.
    open_budget = int(_OPENING_SECONDS * _FPS)
    for frame in _iter_frames(video):
        if len(opening_frames) < open_budget:
            opening_frames.append(frame.copy())
        frac, clipped = _bubble_stats(frame)
        bubble_fracs.append(frac)
        clipped_flags.append(clipped)
        dead.append(_dead_width(frame))
        lumas.append(float(frame.mean()))
        text_mask, content_mask = lettering_masks(frame)
        lettering.append(float(text_mask.mean()))
        # "Art" is content that is not lettering: what the viewer is here to look at.
        art.append(float((content_mask & ~text_mask).mean()))

    n = max(len(lumas), 1)
    open_n = min(open_budget, n)
    # Lettering in the opening, measured with the VALIDATED detector rather than the
    # bright-blob test below. The two disagreed on the 2026-08-27 render and the blob
    # test was wrong: it read the Frost Queen's pale hair as a 34%-of-frame "bubble" and
    # failed an opening that had in fact improved, while lettering fell 48% -> 30%.
    opening_text = max(lettering[:open_n], default=0.0)
    per_second = [
        float(np.mean(art[i : i + max(int(_FPS), 1)]))
        for i in range(0, open_n, max(int(_FPS), 1))
    ]
    metrics: dict[str, Any] = {
        "frames": n,
        "opening_luma_mean": round(float(np.mean(lumas[:open_n])), 1),
        "opening_bubble_frac_max": round(float(max(bubble_fracs[:open_n], default=0.0)), 3),
        "opening_lettering_max": round(opening_text, 3),
        "opening_art_min_second": round(min(per_second), 3) if per_second else 0.0,
        # Composition, validated detector. REPORT-ONLY — see the note on the gates below.
        "lettering_area_median": round(float(np.median(lettering)), 3),
        "lettering_over_30pct_frames_pct": round(
            100.0 * float(np.mean([x > 0.30 for x in lettering])), 1
        ),
        "bare_bubble_frames_pct": round(
            100.0 * float(np.mean([t > 0.15 and a < 0.12 for t, a in zip(lettering, art)])), 1
        ),
        "bubble_over_20pct_frames_pct": round(
            100.0 * float(np.mean([f > 0.20 for f in bubble_fracs])), 1
        ),
        "clipped_text_frames_pct": round(100.0 * float(np.mean(clipped_flags)), 1),
        "dead_width_mean": round(float(np.mean(dead)), 3),
        "dead_over_50pct_frames_pct": round(100.0 * float(np.mean([d > 0.5 for d in dead])), 1),
    }

    metrics.update(measure_audio(video))

    # Shot lengths via scene detection — same detector the reference was profiled with.
    cuts = detect_cuts(video)
    duration = n / _FPS
    shots = shot_lengths(cuts, duration)
    if shots:
        s = sorted(shots)
        metrics["shots"] = len(shots)
        metrics["cuts_per_min"] = round(60 * len(cuts) / max(duration, 1e-6), 2)
        metrics["shot_median_s"] = round(float(np.median(s)), 2)
        metrics["shot_under_1_5s_pct"] = round(100.0 * sum(x < 1.5 for x in s) / len(s), 1)
        metrics["shot_longest_s"] = round(s[-1], 2)
    return metrics


def enforce_render_qa(
    video: Path,
    paths: dict[str, Path],
    config: dict[str, Any],
    extra_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`extra_metrics` carries values only the renderer could measure — chiefly the true
    duck depth, which needs the narration stem the mix consumes and deletes."""
    metrics = measure_video(video)
    metrics.update(extra_metrics or {})
    report = QAReport(stage="render")
    # Which file these numbers describe. A project accumulates dozens of previews; without
    # this, export gates on whichever one last wrote the report.
    try:
        stat = video.stat()
        report.subject = {"video": video.name, "size": stat.st_size,
                          "mtime": round(stat.st_mtime, 3)}
    except OSError:
        pass

    # Opening: SL opened on 19 seconds of speech bubbles on black.
    # Lettering, not "bright blob". Solo Leveling opened on 19 seconds of speech bubbles
    # on black, which is what this must catch; the bright-blob test caught pale artwork
    # instead and inverted the verdict on a real render. Measured openings: 48% before
    # the camera was retargeted, 30% after, and the band sits above both.
    # Also requires the opening to actually SHOW something: every second of the first 15
    # must carry art. Solo Leveling's per-second minimum is 5.4% — it opens on a speech
    # bubble on black — against Frozen Player's 28.3% and the reference's 26.2-45.7%.
    # Judged on LUMA and ART, not on a lettering ceiling. The lettering ceiling was here
    # and it produced a false FAIL on a real render: Solo Leveling's frame at t=14.5s is a
    # blood-spattered stone wall with no lettering whatsoever, and the frame-level detector
    # scored it 0.736. That is the same failure documented in §7 of the audit — texture
    # reads as glyph rows — and gating on it here contradicted the decision to demote
    # `lettering-share` and `bare-bubble` to report-only for exactly that reason.
    #
    # The art floor catches what the ceiling was meant to catch. A bubble on black has
    # almost no art: Solo Leveling's opening measured 5.4% before the camera was retargeted
    # and 26% after, against a 15% floor. Lettering stays in the details as data.
    art_min = metrics.get("opening_art_min_second")
    opening_ok = (
        metrics["opening_luma_mean"] > 16.0
        and (art_min is None or art_min >= _OPENING_ART_FAIL)
    )
    report.add(
        "opening-shot",
        opening_ok,
        f"first {_OPENING_SECONDS:.0f}s: luma {metrics['opening_luma_mean']}, lettering "
        f"{100 * metrics.get('opening_lettering_max', 0.0):.0f}% of frame, "
        f"quietest second carries {100 * (art_min or 0.0):.0f}% art "
        f"(fail under {100 * _OPENING_ART_FAIL:.0f}%), "
        f"largest bubble {metrics['opening_bubble_frac_max']:.0%} of frame — "
        "a recap must not open on a bubble or a black screen",
        **{k: metrics[k] for k in ("opening_luma_mean", "opening_bubble_frac_max")},
    )

    # Bands below are calibrated against the REFERENCE channel's own video run through
    # these exact detectors (10-min sample, 2026-08-26): clipped-text 43.9%, dead-width
    # 0.742. Calibrating against our old defective videos instead produced gates that
    # the reference itself would fail.

    # Bubble dominance: REPORT-ONLY, because the detector does not measure bubbles well
    # enough to gate on. Audited on the FP render (2026-08-27): of the 223 frames it
    # flagged, 64% carry a "bubble" larger than 40% of the frame and 30% larger than 55%
    # — sizes a speech bubble essentially never reaches. The worst two (0.76, 0.73) are
    # hospital bedding and a white wall; a frame containing a real "??" bubble scores
    # 0.00. The dark-pixel text test in `_bubble_stats` was added for exactly this and is
    # not sufficient: pale art with any line work inside it passes, and measuring dark
    # pixels inside the blob instead of its bbox leaves the 0.76 bedding unchanged
    # (verified). So the number is substantially "how much flat pale area is on screen",
    # which is a property of the art, not a defect — the same reasoning that makes
    # `dead-space` report-only.
    #
    # It stays MEASURED because bubble-dominant frames are a genuine concern (the viewer
    # is listening to narration, so a screen of text competes with it) and this is the
    # data a real detector would be built and calibrated against. Gating on it would
    # push the camera to avoid pale artwork — tuning the video against a broken ruler.
    # A detector worth gating on needs bounded size, convexity, AND dark pixels forming
    # small connected strokes (text) rather than any dark pixels at all.
    pct = metrics["bubble_over_20pct_frames_pct"]
    report.add(
        "bubble-dominance",
        True,
        f"{pct}% of frames have a large bright blob covering >20% of the screen "
        f"(reference, same content: {_REF_BUBBLE_PCT}%) — report-only: the detector "
        f"also counts pale artwork, see the note in qa_visual.py",
        pct=pct,
    )

    # Edge-clipped text: REPORT-ONLY. Re-measured 2026-08-28 with the validated lettering
    # detector, the REFERENCE channel slices lettering on 67.5-69.8% of its frames against
    # our 45.3% (FP) and 56.5% (SL) — it is markedly worse at this than we are. Panning a
    # 16:9 window over tall bubbled art clips lettering as a matter of course, so the
    # brief's proposed 10% ceiling is unreachable for anyone. Kept as data; revisit if the
    # crop-constraint work makes a low number achievable.
    pct = metrics["clipped_text_frames_pct"]
    report.add(
        "clipped-text",
        True,
        f"{pct}% of frames slice a text blob at the frame edge (reference, same "
        f"detector: 67.5-69.8% — worse than ours; data only)",
        pct=pct,
    )

    # Lettering on screen, and frames that are lettering with no art beside them.
    # REPORT-ONLY, and this is a measured limitation rather than caution: the geometric
    # detector is validated on PANELS at source resolution, and that validation does not
    # transfer to rendered frames. On real frames a brick wall with no text measures 0.615
    # and a crowd on rock 0.818, against 0.402 for a real "E-RANK HUNTER." bubble —
    # texture makes rows of similar-sized, similar-stroke-width blobs, which is the
    # geometric signature of lettering. Four separating rules were tried against an
    # eye-labelled window set and all four overlap; see reports/render_audit_2026-08-28.md
    # §7. Gating on them would repeat the mistake bubble-dominance already made.
    for gate, key, unit in (
        ("lettering-share", "lettering_over_30pct_frames_pct",
         "% of frames where lettering covers >30% of the screen (reference 5.5-11.0%)"),
        ("bare-bubble", "bare_bubble_frames_pct",
         "% of frames that are lettering with no art beside them (reference 0.0-0.4%)"),
    ):
        if key in metrics:
            report.add(gate, True, f"{metrics[key]}{unit} — data only, detector "
                                   f"not validated at frame resolution", pct=metrics[key])

    # Dead space: REPORT-ONLY. The detector reads low-detail columns, and manhwa art is
    # flat by style — the reference video measures 0.742, worse than anything we ship.
    # The audited defect (blurred pillarbox bars) is structurally gone with the
    # fill-frame camera; this number is kept as data, not a gate.
    dead = metrics["dead_width_mean"]
    report.add(
        "dead-space",
        True,
        f"mean fraction of frame width with no detail: {dead:.0%} (reference: 74%; data only)",
        mean=dead,
    )

    # --- audio ------------------------------------------------------------------------
    #
    # Thresholds from docs/audio-quality-spec.md §6, reconciled against fresh
    # measurements in reports/render_audit_2026-08-28.md. Two of them are WARN today and
    # promote to FAIL when the mastering chain lands: a permanently-red blocking gate
    # trains the operator to reach for --force-past-qa, which is how both audited videos
    # shipped over a failing name-integrity in the first place.

    # Audited true peak was +0.30/+0.35 dBTP — clips on transcode. The spec tightens the
    # ceiling from -0.8 to -1.0; measured -1.35/-1.32, so this costs nothing today and
    # catches a real regression.
    tp = metrics.get("true_peak_dbtp")
    if tp is not None:
        report.add(
            "true-peak",
            tp <= _TRUE_PEAK_MAX_DBTP,
            f"true peak {tp} dBTP (target -1.5, must stay below {_TRUE_PEAK_MAX_DBTP})",
            dbtp=tp, threshold=_TRUE_PEAK_MAX_DBTP,
        )

    # Loudness is judged against the CONFIGURED target, never a hardcoded -16. The spec
    # proposed -16 +/- 1, but -16.4 is the pipeline's UNDERSHOOT: loudnorm in linear mode
    # will not apply gain that would breach TP -1.5, so it lands short of the -14 it aims
    # for. Pinning the gate at the undershoot would fail a future render that fixes it.
    lufs = metrics.get("loudness_lufs")
    if lufs is not None:
        target = float(get_nested(config, "export", "loudness_target", default=-14))
        off = lufs - target
        report.add(
            "audio-loudness",
            True if abs(off) <= 1.0 else ("warn" if -3.0 <= off <= 2.0 else False),
            f"{lufs} LUFS against a {target} target ({off:+.1f} LU)",
            lufs=lufs, target=target, offset=round(off, 2),
        )

    # Is there music under this at all? The bed is chosen by globbing assets/bgm/ and
    # taking the first file, so an empty directory ships a silent bed and no level check
    # can tell that from a quiet mix. Tonality (peak/mean of the quiet-window spectrum)
    # can: music is peaky, room tone is not. Measured 6.26/6.58 against a floor of 5.
    floor = metrics.get("quiet_floor_dbfs")
    tonality = metrics.get("tonality_ratio")
    if floor is not None and tonality is not None:
        ok = floor > _BED_FLOOR_MIN_DBFS and tonality > _BED_TONALITY_MIN
        report.add(
            "audio-music-present",
            ok,
            f"bed floor {floor} dBFS (min {_BED_FLOOR_MIN_DBFS}), tonality {tonality} "
            f"(min {_BED_TONALITY_MIN}) — is there actually music under the narration?",
            floor_dbfs=floor, tonality=tonality,
        )

    # How far the bed drops under the voice. 19.5/19.7 dB today: the bed is so far down it
    # barely registers. WARN until the sidechain chain lands (audio-quality-spec §5).
    # Only the stem-derived value, never the estimate. The estimate overstates the duck
    # by 2-7 dB on long material, and acting on it would mean mixing the bed far too loud
    # while this gate reported it was fine.
    duck = metrics.get("duck_depth_db")
    if duck is not None:
        report.add(
            "audio-duck-depth",
            True if _DUCK_MIN_DB <= duck <= _DUCK_MAX_DB else "warn",
            f"narration sits {duck} dB over the bed (want {_DUCK_MIN_DB}-{_DUCK_MAX_DB}); "
            f"promotes to FAIL when the mastering chain lands",
            duck_depth_db=duck,
        )

    # Loudness range. 2.0-2.3 LU is a flat wall — the delivery has no dynamics at all.
    lra = metrics.get("loudness_range_lu")
    if lra is not None:
        report.add(
            "audio-lra",
            True if _LRA_MIN_LU <= lra <= _LRA_MAX_LU else "warn",
            f"loudness range {lra} LU (want {_LRA_MIN_LU}-{_LRA_MAX_LU}); "
            f"promotes to FAIL when the mastering chain lands",
            lra_lu=lra,
        )

    # --- editing rhythm ----------------------------------------------------------------
    #
    # Measured on the FINISHED file by the same scene detector the reference channel was
    # profiled with, so the bands below are like-for-like. Reference windows, measured
    # 2026-08-28 (reference/mamoru_metrics_2026-08-28.json): median 2.30-2.87s, 21.8-23.6%
    # under 1.5s, 16.2-20.1 cuts/min, longest shot 13.1-16.4s, 13.6-22.2% of runtime in
    # shots over 8s.
    if "shot_median_s" in metrics:
        median = metrics["shot_median_s"]
        report.add(
            "shot-median",
            True if _MEDIAN_MIN_S <= median <= _MEDIAN_MAX_S else "warn",
            f"median shot {median}s (reference {_REF_MEDIAN_S}s; band "
            f"{_MEDIAN_MIN_S}-{_MEDIAN_MAX_S}s)",
            median_s=median,
        )
        accent = metrics["shot_under_1_5s_pct"]
        report.add(
            "shot-accent-share",
            True if accent >= _ACCENT_MIN_PCT else "warn",
            f"{accent}% of shots under 1.5s (reference {_REF_UNDER_1_5_PCT}%, floor "
            f"{_ACCENT_MIN_PCT}%) — short shots are the reference's main rhythm tool",
            pct=accent,
        )
    if "cuts_per_min" in metrics:
        cadence = metrics["cuts_per_min"]
        report.add(
            "shot-cadence",
            True if _CADENCE_MIN <= cadence <= _CADENCE_MAX else "warn",
            f"{cadence} cuts/min (reference 16.2-20.1; band {_CADENCE_MIN}-{_CADENCE_MAX})",
            cuts_per_min=cadence,
        )
    if "shot_longest_s" in metrics:
        longest = metrics["shot_longest_s"]
        report.add(
            "shot-max-duration",
            True if longest <= _SHOT_MAX_WARN_S
            else ("warn" if longest <= _SHOT_MAX_FAIL_S else False),
            f"longest shot {longest}s (reference's own longest is 16.37s; warn over "
            f"{_SHOT_MAX_WARN_S}s, fail over {_SHOT_MAX_FAIL_S}s)",
            longest_s=longest,
        )
    if "shot_over_8s_runtime_pct" in metrics:
        longtail = metrics["shot_over_8s_runtime_pct"]
        report.add(
            "shot-longtail-share",
            True if longtail <= _LONGTAIL_WARN_PCT
            else ("warn" if longtail <= _LONGTAIL_FAIL_PCT else False),
            f"{longtail}% of runtime sits in shots over 8s (reference 13.6-22.2%; warn "
            f"over {_LONGTAIL_WARN_PCT}%, fail over {_LONGTAIL_FAIL_PCT}%)",
            pct=longtail,
        )

    enforce(report, paths["root"], force=qa_forced(config))
    return metrics


def upstream_failures(project_dir: Path, *, include_render: bool = False) -> list[str]:
    """Names of FAILED gates from the stages that CURRENTLY run — the render precondition.

    Both audited videos rendered while script-stage gates were failing; nothing
    connected a red gate to the render that shipped it.

    `include_render` is for EXPORT: the visual and audio gates can only be measured on the
    finished file, so they cannot gate the render that produces it — but they must gate
    the export that publishes it.

    Scoped to `qa.CURRENT_QA_STAGES` rather than every qa.*.json on disk. A project
    directory outlives the pipeline that filled it: reports from deleted stages stay
    there forever, and a glob keeps gating on them. See the note on that constant."""
    from manhwa2vid.qa import CURRENT_QA_STAGES

    failures: list[str] = []
    orphans: list[str] = []
    for qa_file in sorted(project_dir.glob("qa.*.json")):
        stage = qa_file.stem.removeprefix("qa.")
        if stage == "render" and not include_render:
            continue  # the render's own report never blocks the NEXT render
        if stage not in CURRENT_QA_STAGES:
            orphans.append(qa_file.name)
            continue
        try:
            data = json.loads(qa_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for gate in data.get("gates") or []:
            if gate.get("status") == "fail":
                failures.append(f"{stage}:{gate.get('name')}")
    if orphans:
        console.print(
            f"[dim]Ignoring {len(orphans)} QA report(s) from retired stages: "
            f"{', '.join(orphans)} — safe to delete.[/]"
        )
    return failures
