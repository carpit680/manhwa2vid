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
# -60, not -40: re-derived 2026-08-30 against the competitor corpus. A bed-less render
# measures -64.7 dBFS and the quietest real field video -57.4, so -60 separates genuine
# absence from a legitimately quiet bed — which is all this gate can honestly claim. The
# old -40 failed nine of twelve field videos, Mamoru's 5.2M among them.
_BED_FLOOR_MIN_DBFS = -60.0
# Reported only. An absent bed scores 2.87 and the quietest field video 2.71 — tonality
# cannot distinguish silence from music, so gating on it fails real videos and catches
# nothing. Kept in the report because the number is still worth seeing.
_BED_TONALITY_MIN = 5.0
# 12-15 came from docs/audio-quality-spec.md §6 and was never measured against the
# reference. Two things moved it on 2026-08-29: the user asked for a quieter bed after
# hearing the shipped renders, and a like-for-like measurement (same window-RMS
# estimator on both mixes) put the reference's own bed HOTTER than ours, so the band was
# not describing the target either. `bgm_gain_db` went -30 -> -36 by ear; this band
# widens to admit that choice and still catch the failures worth catching — a bed so
# loud it competes with the voice (under 10) or so quiet it may as well be absent (over
# 24, which is where the pre-mastering renders sat at 19.5 and sounded empty).
# Voice-to-bed separation, measured on the corpus with the estimate metric (the only one
# computable without a narration stem): 13.0-35.7 dB across twelve competitor videos,
# median 21.9. The previous 10-24 was reasoned, not measured, and the 12-15 before that
# came from the audio spec. Ours measures 26.2 — inside the field.
_SEPARATION_MIN_DB, _SEPARATION_MAX_DB = 13.0, 36.0
# Measured off the reference channel's OWN audio, 2026-08-28: the full 5h17m track of
# the Mamoru Frozen Player video (reference/frozen_player/mamoru_fp_audio.wav, pulled
# audio-only from the same video id the visual profile used) measures LRA 2.50 LU by
# loudnorm and 2.6 LU by ebur128 — the two meters agree. The spec's 5-9 band was an
# unsourced proposals-table row that no single-voice TTS-plus-bed chain can reach: raw
# Kokoro narration measures 2.0 LU before ANY processing, and loudnorm linear=true
# cannot create range. The channel this pipeline imitates delivers a flat wall on
# purpose. Floor 1.5 catches the real failure this gate can see — a dynamic-mode
# loudnorm fallback or a runaway compressor crushing what little range exists; ceiling
# 4.5 catches dynamics this format never legitimately produces.
#
# Same measurement, for the record: reference integrated -17.5 LUFS (we target -14,
# which is the platform normalization point — theirs plays quieter, not better) and
# true peak -0.77 dBTP, which would FAIL our own -1.0 gate. Ours stays stricter.
_LRA_MIN_LU, _LRA_MAX_LU = 1.5, 4.5

# Integrated loudness, re-derived 2026-08-30 from the 12-video competitor corpus measured
# with our own detectors (reference/corpus/corpus_metrics.json, mid-sections):
#
#     -25.89  vault_med       3 K views      <- quietest, and the least-watched
#     -21.47  tobs_top      1.6 M
#     -21.43  tobs_med
#     -21.01  mamoru_med
#     -20.99  zone_med
#     -19.87  zone_top      1.2 M            median -19.81
#     -19.75  mangaking_top
#     -19.41  vault_top
#     -19.28  mamoru_top    5.2 M
#     -17.27  outpost_med
#     -15.00  isekai_top
#     -14.72  outpost_top   6.2 M            <- loudest, and the most-watched
#
# The old gate judged against `export.loudness_target` -14.0 +/- 1.0 and warned on our
# own -15.37, which is louder than ten of twelve field videos and sits beside the
# corpus's biggest hit. It was measuring distance from a platform constant, not whether
# the mix is wrong, and the field plainly does not punish loud.
#
# We keep PRODUCING at -14.0 (the platform normalization point; loudnorm undershoots to
# about -15.4 because linear mode will not breach TP -1.5). The gate only asks whether
# the result is somewhere a real recap channel lives:
#   ceiling -13.0 — above both the platform point and every video in the field, so the
#                   limiter is doing work the mix should not need;
#   floor   -26.0 — quieter than the entire field, i.e. inaudible on a phone.
# Outside that but not absurd is a warn; beyond the fail bounds the chain is broken
# (a silent stem, a missing loudnorm pass) rather than mis-tuned.
_LUFS_FIELD_MIN, _LUFS_FIELD_MAX = -26.0, -13.0
_LUFS_FAIL_MIN, _LUFS_FAIL_MAX = -30.0, -10.0

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

    # Loudness is judged against the FIELD, not against distance from the platform
    # constant we produce at — see _LUFS_FIELD_MIN above. The old form warned on -15.37,
    # which is louder than ten of twelve competitor videos and a third of a LU from the
    # corpus's most-watched one. Where we AIM stays `export.loudness_target`.
    lufs = metrics.get("loudness_lufs")
    if lufs is not None:
        target = float(get_nested(config, "export", "loudness_target", default=-14))
        if _LUFS_FIELD_MIN <= lufs <= _LUFS_FIELD_MAX:
            verdict: Any = True
        elif _LUFS_FAIL_MIN <= lufs <= _LUFS_FAIL_MAX:
            verdict = "warn"
        else:
            verdict = False
        report.add(
            "audio-loudness",
            verdict,
            f"{lufs} LUFS (field {_LUFS_FIELD_MIN}..{_LUFS_FIELD_MAX}, median -19.8; "
            f"produced against a {target} target)",
            lufs=lufs, target=target,
            field_min=_LUFS_FIELD_MIN, field_max=_LUFS_FIELD_MAX,
        )

    # Is there music under this at all? The bed is globbed from assets/bgm/, so an empty
    # directory ships a silent bed that no level check distinguishes from a quiet mix.
    #
    # Re-derived 2026-08-30 against the competitor corpus and against a deliberately
    # bed-less render, because the old -40 dBFS floor failed NINE of twelve field videos
    # — including Mamoru's 5.2M (-44.2) and Tobs' 1.6M (-42.2). It was codifying our own
    # mix, not the format.
    #
    #     no bed at all      -64.7 dBFS      tonality 2.87
    #     field minimum      -57.4           tonality 2.71
    #     field median       -42.2           tonality 5.51
    #
    # Tonality is REPORTED, not gated: an absent bed scores 2.87 and the quietest real
    # field video scores 2.71, so it cannot tell silence from music and the old ">5"
    # would have failed three more field videos. The claim it was added on ("music is
    # peaky, room tone is not") was only ever checked against our own renders.
    floor = metrics.get("quiet_floor_dbfs")
    tonality = metrics.get("tonality_ratio")
    if floor is not None:
        report.add(
            "audio-music-present",
            floor > _BED_FLOOR_MIN_DBFS,
            f"bed floor {floor} dBFS (min {_BED_FLOOR_MIN_DBFS}; a bed-less render "
            f"measures -64.7, the quietest field video -57.4) — is there music under "
            f"the narration at all?",
            floor_dbfs=floor, tonality=tonality,
        )

    # How far the bed sits under the voice. Renamed from audio-duck-depth on 2026-08-30:
    # sidechain ducking is off by default (it pumped once kokoro_trim_ms shortened the
    # inter-sentence gaps below its release), so "duck depth" no longer describes the
    # chain. The quantity that matters either way is the SEPARATION between voice and
    # bed, which a constant bed has just as much as a ducked one.
    #
    # Judged on the ESTIMATE, not the stem value, because the estimate is the only one
    # computable for the field: competitors ship no narration stem. Its bias is real —
    # it overstates by 2-7 dB on long material — but it is applied identically to both
    # sides, which is the same like-for-like argument the composition gates use. The
    # stem value stays in the report as the more accurate number.
    #
    # Band from the corpus (mid sections): 13.0-35.7 dB, median 21.9. Ours measures
    # 26.2 — inside it. See reports/field_measurement_2026-08-29.md.
    separation = metrics.get("duck_depth_estimate_db")
    if separation is not None:
        report.add(
            "audio-bed-separation",
            True if _SEPARATION_MIN_DB <= separation <= _SEPARATION_MAX_DB else "warn",
            f"narration sits {separation} dB over the bed "
            f"(field {_SEPARATION_MIN_DB}-{_SEPARATION_MAX_DB}, median 21.9)",
            bed_separation_db=separation,
            duck_depth_stem_db=metrics.get("duck_depth_db"),
        )

    # Loudness range, judged against the reference channel's measured 2.5-2.6 LU — a
    # flat delivery is this format's actual sound, and the failure worth catching is
    # range being CRUSHED (a dynamic-mode loudnorm fallback), not range being small.
    # `stem_lra_lu` / `premaster_lra_lu` say where any loss happened: the stem is what
    # the synthesizer produced, premaster is what the chain handed loudnorm.
    lra = metrics.get("loudness_range_lu")
    if lra is not None:
        provenance = {
            k: v for k, v in (
                ("stem_lra_lu", metrics.get("stem_lra_lu")),
                ("premaster_lra_lu", metrics.get("premaster_lra_lu")),
            ) if v is not None
        }
        report.add(
            "audio-lra",
            _LRA_MIN_LU <= lra <= _LRA_MAX_LU,
            f"loudness range {lra} LU (reference-derived band "
            f"{_LRA_MIN_LU}-{_LRA_MAX_LU}; the channel itself measures 2.5)",
            lra_lu=lra,
            **provenance,
        )
    if metrics.get("loudnorm_fallback"):
        report.add(
            "audio-two-pass",
            "warn",
            "loudnorm measurement pass failed to parse — the mix was normalized in "
            "single-pass DYNAMIC mode, which compresses loudness range; if audio-lra "
            "failed, this is why",
            fallback=True,
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
