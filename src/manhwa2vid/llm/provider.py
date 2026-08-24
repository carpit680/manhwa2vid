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


# Longest single wait we'll honor for a daily-token (TPD) limit before giving up. The TPD
# window is rolling, so short server-suggested waits are worth sleeping through on long
# runs; anything beyond this means "come back much later" and should surface as an error
# (incremental checkpoints make the re-run cheap).
_TPD_MAX_WAIT_S = 20 * 60.0


def _parse_retry_after(msg: str) -> float | None:
    match = re.search(r"try again in (?:(\d+)m)?([\d.]+)(?:s|ms)", msg)
    if not match:
        return None
    minutes = float(match.group(1) or 0)
    seconds = float(match.group(2))
    if "ms" in match.group(0):
        seconds /= 1000.0
    return minutes * 60.0 + seconds


class BillingExhausted(RuntimeError):
    """Provider credits are gone. Permanent until a human tops up — never retried,
    never swallowed by a stage's graceful-degradation path."""


# Phrases providers use for "you are out of money", as distinct from "you are going too
# fast". Gemini: "Your prepayment credits are depleted"; OpenAI: "exceeded your current
# quota" / "insufficient_quota"; Anthropic: "credit balance is too low".
_BILLING_PHRASES = (
    "credits are depleted",
    "prepayment",
    "insufficient_quota",
    "exceeded your current quota",
    "credit balance is too low",
    "billing",
)


def _is_billing_exhausted(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(phrase in msg for phrase in _BILLING_PHRASES)


def _retry_on_rate_limit(call: Any, *, max_attempts: int = 8) -> Any:
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return call()
        except Exception as exc:
            last_exc = exc
            msg = str(exc).lower()
            if "request too large" in msg or "reduce your message size" in msg or "413" in msg:
                # A per-request size cap: retrying the identical request can never succeed.
                # Raise immediately so the caller's shrink-and-retry handler engages.
                raise
            if _is_billing_exhausted(exc):
                # Money, not throughput. Retrying and backing off cannot help, and the
                # caller's graceful degradation turns this into a SILENT no-op: three
                # full runs reported EXIT=0 with green gates while every vision window
                # returned nothing and stale cards were reused. Stop the run outright.
                raise BillingExhausted(
                    "LLM provider credits are exhausted — top up billing and re-run. "
                    "No artifacts were regenerated."
                ) from exc
            if "rate_limit" not in msg and "429" not in msg:
                raise
            suggested = _parse_retry_after(msg)
            if "tokens per day" in msg or "tpd" in msg:
                # Daily budget: wait only if the server names a bounded, rolling-window
                # wait; otherwise fail fast so the caller's checkpoint can resume later.
                if suggested is None or suggested > _TPD_MAX_WAIT_S:
                    raise
                from rich.console import Console

                Console().print(
                    f"[yellow]Daily token limit — waiting {suggested / 60:.1f} min for the window to roll[/]"
                )
                time.sleep(suggested + 1.0)
                continue
            wait = min(60.0, 2 ** attempt)
            if suggested is not None:
                wait = max(wait, suggested + 0.5)
            time.sleep(wait)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("rate limit retries exhausted")


def _extract_json_object(text: str) -> str:
    """Strip thinking blocks / prose and return the first top-level JSON object.

    Must return exactly ONE complete object. Models emit trailing prose, markdown fences,
    and sometimes a second object after the first — a naive first-brace-to-last-brace slice
    yields 'Extra data' or 'Expecting , delimiter' at the caller's json.loads(). Decoding
    incrementally from each candidate '{' is the only way to cut at the real object end.
    """
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    # ```json fences wrap the object often enough to be worth stripping outright.
    cleaned = re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", cleaned, flags=re.S).strip()

    decoder = json.JSONDecoder()
    start = cleaned.find("{")
    while start != -1:
        try:
            _obj, end = decoder.raw_decode(cleaned, start)
        except ValueError:
            start = cleaned.find("{", start + 1)
            continue
        return cleaned[start:end]

    # Nothing decoded cleanly. Real generations fail in ways no single heuristic covers:
    # literal newlines inside strings, trailing commas, single-quoted keys, bad backslash
    # escapes, and unescaped quotes in prose (which are genuinely ambiguous — a quote
    # before a comma looks exactly like end-of-string). Hand-rolled repair loses that
    # game, so delegate to a parser built for it.
    try:
        from json_repair import repair_json

        repaired = repair_json(cleaned, return_objects=False)
        if repaired and repaired not in ("{}", '""', "[]"):
            parsed = json.loads(repaired)  # only hand back something that actually parses
            # This function's contract is ONE OBJECT — every caller does data.get(...).
            # Repair happily produces an array when the model emitted a bare list or a
            # single object wrapped in brackets; returning that raised
            # "AttributeError: 'list' object has no attribute 'get'" mid vision run.
            if isinstance(parsed, dict):
                return repaired
            if isinstance(parsed, list):
                first = next((item for item in parsed if isinstance(item, dict)), None)
                if first is not None:
                    return json.dumps(first)
    except Exception:
        pass

    # Fall back to a brace-balanced slice so the caller sees a best-effort object
    # rather than prose.
    start = cleaned.find("{")
    if start == -1:
        return cleaned or "{}"
    depth = 0
    in_string = False
    escaped = False
    for i, ch in enumerate(cleaned[start:], start):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
        elif ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return cleaned[start : i + 1]
    return cleaned[start:] or "{}"


class LLMProvider(ABC):
    #: Sampling temperature for this provider instance, set per stage by
    #: `apply_stage_model`. None means "send no temperature and take the provider
    #: default" — which is roughly 1.0 and was the pipeline's behaviour for its whole
    #: life, so every run resampled the scene cards, the synopsis and the outline as well
    #: as the prose. Structured stages run greedy; only narration keeps any warmth.
    temperature: float | None = None

    @abstractmethod
    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        ...

    @abstractmethod
    def describe_panels(self, image_paths: list[Path], prompt: str) -> str:
        ...

    def describe_labeled_panels(self, labeled: list[tuple[str, Path]], prompt: str) -> str:
        """Annotate images whose identity must be unambiguous.

        Handing a model N images plus a text list of N ids does NOT bind them: on a
        59-panel chapter the annotations came back correct but attached to the id three
        positions later (measured shift +3, 0.75 similarity). The model cannot reliably
        count "this is image 37". Interleaving a label immediately before each image makes
        the binding positional in the message itself rather than a lookup it must
        maintain. Providers that cannot interleave fall back to the unlabeled path.
        """
        return self.describe_panels([path for _label, path in labeled], prompt)


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
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
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
            **({"temperature": self.temperature} if self.temperature is not None else {}),
        )
        return resp.choices[0].message.content or "{}"


def _is_request_too_large(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "request too large" in msg or "reduce your message size" in msg or "413" in msg


def _shrink_middle(text: str, keep_ratio: float = 0.7) -> str:
    """Drop the middle of an oversized prompt, keeping head (instructions/context) and
    tail (the seed/outline being worked on). Free tiers cap tokens per REQUEST, so long
    chapters must degrade gracefully instead of dying."""
    n = len(text)
    keep = max(500, int(n * keep_ratio / 2))
    if keep * 2 >= n:
        return text
    return text[:keep] + "\n…[evidence trimmed to fit the request size limit]…\n" + text[n - keep:]


def _is_json_mode_error(exc: Exception) -> bool:
    """Did the request fail *because* of JSON mode, rather than for a real reason?"""
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("json_validate_failed", "response_format", "json mode", "json_object")
    )


class OpenAICompatProvider(LLMProvider):
    """Shared implementation for OpenAI-compatible chat APIs (Groq, Gemini, Mistral).

    Subclasses only declare their endpoint, key env vars, and default models. Rate-limit
    retries, vision encoding, and the JSON-mode fallback are handled once here.
    """

    BASE_URL: str = ""
    API_KEY_ENVS: tuple[str, ...] = ()
    TEXT_MODEL_ENVS: tuple[str, ...] = ()
    VISION_MODEL_ENVS: tuple[str, ...] = ()
    DEFAULT_TEXT_MODEL: str = ""
    DEFAULT_VISION_MODEL: str = ""
    MAX_VISION_TOKENS: int = 4096

    #: Why the last call stopped ("stop" | "length" | ...). "length" means truncated.
    last_finish_reason: str = ""
    last_completion_tokens: int = 0

    def __init__(self, text_model: str | None = None, vision_model: str | None = None) -> None:
        from openai import OpenAI

        api_key = next((os.getenv(env) for env in self.API_KEY_ENVS if os.getenv(env)), None)
        self.client = OpenAI(api_key=api_key, base_url=self.BASE_URL)
        self.model = text_model or env_or(self.DEFAULT_TEXT_MODEL, *self.TEXT_MODEL_ENVS)
        self.vision_model = vision_model or env_or(self.DEFAULT_VISION_MODEL, *self.VISION_MODEL_ENVS)

    def _extra_body(self, model: str) -> dict[str, Any] | None:
        """Per-model request tweaks. Thinking models otherwise spend their whole token
        budget on reasoning and return an empty/truncated body.

        Gemini 3.x was added after a 28-beat narration response came back cut
        mid-structure at a 4096-token cap: reasoning consumed the budget, the JSON never
        closed, and the salvage path silently yielded zero beats for three straight runs.
        """
        low = model.lower()
        if "qwen" in low:
            return {"reasoning_effort": "none"}
        if "gemini-3" in low or "gemini-4" in low:
            return {"reasoning_effort": "none"}
        return None

    def _record_finish(self, resp: Any) -> None:
        """Remember why the model stopped, so callers can tell truncation from an answer.

        `_extract_json_object` is deliberately resilient: given a truncated body it
        returns the first COMPLETE inner object rather than raising. That is correct for
        vision windows and catastrophic for a whole-script narration response, where the
        first complete inner object is a single beat and the caller reads
        `data["beats"]` — getting nothing, silently, run after run. The salvage stays;
        callers that cannot tolerate it now have a signal to check.
        """
        try:
            self.last_finish_reason = str(resp.choices[0].finish_reason or "")
        except Exception:
            self.last_finish_reason = ""
        try:
            self.last_completion_tokens = int(resp.usage.completion_tokens)
        except Exception:
            self.last_completion_tokens = 0

    def available_models(self) -> list[str]:
        """Model ids this key can actually reach — availability is key-dependent."""
        try:
            return sorted(m.id for m in self.client.models.list().data)
        except Exception:
            return []

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        def call(use_json: bool, user_text: str) -> Any:
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_text},
                ],
            }
            extra = self._extra_body(self.model)
            if extra:
                kwargs["extra_body"] = extra
            if use_json:
                kwargs["response_format"] = {"type": "json_object"}
            if self.temperature is not None:
                kwargs["temperature"] = self.temperature
            return self.client.chat.completions.create(**kwargs)

        resp = None
        current = user
        for shrink_attempt in range(4):
            try:
                resp = _retry_on_rate_limit(lambda: call(json_mode, current))
                break
            except Exception as exc:
                if _is_request_too_large(exc) and shrink_attempt < 3:
                    from rich.console import Console

                    current = _shrink_middle(current)
                    Console().print(
                        f"[yellow]Prompt over the per-request cap — retrying at "
                        f"{len(current)} chars[/]"
                    )
                    continue
                if not (json_mode and _is_json_mode_error(exc)):
                    raise
                resp = _retry_on_rate_limit(lambda: call(False, current))
                break
        self._record_finish(resp)
        content = resp.choices[0].message.content or ""
        return _extract_json_object(content) if json_mode else content

    def describe_labeled_panels(self, labeled: list[tuple[str, Path]], prompt: str) -> str:
        """Interleave each label immediately before its image so binding is positional."""
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for label, path in labeled:
            media_type, data = encode_image_for_api(path)
            content.append({"type": "text", "text": label})
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{data}"},
                }
            )
        return self._vision_call(content)

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
        return self._vision_call(content)

    def _vision_call(self, content: list[dict[str, Any]]) -> str:

        def call(json_mode: bool) -> Any:
            kwargs: dict[str, Any] = {
                "model": self.vision_model,
                "messages": [{"role": "user", "content": content}],
                "max_completion_tokens": self.MAX_VISION_TOKENS,
            }
            extra = self._extra_body(self.vision_model)
            if extra:
                kwargs["extra_body"] = extra
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            if self.temperature is not None:
                kwargs["temperature"] = self.temperature
            return self.client.chat.completions.create(**kwargs)

        try:
            resp = _retry_on_rate_limit(lambda: call(True))
        except Exception as exc:
            if not _is_json_mode_error(exc):
                raise
            # Fall back to free-form output and extract the JSON object locally.
            resp = _retry_on_rate_limit(lambda: call(False))
        self._record_finish(resp)
        return _extract_json_object(resp.choices[0].message.content or "{}")


class GroqProvider(OpenAICompatProvider):
    """Groq Cloud — fastest inference, but the free tier caps on tokens-per-day (200k),
    which images exhaust quickly (~60 panels/day at 512px)."""

    GROQ_BASE_URL = "https://api.groq.com/openai/v1"
    BASE_URL = GROQ_BASE_URL
    API_KEY_ENVS = ("GROQ_API_KEY",)
    TEXT_MODEL_ENVS = ("GROQ_TEXT_MODEL",)
    VISION_MODEL_ENVS = ("GROQ_VISION_MODEL",)
    DEFAULT_TEXT_MODEL = "llama-3.3-70b-versatile"
    DEFAULT_VISION_MODEL = "qwen/qwen3.6-27b"


class GeminiProvider(OpenAICompatProvider):
    """Google Gemini via its OpenAI-compatible endpoint. The free tier limits requests
    per day rather than tokens per day, which suits image-heavy workloads far better."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
    API_KEY_ENVS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
    TEXT_MODEL_ENVS = ("GEMINI_TEXT_MODEL",)
    VISION_MODEL_ENVS = ("GEMINI_VISION_MODEL",)
    DEFAULT_TEXT_MODEL = "gemini-2.5-flash"
    DEFAULT_VISION_MODEL = "gemini-2.5-flash"


class MistralProvider(OpenAICompatProvider):
    """Mistral — very large monthly token allowance on the free tier, but a low
    requests-per-minute ceiling, so it suits long unattended batches."""

    BASE_URL = "https://api.mistral.ai/v1"
    API_KEY_ENVS = ("MISTRAL_API_KEY",)
    TEXT_MODEL_ENVS = ("MISTRAL_TEXT_MODEL",)
    VISION_MODEL_ENVS = ("MISTRAL_VISION_MODEL",)
    DEFAULT_TEXT_MODEL = "mistral-large-latest"
    # Vision model naming has churned (Pixtral 12B retired). Verify against
    # available_models() — tools/vision_bakeoff.py does this before running.
    DEFAULT_VISION_MODEL = "mistral-medium-latest"


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
            if "checking a narration against the storyboard" in system:
                # Flags any beat whose text follows a marked boundary without naming an
                # interval, so the corrective loop can be exercised offline.
                import re as _re

                flagged = []
                bounds = _re.findall(r"beat (\d+): ", user)
                for bid in bounds[:3]:
                    seg = user.split(f"[beat {bid}] ")
                    body = seg[1].split("[beat")[0] if len(seg) > 1 else ""
                    if not _re.search(r"\b(?:years?|hours?|days?) (?:later|earlier|ago)\b", body, _re.I):
                        flagged.append({
                            "beat_id": int(bid),
                            "problem": "the story crosses a marked boundary without saying so",
                            "fix_hint": "Open with: 'Twenty-five years later, ...'",
                        })
                return json.dumps({
                    "transitions": flagged, "order_problems": [], "misportrayals": [],
                    "sequence_ok": not flagged, "score": 9 if not flagged else 5,
                })
            if "You are watching a recap video" in system:
                # Deterministic stand-in for the viewer: complains when the narration
                # never marks its time jumps, so fixtures can drive the loop offline.
                # followable is the axis that actually moves on the seeded defect; the
                # other three stay fixed so a candidate's total score still separates
                # cleanly without every axis needing its own offline heuristic.
                first = user.strip().split(".")[0][:60]
                marked = "years later" in user.lower() or "earlier," in user.lower()
                lost = [] if marked else [{"quote": first, "why": "no idea when or where this is"}]
                return json.dumps({
                    "lost": lost, "flat": [], "best_moment": first,
                    "followable": 5 if marked else 2,
                    "told_not_listed": 4, "payoffs_landed": 4, "rhythm": 4,
                    "keep_watching": marked,
                })
            if "Pick the one a viewer would rather listen to" in system:
                a = user.split("Candidate B:")[0]
                marked = "years later" in a.lower() or "earlier," in a.lower()
                return json.dumps({"winner": "A" if marked else "B",
                                   "why": "mock prefers the candidate that marks its time jumps"})
            if "narration entry for every outline beat" in system_lower:
                ids = sorted({int(m) for m in re.findall(r"Beat (\d+) \[", user)})
                if not ids:
                    ids = [1]
                return json.dumps(
                    {
                        "beats": [
                            {
                                "beat_id": i,
                                "narration": "Our hero presses forward as the story continues.",
                            }
                            for i in ids
                        ]
                    }
                )
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
                return text  # rewrite_beat takes plain prose, not a JSON envelope
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
        if "Choose the better narration" in prompt:
            # Placed ABOVE the fact-check branch: a judge prompt that fell through to it
            # would get {"unsupported": [], "severity": "none"} and silently "pass".
            # Deterministic pick so order-swap agreement is testable offline.
            return json.dumps({"winner": "A", "why": "mock prefers the first candidate"})
        if "fact-check" in prompt.lower():
            return json.dumps({"unsupported": [], "severity": "none"})
        if "series story map by skimming" in prompt:
            return json.dumps(
                {
                    "summary": "The hero survives an ordeal and sets out toward the tower.",
                    "key_events": ["hero survives", "sets out"],
                    "characters_introduced": [{"name": "Hero", "role": "protagonist"}],
                    "world_facts": ["gates lead to dungeons"],
                    "cliffhanger": "a new floor opens",
                    "hook_moments": ["the hero shatters the ice"],
                }
            )
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
        if "Read it as a story" in prompt:
            return json.dumps({
                "summary": "A hunter crosses the city, joins a party, enters a gate.",
                "temporal_devices": "",
                "roster": [{"who": "Hero", "looks": "dark hair", "first_seen": "start"}],
            })
        if "annotate ONLY these" in prompt or "IMAGE -> PANEL ID MAPPING" in prompt:
            # Chapter mode annotates every panel in ONE response, keyed by the ids the
            # prompt assigned. Reading them back out of the prompt is exactly what a real
            # model does, so the mock exercises the same id-binding path.
            mapped = re.findall(r"Image \d+: (\S+)", prompt) or [
                (pp.stem if pp.stem.startswith("p") else f"panel_{pp.stem}")
                for pp in image_paths
            ]
            return json.dumps(
                {
                    "story_map": {
                        "summary": "A hunter crosses the city, joins a party, enters a gate.",
                        "temporal_devices": "",
                    },
                    "panels": [self._mock_panel_dict([pid]) for pid in mapped],
                }
            )
        return json.dumps(self._mock_panel_dict(ids))

    def describe_labeled_panels(self, labeled: list[tuple[str, Path]], prompt: str) -> str:
        """Sighted narration sends BEAT/PANEL labels — answer in the narration shape.

        Without this the mock replies with a scene card and every beat comes back empty,
        so beat-conservation fails on a pipeline that is actually fine.
        """
        beat_ids: list[int] = []
        for label, _path in labeled:
            match = re.search(r"BEAT (\d+)", label)
            if match:
                bid = int(match.group(1))
                if bid not in beat_ids:
                    beat_ids.append(bid)
        if beat_ids:
            return json.dumps(
                {
                    "beats": [
                        {"beat_id": bid,
                         "narration": f"Beat {bid}: the hunter moves through the scene."}
                        for bid in beat_ids
                    ]
                }
            )
        return self.describe_panels([path for _label, path in labeled], prompt)

    def _mock_panel_dict(self, ids: list[str]) -> dict[str, Any]:
        # Vary per panel. A mock that returns one identical card for every panel is not a
        # faithful stand-in: it is exactly the degenerate output the card-diversity gate
        # exists to catch, so a constant mock would make the suite assert that a real bug
        # is acceptable. List lengths are coprime so the phrasing cycle is long (7*11*13).
        tag = ids[0] if ids else "p0000_00"
        seed = sum(ord(c) * (i + 1) for i, c in enumerate(tag))
        places = ["a rain-slicked street", "a lamplit corridor", "a crowded platform",
                  "a quiet rooftop", "a flooded stairwell", "a shuttered market",
                  "a humming server room"]
        actors = ["a courier", "the guild clerk", "two students", "a night nurse",
                  "an off-duty guard", "a busker", "the shop owner", "a lost tourist",
                  "a taxi driver", "a window cleaner", "a paramedic"]
        beats = ["braces against the wall", "counts something under their breath",
                 "turns toward a distant sound", "checks a cracked phone screen",
                 "shoulders a heavy bag", "steps back from the kerb",
                 "wipes rain from their eyes", "waves someone through",
                 "stops mid-sentence", "reaches for a door handle",
                 "glances at the darkening sky", "shakes out a numb hand",
                 "pockets a folded note"]
        place = places[seed % 7]
        actor = actors[seed % 11]
        beat = beats[seed % 13]
        return (
            {
                "panel_id": tag,
                "speakers": ["Hero"],
                "people": [
                    {"ref": "new", "name_used": "Hero", "descriptor": "", "visibility": "face"}
                ],
                # Attributed shape, so the pipeline test exercises the real contract.
                "bubbles": [
                    {"text": f"We should move, {actor} says.", "speaker": "Hero", "to": actor}
                ],
                "dialogue_summary": f"{actor} mentions {place} while {beat}.",
                "action": f"Near {place}, {actor} {beat} as the light shifts ({tag}).",
                "mood": "dramatic",
                "key_terms": [],
                "panel_ids": ids,
                "is_story": True,
                "panel_type": "story",
            }
        )


def preflight_check(llm: LLMProvider, *, label: str = "provider") -> None:
    """One cheap call to prove the key can actually spend, before a long run starts.

    A depleted key fails identically to a healthy one until the first request — and a
    chapter pass makes ~60 of them. Costs a handful of tokens; saves discovering the
    problem after the run reports success on stale artifacts.
    """
    from rich.console import Console

    try:
        llm.complete("Reply with OK.", "ping", json_mode=False)
    except BillingExhausted:
        raise
    except Exception as exc:
        if _is_billing_exhausted(exc):
            raise BillingExhausted(
                f"{label}: credits exhausted — top up billing before re-running."
            ) from exc
        # Anything else (transient network, odd model) is not worth blocking the run.
        Console().print(f"[dim]Preflight warning for {label}: {type(exc).__name__}[/]")


def get_stage_llm(stage: str, config: dict[str, Any] | None = None) -> LLMProvider:
    """Provider for a pipeline stage, honoring a per-stage override before the global one.

    `scene.provider` covers the vision-heavy stages (scene analysis, scout, alignment
    audit); `script.provider` covers the text stages. Free tiers cap on different axes
    (Groq: tokens/day; Gemini: requests/day; Mistral: tokens/month), so splitting vision
    and text across providers is often the difference between one chapter per day and a
    full run.
    """
    config = config or load_config()
    # Precedence: per-stage env > global mock kill-switch > per-stage config > global.
    # LLM_PROVIDER=mock must always win so tests/dev runs can never hit a real API just
    # because config.yaml carries a stage override.
    name = os.getenv(f"{stage.upper()}_LLM_PROVIDER") or None
    if name is None and os.getenv("LLM_PROVIDER", "").lower() == "mock":
        name = "mock"
    if name is None:
        name = get_nested(config, stage, "provider")
    return get_llm_provider(name, config=config)


def stage_temperature(stage: str, config: dict[str, Any]) -> float | None:
    """Per-stage sampling temperature, falling back to the global default.

    Greedy decoding on the structured stages is what makes two runs of a chapter
    comparable: the same cards, the same synopsis, the same beat partition and panel
    bindings. Narration keeps a little warmth because greedy decoding is the classic cause
    of repetitive text, and this module already carries lints for that failure whose every
    extra firing routes a beat into the rewrite path.

    Note this buys much LESS variance, not reproducibility: hosted providers batch and
    route requests server-side, so none of them promise identical output even at 0.
    """
    value = get_nested(config, stage, "temperature")
    if value is None:
        value = get_nested(config, "llm", "temperature")
    return None if value is None else float(value)


def apply_stage_model(llm: LLMProvider, stage: str, config: dict[str, Any]) -> LLMProvider:
    """Apply the stage's configured model pin — UNLESS an env override redirected the
    stage to a different provider. Model ids are provider-specific: pinning
    `script.model: gemini-2.5-flash` onto a Mistral client (reached via
    SCRIPT_LLM_PROVIDER=mistral) is a guaranteed 400."""
    if os.getenv(f"{stage.upper()}_LLM_PROVIDER"):
        return llm  # provider overridden — its own default/config model applies
    llm.temperature = stage_temperature(stage, config)
    model = get_nested(config, stage, "model")
    if model:
        if stage == "scene" and hasattr(llm, "vision_model"):
            llm.vision_model = model
        elif hasattr(llm, "model"):
            llm.model = model
    return llm


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

    if name == "gemini":
        if not any(os.getenv(env) for env in GeminiProvider.API_KEY_ENVS):
            console.print(
                "[yellow]Warning:[/] GEMINI_API_KEY is missing or empty in .env — "
                "using mock LLM (placeholder script). Add your key and re-run with --force."
            )
            return MockLLMProvider()
        return GeminiProvider(
            text_model=get_nested(config, "llm", "gemini", "text_model"),
            vision_model=get_nested(config, "llm", "gemini", "vision_model"),
        )

    if name == "mistral":
        if not os.getenv("MISTRAL_API_KEY"):
            console.print(
                "[yellow]Warning:[/] MISTRAL_API_KEY is missing or empty in .env — "
                "using mock LLM (placeholder script). Add your key and re-run with --force."
            )
            return MockLLMProvider()
        return MistralProvider(
            text_model=get_nested(config, "llm", "mistral", "text_model"),
            vision_model=get_nested(config, "llm", "mistral", "vision_model"),
        )

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
