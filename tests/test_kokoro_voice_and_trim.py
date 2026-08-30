"""Voice blending and silence trimming — both chosen by ear, both pinned here.

The trim is the load-bearing one. Synthesis runs ONE call per sentence so every sidecar
duration is measured rather than estimated, and the cost of that choice is Kokoro's own
per-sentence lead/trail silence landing at every boundary: ~250 ms + ~500 ms each,
4.6 s of dead air in a six-sentence passage against the 60 ms join gap we add. Trimming
raises words-per-minute without touching articulation.

It must happen BEFORE the sidecar is written. The shot planner joins the shot list to
those durations, so a trim applied after measurement would desynchronise picture from
sound — silently, because both files would still be internally consistent.
"""

from __future__ import annotations

import numpy as np
import pytest

from manhwa2vid.tts.kokoro import SAMPLE_RATE, _resolve_voice, _trim_silence


def _speech(lead_ms: float, body_ms: float, trail_ms: float, amp: float = 0.5):
    n = lambda ms: int(SAMPLE_RATE * ms / 1000.0)  # noqa: E731
    body = np.full(n(body_ms), amp, dtype="float32")
    return np.concatenate([
        np.zeros(n(lead_ms), dtype="float32"), body, np.zeros(n(trail_ms), dtype="float32")
    ])


class TestTrimSilence:
    def test_the_observed_case(self):
        """Kokoro's measured shape: 250 ms lead, 500 ms trail."""
        a = _speech(250, 1000, 500)
        out = _trim_silence(a, 150)
        # 150 ms kept each side, so ~1300 ms total instead of 1750.
        assert out.size == pytest.approx(SAMPLE_RATE * 1.30, rel=0.02)

    def test_zero_disables(self):
        a = _speech(250, 1000, 500)
        assert _trim_silence(a, 0).size == a.size

    def test_never_eats_speech(self):
        """The body must survive intact — this is audio, a bug here is audible."""
        a = _speech(300, 800, 400, amp=0.5)
        out = _trim_silence(a, 50)
        loud_in = int((np.abs(a) > 0.25).sum())
        loud_out = int((np.abs(out) > 0.25).sum())
        assert loud_out == loud_in

    def test_a_quiet_sentence_is_not_mistaken_for_silence(self):
        """The threshold is relative to the segment's OWN peak, so a softly-spoken
        line is trimmed like any other rather than erased."""
        a = _speech(250, 1000, 500, amp=0.02)
        out = _trim_silence(a, 150)
        assert out.size == pytest.approx(SAMPLE_RATE * 1.30, rel=0.02)

    def test_all_silence_is_returned_untouched(self):
        a = np.zeros(int(SAMPLE_RATE * 0.5), dtype="float32")
        assert _trim_silence(a, 150).size == a.size

    def test_empty_is_safe(self):
        assert _trim_silence(np.zeros(0, dtype="float32"), 150).size == 0

    def test_keeping_more_than_exists_does_not_pad(self):
        a = _speech(40, 500, 40)
        assert _trim_silence(a, 150).size == a.size


class _FakePipeline:
    """load_single_voice returns a recognisable constant vector per name."""

    SHAPE = (510, 1, 256)

    def load_single_voice(self, name: str):
        return np.full(self.SHAPE, {"af_heart": 1.0, "af_nicole": 3.0}[name], dtype="float32")


class TestResolveVoice:
    def test_a_bare_name_passes_through_unchanged(self):
        """Presets must keep working — the blend syntax is additive."""
        assert _resolve_voice(_FakePipeline(), "af_heart") == "af_heart"

    def test_weighted_blend(self):
        v = _resolve_voice(_FakePipeline(), "af_heart:0.65,af_nicole:0.35")
        assert v.shape == _FakePipeline.SHAPE
        assert float(v.flat[0]) == pytest.approx(0.65 * 1.0 + 0.35 * 3.0)

    def test_weights_are_normalised(self):
        """65/35 and 0.65/0.35 must mean the same thing."""
        a = _resolve_voice(_FakePipeline(), "af_heart:65,af_nicole:35")
        b = _resolve_voice(_FakePipeline(), "af_heart:0.65,af_nicole:0.35")
        assert float(a.flat[0]) == pytest.approx(float(b.flat[0]))

    def test_the_shipped_config_value_parses(self):
        import yaml

        from manhwa2vid.config import get_nested

        cfg = yaml.safe_load(open("config.yaml"))
        spec = str(get_nested(cfg, "tts", "kokoro_voice", default=""))
        v = _resolve_voice(_FakePipeline(), spec)
        assert not isinstance(v, str), "shipped config should be a blend"
        assert v.shape == _FakePipeline.SHAPE


class TestDefaultsMatchTheShippedConfig:
    """CLAUDE.md's standing trap: "Config defaults must match config.yaml. Keys are read
    where used, so a default that differs from the file changes behaviour silently the
    moment the key is absent."

    `kokoro_trim_ms` was read with `default=0.0` against 150 in the file, so a config
    missing the key silently restored the untrimmed read that `kokoro_speed: 1.30` was
    calibrated against — a ~24 wpm swing with nothing to show for it. These are the
    audio-shaping keys where an absent key changes what the listener hears.
    """

    import pytest as _pytest

    @_pytest.mark.parametrize("key", ["kokoro_trim_ms", "kokoro_max_pause_ms"])
    def test_the_code_default_equals_the_file(self, key):
        import inspect
        import re

        import yaml

        from manhwa2vid.tts import kokoro

        shipped = yaml.safe_load(open("config.yaml"))["tts"][key]
        src = inspect.getsource(kokoro.KokoroTTSProvider.synthesize)
        found = re.search(rf'"{key}", default=([0-9.]+)', src)
        assert found, f"{key} is not read in synthesize() — did the call site move?"
        assert float(found.group(1)) == float(shipped), (
            f"{key}: code default {found.group(1)} != config.yaml {shipped}"
        )
