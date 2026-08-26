"""Test-wide hermeticity guards.

The pipeline tests drive REAL renders of synthetic panels through the repo's
config.yaml, which enables production-only passes (render QA measures art
properties synthetic fixtures fail by design; upscaling runs a 17MB model).
Env wins over config for these, same as SCRIPT_ARCHITECTURE, so the whole
suite opts out here instead of mutating the shared config.yaml.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _hermetic_render(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MANHWA2VID_RENDER_QA", "0")
    monkeypatch.setenv("MANHWA2VID_UPSCALE", "0")
