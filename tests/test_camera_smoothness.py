"""The camera stuttered on every zoom, in every video, for as long as there were videos.

Reported from watching: "while zooming in or out, the frames are jiggling. They have
always been jiggling in all videos."

Both motion paths built an integer crop box out of a float camera path:

    crop = panel.crop((int(left), int(top), int(left + cw), int(top + ch)))
    frames.append(crop.resize((width, height), LANCZOS))

which quantises TWICE. The origin snaps (100.2, 100.7, 101.1 -> 100, 100, 101) instead
of gliding, and the box WIDTH flips between cw and cw+1 as the fractional parts cross,
so the scale factor changes from one frame to the next. `resize(box=...)` takes float
coordinates and does crop+scale in a single resampling step, so neither happens.

Measured on a real panel with a perfectly LINEAR pan, which by construction should have
zero jerk — phase-correlated frame-to-frame displacement, confidence 0.94/0.99:

    int() crop   velocity std 0.7042   jerk RMS 1.1158
    float box    velocity std 0.0116   jerk RMS 0.0050

These tests use an intensity centroid rather than phase correlation so they carry no
OpenCV dependency, but they measure the same thing: a smooth camera path must produce a
smooth centroid path.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from manhwa2vid.video.effects import (
    render_fill_frame_frames,
    render_vertical_scroll_frames,
)


@pytest.fixture
def smooth_panel(tmp_path):
    """Non-periodic texture. Periodic content aliases against a moving crop window and
    makes any motion measurement meaningless — a striped panel measured phase-correlation
    jerk 12.4 where a smooth one measured 0.75."""
    rng = np.random.default_rng(0)
    a = rng.random((1400, 900))
    # cheap separable blur, so the fixture carries no OpenCV dependency
    k = np.ones(9) / 9.0
    a = np.apply_along_axis(lambda r: np.convolve(r, k, "same"), 1, a)
    a = np.apply_along_axis(lambda c: np.convolve(c, k, "same"), 0, a)
    arr = np.stack([(a * 255).astype(np.uint8)] * 3, axis=-1)
    p = tmp_path / "smooth.png"
    Image.fromarray(arr, mode="RGB").save(p)
    return p


@pytest.fixture
def textured_panel(tmp_path):
    """Fine vertical stripes: the centroid of a stripe field tracks camera movement
    precisely, and sub-pixel shifts show up as intermediate centroid values."""
    w, h = 900, 1400
    x = np.arange(w)
    col = (127 + 120 * np.sin(x / 3.0)).astype(np.uint8)
    arr = np.repeat(col[None, :], h, axis=0)
    arr = np.stack([arr, arr, arr], axis=-1)
    arr[::37, :, :] = 20                      # horizontal ticks for the scroll case
    p = tmp_path / "panel.png"
    Image.fromarray(arr, mode="RGB").save(p)
    return p


def _centroids(frames, axis):
    """Intensity centroid along one axis, per frame."""
    out = []
    for f in frames:
        a = np.asarray(f.convert("L"), dtype=np.float64)
        prof = a.mean(axis=0 if axis == "x" else 1)
        idx = np.arange(prof.size)
        prof = prof - prof.min()
        out.append(float((prof * idx).sum() / max(prof.sum(), 1e-9)))
    return np.array(out)


def _jerk_rms(series):
    """RMS of the second difference — how much the velocity changes frame to frame."""
    return float(np.sqrt((np.diff(series, n=2) ** 2).mean()))


def test_the_fill_frame_camera_moves_smoothly(textured_panel):
    frames = render_fill_frame_frames(
        textured_panel, 480, 270, 48, {}, seed="smoothness"
    )
    assert len(frames) == 48
    jerk = _jerk_rms(_centroids(frames, "x"))
    # The int()-crop version measured jerk RMS ~1.1 px against a linear path. Anything
    # near a pixel is the quantisation staircase coming back.
    assert jerk < 0.35, f"camera is stuttering: jerk RMS {jerk:.3f}"


def test_a_slow_camera_never_freezes_between_frames(smooth_panel):
    """The sharpest form of the defect, and the one with no measurement artefact.

    At 0.3 px/frame an integer crop box does not change for three frames at a time, so
    the rendered frames are byte-IDENTICAL and the camera is frozen, then snaps a whole
    pixel. Measured on this exact path: int() crop produced 27 identical consecutive
    frames out of 39; float box produces 0.

    A jerk threshold cannot be used on the scroll path — it eases with `cosine_ease`, so
    genuine acceleration is expected — and phase correlation misreads periodic texture
    (a striped panel measured jerk 12.4 against a smooth one's 0.75). Duplicate frames
    are unambiguous.
    """
    frames = render_vertical_scroll_frames(smooth_panel, 480, 270, 48, {})
    arrays = [np.asarray(f.convert("L"), dtype=np.int16) for f in frames]
    dupes = sum(1 for a, b in zip(arrays, arrays[1:]) if np.array_equal(a, b))
    assert dupes == 0, f"{dupes} frozen frame pairs — the camera is quantised"


def test_the_fill_frame_camera_never_freezes(smooth_panel):
    frames = render_fill_frame_frames(smooth_panel, 480, 270, 48, {}, seed="slow")
    arrays = [np.asarray(f.convert("L"), dtype=np.int16) for f in frames]
    dupes = sum(1 for a, b in zip(arrays, arrays[1:]) if np.array_equal(a, b))
    # A deliberately STATIC shot is a legitimate camera choice, so allow a still shot to
    # be still; what must not happen is a moving shot freezing intermittently.
    moving = not np.array_equal(arrays[0], arrays[-1])
    if moving:
        assert dupes <= 2, f"{dupes} frozen frame pairs in a moving shot"


def test_consecutive_frames_actually_differ(textured_panel):
    """A 'smooth' camera that never moves would pass a jerk test trivially."""
    frames = render_fill_frame_frames(
        textured_panel, 480, 270, 48, {}, seed="smoothness"
    )
    c = _centroids(frames, "x")
    assert abs(c[-1] - c[0]) > 0.5 or _frames_change(frames), "the camera never moved"


def _frames_change(frames):
    a = np.asarray(frames[0].convert("L"), dtype=np.float64)
    b = np.asarray(frames[-1].convert("L"), dtype=np.float64)
    return float(np.abs(a - b).mean()) > 1.0


def test_frames_are_the_requested_size(textured_panel):
    for f in render_fill_frame_frames(textured_panel, 480, 270, 12, {}, seed="s"):
        assert f.size == (480, 270)
    for f in render_vertical_scroll_frames(textured_panel, 480, 270, 12, {}):
        assert f.size == (480, 270)


def test_the_letterbox_push_in_never_freezes(tmp_path):
    """Second round of the same defect, reported from watching: "earlier in the video
    the pans and zoom ins are smooth but later they become jiggly again." The first
    sub-pixel fix reached the fill and scroll cameras but not the LETTERBOX one — the
    default for tall panels, which dominate later in the video while the opening
    prefers the fill camera. Its push-in resized the panel to int(round(w*scale)) per
    frame and centred at (width-new_w)//2: whole-pixel size steps plus parity hops.

    Same criterion as the others: a moving camera must not render byte-identical
    consecutive frames."""
    from manhwa2vid.video.effects import render_letterbox_frames

    rng = np.random.default_rng(4)
    a = rng.random((1000, 800))
    k = np.ones(9) / 9.0
    a = np.apply_along_axis(lambda r: np.convolve(r, k, "same"), 1, a)
    arr = np.stack([(a * 255).astype(np.uint8)] * 3, axis=-1)
    p = tmp_path / "tall.png"
    Image.fromarray(arr, mode="RGB").save(p)

    frames = render_letterbox_frames(p, 480, 270, 48, {})
    arrays = [np.asarray(f.convert("L"), dtype=np.int16) for f in frames]
    dupes = sum(1 for x, y in zip(arrays, arrays[1:]) if np.array_equal(x, y))
    assert dupes == 0, f"{dupes} frozen frame pairs — the letterbox push-in is quantised"
    assert not np.array_equal(arrays[0], arrays[-1]), "the push-in never moved"
