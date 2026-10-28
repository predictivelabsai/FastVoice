"""YAML + environment configuration.

Values of the form ``${VAR}`` or ``${VAR:-default}`` in YAML are expanded
from the environment, so one YAML file serves every deployment and secrets
stay in ``.env``.
"""

from __future__ import annotations

import copy
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PKG_DIR = Path(__file__).resolve().parent
REPO_DIR = PKG_DIR.parent
DEFAULT_CONFIG = PKG_DIR / "configs" / "default.yaml"
_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def load_dotenv_files() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    for p in (PKG_DIR / ".env", REPO_DIR / ".env"):
        if p.exists():
            load_dotenv(p, override=False)


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        def rep(m: re.Match) -> str:
            return os.environ.get(m.group(1), m.group(2) or "")
        out = _ENV_RE.sub(rep, value)
        if out.lower() in ("true", "false"):
            return out.lower() == "true"
        try:
            return float(out) if "." in out and out.replace(".", "", 1).isdigit() else out
        except ValueError:
            return out
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class Settings:
    raw: dict

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @property
    def profile_dir(self) -> Path:
        p = Path(self.get("profile_dir") or (PKG_DIR / "profiles" / self.get("profile")))
        return p if p.is_absolute() else (PKG_DIR / p)

    @property
    def profile(self) -> dict:
        f = self.profile_dir / "profile.yaml"
        return _expand(yaml.safe_load(f.read_text(encoding="utf-8"))) if f.exists() else {}

    @property
    def locale(self) -> str:
        return self.get("locale", "lt-LT")

    @property
    def lang(self) -> str:
        return self.locale.split("-")[0]


def load_settings(path: str | Path | None = None, overrides: dict | None = None) -> Settings:
    load_dotenv_files()
    data = yaml.safe_load(Path(DEFAULT_CONFIG).read_text(encoding="utf-8"))
    extra = path or os.environ.get("KL_CONFIG")
    if extra:
        data = deep_merge(data, yaml.safe_load(Path(extra).read_text(encoding="utf-8")) or {})
    data = _expand(data)
    if overrides:
        data = deep_merge(data, overrides)
    return Settings(data)


def has_key(*names: str) -> bool:
    return any(os.environ.get(n) for n in names)
