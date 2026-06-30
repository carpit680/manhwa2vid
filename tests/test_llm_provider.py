"""LLM provider selection tests."""

from __future__ import annotations

import pytest

from manhwa2vid.llm.provider import GroqProvider, MockLLMProvider, OpenAIProvider, get_llm_provider


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
