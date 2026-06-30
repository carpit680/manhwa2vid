"""Pluggable LLM providers."""

from __future__ import annotations

import base64
import json
import os
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

from manhwa2vid.config import env_or, get_nested, load_config
from manhwa2vid.llm.vision_utils import encode_image_for_api


def _retry_on_rate_limit(call: Any, *, max_attempts: int = 8) -> Any:
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return call()
        except Exception as exc:
            last_exc = exc
            msg = str(exc).lower()
            if "tokens per day" in msg or "tpd" in msg:
                raise
            if "rate_limit" not in msg and "429" not in msg:
                raise
            wait = min(60.0, 2 ** attempt)
            match = re.search(r"try again in ([\d.]+)s", msg)
            if match:
                wait = max(wait, float(match.group(1)) + 0.5)
            time.sleep(wait)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("rate limit retries exhausted")


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        ...

    @abstractmethod
    def describe_panels(self, image_paths: list[Path], prompt: str) -> str:
        ...


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str | None = None, vision_model: str | None = None) -> None:
        from openai import OpenAI

        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model or env_or("gpt-4o-mini", "OPENAI_MODEL")
        self.vision_model = vision_model or self.model

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def describe_panels(self, image_paths: list[Path], prompt: str) -> str:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for path in image_paths:
            media_type, data = encode_image_for_api(path)
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{data}"},
                }
            )
        resp = self.client.chat.completions.create(
            model=self.vision_model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or "{}"


class GroqProvider(LLMProvider):
    """Groq Cloud — OpenAI-compatible API for fast LLM + VLM inference."""

    GROQ_BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self, text_model: str | None = None, vision_model: str | None = None) -> None:
        from openai import OpenAI

        self.client = OpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url=self.GROQ_BASE_URL,
        )
        self.model = text_model or env_or(
            "llama-3.3-70b-versatile",
            "GROQ_TEXT_MODEL",
        )
        self.vision_model = vision_model or env_or(
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "GROQ_VISION_MODEL",
        )

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = _retry_on_rate_limit(lambda: self.client.chat.completions.create(**kwargs))
        return resp.choices[0].message.content or ""

    def describe_panels(self, image_paths: list[Path], prompt: str) -> str:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for path in image_paths:
            media_type, data = encode_image_for_api(path)
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{data}"},
                }
            )
        resp = _retry_on_rate_limit(
            lambda: self.client.chat.completions.create(
                model=self.vision_model,
                messages=[{"role": "user", "content": content}],
                response_format={"type": "json_object"},
            )
        )
        return resp.choices[0].message.content or "{}"


class OllamaProvider(LLMProvider):
    def __init__(self) -> None:
        self.base_url = env_or("http://localhost:11434", "OLLAMA_BASE_URL")
        self.model = env_or("llama3.2-vision", "OLLAMA_MODEL")
        self.vision_model = self.model

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json" if json_mode else None,
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]

    def describe_panels(self, image_paths: list[Path], prompt: str) -> str:
        images_b64 = [base64.b64encode(p.read_bytes()).decode("ascii") for p in image_paths]
        payload = {
            "model": self.vision_model,
            "messages": [{"role": "user", "content": prompt, "images": images_b64}],
            "stream": False,
            "format": "json",
        }
        with httpx.Client(timeout=180.0) as client:
            resp = client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]


class MockLLMProvider(LLMProvider):
    """Deterministic provider for tests without API keys."""

    def __init__(self) -> None:
        self.model = "mock"
        self.vision_model = "mock"

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        if json_mode:
            system_lower = system.lower()
            if "beat-by-beat" in system_lower or "plot_beat" in system_lower:
                return json.dumps(
                    {
                        "hook": "Everything changes in an instant.",
                        "beats": [
                            {
                                "beat_id": 1,
                                "panel_ids": ["p001_01"],
                                "character_ids": [],
                                "plot_beat": "Our hero begins an unexpected journey.",
                            }
                        ],
                    }
                )
            if "linking manhwa panel" in system_lower:
                return json.dumps({"merges": [], "panel_updates": []})
            if "identify people in this manhwa panel sample" in system_lower:
                return json.dumps(
                    {
                        "people": [{"name_used": "Sung Jin-Woo", "descriptor": "black hair", "visibility": "face"}],
                        "speakers": ["Sung Jin-Woo"],
                        "hair": "black",
                        "outfit": "casual",
                        "build": "slim",
                        "key_terms": ["hunter"],
                    }
                )
            if "rewrite this recap beat" in system_lower:
                text = "Our hero begins an unexpected journey."
                if "Original narration:" in user:
                    text = user.split("Original narration:")[-1].strip()
                text = re.sub(r"\bcharacter(s)?\b", "someone", text, flags=re.I)
                return json.dumps({"narration": text})
            if "character name registry" in system_lower:
                return json.dumps({"characters": {"Hero": ["Narrator"]}})
            return json.dumps(
                {
                    "beats": [
                        {
                            "beat_id": 1,
                            "panel_ids": ["p001_01"],
                            "narration": "Our hero begins an unexpected journey.",
                            "estimated_seconds": 5,
                            "character_ids": [],
                        }
                    ],
                    "hook": "Everything changes in an instant.",
                }
            )
        return "Mock recap narration."

    def describe_panels(self, image_paths: list[Path], prompt: str) -> str:
        ids = []
        for p in image_paths:
            stem = p.stem
            ids.append(stem if stem.startswith("p") else f"panel_{stem}")
        if "panel sample" in prompt.lower():
            return json.dumps(
                {
                    "people": [{"name_used": "Sung Jin-Woo", "descriptor": "black hair", "visibility": "face"}],
                    "speakers": ["Sung Jin-Woo"],
                    "hair": "black",
                    "outfit": "casual",
                    "build": "slim",
                    "key_terms": ["hunter"],
                }
            )
        return json.dumps(
            {
                "speakers": ["Hero"],
                "people": [{"ref": "new", "name_used": "Hero", "descriptor": "", "visibility": "face"}],
                "dialogue_summary": "People discuss the situation.",
                "action": "A tense scene unfolds.",
                "mood": "dramatic",
                "key_terms": [],
                "panel_ids": ids,
                "is_story": True,
                "panel_type": "story",
            }
        )


def _resolve_provider_name(provider: str | None, config: dict[str, Any]) -> str:
    return (
        provider
        or os.getenv("LLM_PROVIDER")
        or get_nested(config, "llm", "provider", default="openai")
    ).lower()


def get_llm_provider(provider: str | None = None, config: dict[str, Any] | None = None) -> LLMProvider:
    from rich.console import Console

    console = Console()
    config = config or load_config()
    name = _resolve_provider_name(provider, config)

    if name == "mock":
        return MockLLMProvider()

    if name == "groq":
        if not os.getenv("GROQ_API_KEY"):
            console.print(
                "[yellow]Warning:[/] GROQ_API_KEY is missing or empty in .env — "
                "using mock LLM (placeholder script). Add your key and re-run with --force."
            )
            return MockLLMProvider()
        text_model = (
            get_nested(config, "llm", "groq", "text_model")
            or get_nested(config, "script", "model")
        )
        vision_model = (
            get_nested(config, "llm", "groq", "vision_model")
            or get_nested(config, "scene", "model")
        )
        return GroqProvider(text_model=text_model, vision_model=vision_model)

    if name == "ollama":
        return OllamaProvider()

    if not os.getenv("OPENAI_API_KEY"):
        console.print(
            "[yellow]Warning:[/] OPENAI_API_KEY is missing — using mock LLM for script/scene stages."
        )
        return MockLLMProvider()

    text_model = get_nested(config, "script", "model")
    vision_model = get_nested(config, "scene", "model") or text_model
    return OpenAIProvider(model=text_model, vision_model=vision_model)
