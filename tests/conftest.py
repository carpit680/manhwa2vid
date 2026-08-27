"""Test-wide hermeticity guards.

Two separate hazards, both autouse because both were shipped unnoticed.

RENDER: the pipeline tests drive REAL renders of synthetic panels through the repo's
config.yaml, which enables production-only passes (render QA measures art properties
synthetic fixtures fail by design; upscaling runs a 17MB model). Env wins over config for
these, so the whole suite opts out here instead of mutating the shared config.yaml.

NETWORK: `LLM_PROVIDER=mock` is NOT sufficient. `_resolve_provider_name` takes an explicit
argument first (`llm/provider.py`), and every stage passes one —
`get_llm_provider(get_nested(config, "read", "provider"), config)` resolves the config's
`gemini` and beats the env var. Measured 2026-08-26: `test_freeform_pipeline_mock` took
47s and passed by calling the real Gemini API, which is also why nobody noticed that the
mock could not run the freeform path at all. Blanking the KEYS is what actually forces
the offline path, because every real provider falls back to the mock without one.
"""

from __future__ import annotations

import pytest

_API_KEY_VARS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "OPENAI_API_KEY",
    "MISTRAL_API_KEY",
    "ANTHROPIC_API_KEY",
)


@pytest.fixture(autouse=True)
def _hermetic_render(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MANHWA2VID_RENDER_QA", "0")
    monkeypatch.setenv("MANHWA2VID_UPSCALE", "0")


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("TTS_PROVIDER", "mock")
    for var in _API_KEY_VARS:
        monkeypatch.setenv(var, "")
