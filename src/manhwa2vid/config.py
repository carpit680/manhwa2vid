"""Configuration loading."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def find_repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for parent in [here, *here.parents]:
        if (parent / "config.yaml").exists():
            return parent
    return Path.cwd()


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    root = find_repo_root()
    load_dotenv(root / ".env")
    path = config_path or root / "config.yaml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_nested(config: dict[str, Any], *keys: str, default: Any = None) -> Any:
    node: Any = config
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def env_or(default: str, *keys: str) -> str:
    for key in keys:
        val = os.getenv(key)
        if val:
            return val
    return default
