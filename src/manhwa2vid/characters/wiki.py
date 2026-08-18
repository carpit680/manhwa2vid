"""Wiki / Fandom cast lookup."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

import httpx

from manhwa2vid.characters.bible import slugify_char_id
from manhwa2vid.config import get_nested
from manhwa2vid.models import CharacterProfile, CharacterTier

_USER_AGENT = "manhwa2vid/1.0 (character scout)"


def _fandom_slug(title: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", title.strip()).strip("-")


def fetch_wiki_cast(title: str, config: dict[str, Any]) -> list[CharacterProfile]:
    """Fetch main cast from Fandom API. Returns [] on failure."""
    if not get_nested(config, "characters", "wiki_lookup", default=False):
        return []

    wiki_slug = _fandom_slug(title)
    api_url = f"https://{wiki_slug}.fandom.com/api.php"
    params = {
        "action": "query",
        "format": "json",
        "list": "categorymembers",
        "cmtitle": "Category:Characters",
        "cmlimit": "50",
    }
    try:
        with httpx.Client(timeout=15.0, headers={"User-Agent": _USER_AGENT}) as client:
            resp = client.get(api_url, params=params)
            if resp.status_code != 200:
                return _fetch_wiki_fallback(title, config)
            data = resp.json()
    except Exception:
        return _fetch_wiki_fallback(title, config)

    members = data.get("query", {}).get("categorymembers", [])
    profiles: list[CharacterProfile] = []
    for index, member in enumerate(members[:20]):
        name = str(member.get("title", "")).strip()
        if not name or name.startswith("Category:"):
            continue
        tier = CharacterTier.MAIN if index == 0 else CharacterTier.SUPPORTING
        profiles.append(
            CharacterProfile(
                id=slugify_char_id(name),
                canonical_name=name,
                tier=tier,
                role="protagonist" if tier == CharacterTier.MAIN else "",
                pronoun="he",
                confidence=0.6,
                source_chapters=[],
            )
        )
    return profiles


def _fetch_wiki_fallback(title: str, config: dict[str, Any]) -> list[CharacterProfile]:
    """No cast when the wiki is unavailable.

    This used to return a curated Solo Leveling roster whenever the lookup failed, which
    only ever worked for one series and silently seeded the wrong cast for any other. The
    per-project glossary.json is the correct place to record characters by hand — it is
    human-editable, series-agnostic, and already feeds the bible through
    profiles_from_glossary.
    """
    return []


def wiki_protagonist_hint(profiles: list[CharacterProfile]) -> str | None:
    for profile in profiles:
        if profile.role == "protagonist" or profile.tier == CharacterTier.MAIN:
            return profile.id
    return profiles[0].id if profiles else None
