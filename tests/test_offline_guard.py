"""The suite must be offline — and `LLM_PROVIDER=mock` alone does not achieve it.

Measured 2026-08-26: `test_freeform_pipeline_mock` ran for 47 seconds against the REAL
Gemini API and passed, because `_resolve_provider_name` honours an explicit argument
before the env var and every stage passes one from config (`read.provider: gemini`).
The test was the pipeline's main end-to-end safety net, it had never once exercised the
mock, and it was concealing that `MockLLMProvider.describe_labeled_panels` could not
accept `max_width` — i.e. the story-first path could not run offline at all.

These tests pin the guard itself, so a future config key or a new stage cannot quietly
put the suite back on the network.
"""

from __future__ import annotations

import pytest

from manhwa2vid.llm.provider import MockLLMProvider, get_llm_provider

# Every provider value a stage passes explicitly today. `ollama` is deliberately absent:
# it is a LOCAL server with no API key, so blanking keys cannot gate it — see
# test_ollama_would_escape_the_guard below, which is why no stage may select it.
_STAGE_PROVIDERS = ["gemini", "groq", "mistral", "openai", None]


@pytest.mark.parametrize("explicit", _STAGE_PROVIDERS)
def test_every_stage_provider_resolves_to_the_mock(explicit):
    """A stage passing its configured provider by name must still land on the mock.

    This is the exact call shape used by read/freeform/audit/align/match:
        get_llm_provider(get_nested(config, "<stage>", "provider"), config)
    """
    provider = get_llm_provider(explicit, {"llm": {"provider": "gemini"}})
    assert isinstance(provider, MockLLMProvider), (
        f"stage provider {explicit!r} escaped the offline guard — the suite would "
        "make real API calls"
    )


def test_ollama_would_escape_the_guard_so_no_stage_may_select_it():
    """The offline guard works by blanking API keys — every hosted provider falls back to
    the mock without one. Ollama has no key: it talks to a local server, so it is the one
    provider that can slip past. Rather than pretend otherwise, assert that nothing in
    config.yaml routes a stage to it.
    """
    import yaml

    from manhwa2vid.config import find_repo_root

    config = yaml.safe_load((find_repo_root() / "config.yaml").read_text())

    def providers(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "provider" and isinstance(value, str):
                    yield value
                else:
                    yield from providers(value)

    assert "ollama" not in set(providers(config)), (
        "a stage is configured for ollama, which the offline test guard cannot block"
    )


def test_api_keys_are_blanked():
    """The keys are what force the fallback; if one leaks in, a real provider is built."""
    import os

    for var in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "MISTRAL_API_KEY"):
        assert not os.getenv(var), f"{var} is set inside the test session"


def test_mock_accepts_the_full_vision_signature(tmp_path):
    """The story-first path passes `max_width` to every labelled-vision call. The mock
    omitted the keyword, so read/align/audit raised TypeError the moment they actually
    used it — invisible while the tests were hitting a real provider."""
    from PIL import Image

    page = tmp_path / "p0001.png"
    Image.new("RGB", (32, 32)).save(page)
    mock = MockLLMProvider()

    # must not raise
    mock.describe_labeled_panels([("[page p0001]", page)], "prompt", max_width=1024)
    mock.describe_labeled_panels_text([("[page p0001]", page)], "sys", "user", max_width=1024)
    mock.describe_panels([page], "prompt", max_width=1024)


def test_base_class_forwards_max_width_to_the_encoder():
    """The base `describe_labeled_panels` fallback used to accept `max_width` and drop
    it, so a provider relying on the fallback encoded a webtoon page under the
    longest-side cap — the 800x10060 page becomes a 40px sliver (see vision_utils)."""
    import inspect

    from manhwa2vid.llm.provider import LLMProvider

    source = inspect.getsource(LLMProvider.describe_labeled_panels)
    assert "max_width=max_width" in source, "base fallback drops max_width again"
    assert "max_width" in inspect.signature(LLMProvider.describe_panels).parameters
