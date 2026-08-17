"""LLM provider selection tests."""

from __future__ import annotations

import pytest

from manhwa2vid.llm.provider import (
    GeminiProvider,
    GroqProvider,
    MistralProvider,
    MockLLMProvider,
    OpenAIProvider,
    get_llm_provider,
)


@pytest.fixture(autouse=True)
def _clear_provider_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real key in the developer's .env must not leak into provider-selection tests.

    Set to empty rather than delete: load_config() re-runs load_dotenv(), which would
    restore a deleted var from .env but never overrides an existing (even empty) one.
    """
    for env in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.setenv(env, "")


def test_get_llm_provider_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    provider = get_llm_provider()
    assert isinstance(provider, MockLLMProvider)


def test_get_llm_provider_groq_without_key_falls_back_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "")
    provider = get_llm_provider()
    assert isinstance(provider, MockLLMProvider)


def test_get_llm_provider_groq_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")
    config = {
        "llm": {
            "provider": "groq",
            "groq": {
                "text_model": "llama-3.3-70b-versatile",
                "vision_model": "meta-llama/llama-4-scout-17b-16e-instruct",
            },
        }
    }
    provider = get_llm_provider(config=config)
    assert isinstance(provider, GroqProvider)
    assert provider.model == "llama-3.3-70b-versatile"
    assert provider.vision_model == "meta-llama/llama-4-scout-17b-16e-instruct"


def test_get_llm_provider_gemini_without_key_falls_back_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    provider = get_llm_provider()
    assert isinstance(provider, MockLLMProvider)


def test_get_llm_provider_gemini_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza_test_key")
    config = {"llm": {"gemini": {"text_model": "gemini-2.5-flash", "vision_model": "gemini-2.5-flash-lite"}}}
    provider = get_llm_provider(config=config)
    assert isinstance(provider, GeminiProvider)
    assert provider.model == "gemini-2.5-flash"
    assert provider.vision_model == "gemini-2.5-flash-lite"


def test_get_llm_provider_gemini_accepts_google_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza_test_key")
    assert isinstance(get_llm_provider(), GeminiProvider)


def test_get_llm_provider_mistral_without_key_falls_back_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mistral")
    provider = get_llm_provider()
    assert isinstance(provider, MockLLMProvider)


def test_get_llm_provider_mistral_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mistral")
    monkeypatch.setenv("MISTRAL_API_KEY", "mi_test_key")
    provider = get_llm_provider(config={})
    assert isinstance(provider, MistralProvider)
    assert provider.model == "mistral-large-latest"


def test_env_sets_model_when_config_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model precedence is config.yaml > env var > built-in default (same as Groq)."""
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza_test_key")
    monkeypatch.setenv("GEMINI_VISION_MODEL", "gemini-3-pro")

    from_env = get_llm_provider(config={"llm": {"gemini": {}}})
    assert from_env.vision_model == "gemini-3-pro"

    from_config = get_llm_provider(config={"llm": {"gemini": {"vision_model": "gemini-2.5-flash-lite"}}})
    assert from_config.vision_model == "gemini-2.5-flash-lite"


def test_thinking_models_get_reasoning_override() -> None:
    """qwen burns its whole budget on <think> unless reasoning is disabled."""
    groq = GroqProvider.__new__(GroqProvider)
    assert groq._extra_body("qwen/qwen3.6-27b") == {"reasoning_effort": "none"}
    assert groq._extra_body("gemini-2.5-flash") is None


def test_get_llm_provider_openai_without_key_falls_back_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", "")
    provider = get_llm_provider()
    assert isinstance(provider, MockLLMProvider)


def test_get_llm_provider_openai_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    config = {"script": {"model": "gpt-4o-mini"}, "scene": {"model": "gpt-4o"}}
    provider = get_llm_provider(config=config)
    assert isinstance(provider, OpenAIProvider)
    assert provider.model == "gpt-4o-mini"
    assert provider.vision_model == "gpt-4o"


def test_extract_json_object_stops_at_first_object() -> None:
    """Two concatenated objects both start with '{' and end with '}'.

    The old first-brace-to-last-brace slice returned the whole string, and the caller's
    json.loads() died with 'Extra data' mid-run (the ch1 synopsis stage, 2026-08-17).
    """
    import json as _json

    from manhwa2vid.llm.provider import _extract_json_object

    raw = '{"logline": "first"}\n{"logline": "second"}'
    assert _json.loads(_extract_json_object(raw)) == {"logline": "first"}


def test_extract_json_object_ignores_trailing_prose() -> None:
    import json as _json

    from manhwa2vid.llm.provider import _extract_json_object

    raw = 'Here you go:\n{"beats": [{"beat_id": 1}]}\nLet me know if you want changes.'
    assert _json.loads(_extract_json_object(raw)) == {"beats": [{"beat_id": 1}]}


def test_extract_json_object_strips_markdown_fence() -> None:
    import json as _json

    from manhwa2vid.llm.provider import _extract_json_object

    raw = '```json\n{"a": 1}\n```'
    assert _json.loads(_extract_json_object(raw)) == {"a": 1}


def test_extract_json_object_ignores_braces_inside_strings() -> None:
    import json as _json

    from manhwa2vid.llm.provider import _extract_json_object

    raw = '{"narration": "he mutters \\"} not yet\\" and turns"} trailing'
    assert _json.loads(_extract_json_object(raw))["narration"].endswith("and turns")


def test_extract_json_object_truncated_falls_back_to_balance_scan() -> None:
    """A truncated generation still yields the best-effort object, never raw prose."""
    from manhwa2vid.llm.provider import _extract_json_object

    raw = 'preamble {"beats": [{"beat_id": 1, "narration": "unterminated'
    out = _extract_json_object(raw)
    assert out.startswith("{")
    assert "preamble" not in out


def test_extract_json_object_repairs_stray_inner_quotes() -> None:
    """Unescaped quotes inside narration killed every rewrite attempt on ch1.

    'Rewrite failed: Expecting , delimiter' appeared on 2-3 beats of every run, silently
    keeping the flagged narration instead of the repaired one.
    """
    import json as _json

    from manhwa2vid.llm.provider import _extract_json_object

    raw = '{"narration": "he says "no" and walks out", "beat_id": 3}'
    data = _json.loads(_extract_json_object(raw))
    assert data["beat_id"] == 3
    assert "no" in data["narration"]


def test_extract_json_object_preserves_already_escaped_quotes() -> None:
    import json as _json

    from manhwa2vid.llm.provider import _extract_json_object

    raw = '{"narration": "he mutters \\"fine\\" and leaves"}'
    assert _json.loads(_extract_json_object(raw))["narration"] == 'he mutters "fine" and leaves'


@pytest.mark.parametrize(
    "name,raw,expect_key",
    [
        ("literal newline in string", '{\n "narration": "line one\nline two"\n}', "narration"),
        ("trailing comma", '{\n "narration": "text",\n}', "narration"),
        ("single-quoted keys", "{'narration': 'text'}", "narration"),
        ("bad backslash escape", '{"narration": "path C:\\Users end"}', "narration"),
        ("stray inner quote", '{"narration": "he says "no" and leaves"}', "narration"),
    ],
)
def test_extract_json_object_repairs_real_generation_failures(name, raw, expect_key) -> None:
    """Every one of these shipped from a live model and killed a stage mid-run.

    A hand-rolled repair cannot cover them all — an unescaped quote before a comma is
    indistinguishable from end-of-string — so the extractor delegates to json_repair.
    """
    import json as _json

    from manhwa2vid.llm.provider import _extract_json_object

    data = _json.loads(_extract_json_object(raw))
    assert expect_key in data, name


def test_rewrite_beat_takes_plain_prose_not_json() -> None:
    """rewrite_beat's payload is one string; the JSON envelope only added a failure mode."""
    from manhwa2vid.models import CharacterProfile, CharacterTier, ScriptBeat, SeriesBible
    from manhwa2vid.script.lint import rewrite_beat

    class _ProseLLM:
        def complete(self, system, user, *, json_mode=False):
            assert not json_mode, "rewrite must not request JSON mode"
            return "He walks into the gate and the light swallows him."

        def describe_panels(self, image_paths, prompt):
            return "{}"

    bible = SeriesBible(series_slug="s", title="S", protagonist_id="char_mc")
    bible.characters["char_mc"] = CharacterProfile(
        id="char_mc", canonical_name="Sung Jin-Woo", tier=CharacterTier.MAIN
    )
    # Must carry a real violation ("possibly" hedges) or rewrite_beat short-circuits.
    beat = ScriptBeat(
        beat_id=1,
        panel_ids=["p0001_01"],
        narration="He possibly walks somewhere and a character possibly reacts.",
    )

    out = rewrite_beat(beat, bible, [], {}, issues=["hedging"], llm=_ProseLLM())

    assert "walks into the gate" in out
    assert "{" not in out and "narration" not in out


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("Plain narration text.", "Plain narration text."),
        ('```\nFenced narration.\n```', "Fenced narration."),
        ('{"narration": "Envelope narration."}', "Envelope narration."),
        ('Narration: Labelled narration.', "Labelled narration."),
        ('"Quoted narration."', "Quoted narration."),
    ],
)
def test_clean_prose_reply_unwraps_stock_shapes(reply, expected) -> None:
    """Models still wrap prose replies despite the instruction — unwrap, never ship braces."""
    from manhwa2vid.script.lint import _clean_prose_reply

    assert _clean_prose_reply(reply) == expected


@pytest.mark.parametrize(
    "raw",
    [
        '[{"bubbles": ["hi"], "people": []}]',           # object wrapped in an array
        '[{"bubbles": ["hi"]}, {"bubbles": ["bye"]}]',   # array of objects
        "[{'bubbles': ['hi']},]",                        # malformed array needing repair
    ],
)
def test_extract_json_object_never_returns_a_list(raw) -> None:
    """The contract is ONE OBJECT — every caller does data.get(...).

    json_repair happily produces an array from a bare list, and returning it raised
    "AttributeError: 'list' object has no attribute 'get'" mid vision run.
    """
    import json as _json

    from manhwa2vid.llm.provider import _extract_json_object

    data = _json.loads(_extract_json_object(raw))
    assert isinstance(data, dict), f"got {type(data).__name__}"
    assert "bubbles" in data


@pytest.mark.parametrize(
    "message",
    [
        "Error code: 429 - Your prepayment credits are depleted. Please go to AI Studio",
        "429 insufficient_quota: You exceeded your current quota",
        "Your credit balance is too low to access this model",
    ],
)
def test_billing_exhaustion_is_fatal_not_retried(message) -> None:
    """Out of money is permanent; retrying wastes time and, worse, the caller's graceful
    degradation turns it into a SILENT no-op — three runs reported EXIT=0 with green
    gates while every vision call failed and stale cards were reused."""
    from manhwa2vid.llm.provider import BillingExhausted, _retry_on_rate_limit

    calls = {"n": 0}

    def _boom():
        calls["n"] += 1
        raise RuntimeError(message)

    with pytest.raises(BillingExhausted):
        _retry_on_rate_limit(_boom)
    assert calls["n"] == 1, "must not retry a billing failure"


def test_ordinary_rate_limit_still_retries(monkeypatch) -> None:
    """Throughput limits are transient and must keep their backoff."""
    from manhwa2vid.llm.provider import _retry_on_rate_limit

    monkeypatch.setattr("time.sleep", lambda _s: None)
    calls = {"n": 0}

    def _flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("429 rate_limit_exceeded: too many requests")
        return "ok"

    assert _retry_on_rate_limit(_flaky) == "ok"
    assert calls["n"] == 3


def test_preflight_raises_on_dead_key() -> None:
    """One cheap call proves the key can spend before ~60 vision calls are attempted."""
    from manhwa2vid.llm.provider import BillingExhausted, preflight_check

    class _Dead:
        def complete(self, system, user, *, json_mode=False):
            raise RuntimeError("429 - Your prepayment credits are depleted.")

        def describe_panels(self, image_paths, prompt):
            return "{}"

    with pytest.raises(BillingExhausted):
        preflight_check(_Dead(), label="test")
