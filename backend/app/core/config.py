"""Centralised, environment-driven configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_SYSTEM_PROMPT = (
    "You are Lyftr AI, a concise and helpful assistant. "
    "Answer clearly and accurately. Use Markdown when it improves readability."
)


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def sqlite_path_from_url(url: str) -> str:
    """Convert a SQLAlchemy-style SQLite URL into a filesystem path.

    sqlite:////data/app.db -> /data/app.db   (absolute)
    sqlite:///./app.db     -> ./app.db       (relative)
    """
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise ConfigError("DATABASE_URL must be a SQLite URL, e.g. sqlite:////data/app.db")
    path = url[len(prefix):]
    if not path:
        raise ConfigError("DATABASE_URL does not contain a database file path")
    return path


@dataclass(frozen=True)
class Settings:
    api_keys: list[str] = field(repr=False)  # never printed
    database_url: str
    allowed_origins: list[str]
    enable_failure_simulation: bool
    llm_models: list[str]
    default_system_prompt: str
    llm_timeout_seconds: float
    cache_ttl_seconds: int
    fallback_model: str = ""
    fallback_api_base: str = ""
    fallback_api_key: str = field(default="", repr=False)
    fallback_timeout_seconds: float = 120.0

    @property
    def fallback_enabled(self) -> bool:
        return bool(self.fallback_model and self.fallback_api_base and self.fallback_api_key)

    @property
    def key_ids(self) -> list[str]:
        return [f"key_{i}" for i in range(1, len(self.api_keys) + 1)]

    @property
    def database_path(self) -> str:
        return sqlite_path_from_url(self.database_url)


def load_settings() -> Settings:
    keys = _csv(os.getenv("LLM_API_KEYS"))
    if len(keys) < 2:
        raise ConfigError(
            f"LLM_API_KEYS must contain at least 2 comma-separated keys (found {len(keys)})"
        )
    database_url = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
    sqlite_path_from_url(database_url)  # validate early

    return Settings(
        api_keys=keys,
        database_url=database_url,
        allowed_origins=_csv(os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")),
        enable_failure_simulation=_bool(os.getenv("ENABLE_FAILURE_SIMULATION"), False),
        llm_models=_csv(os.getenv("LLM_MODEL")) or ["gemini/gemini-3.5-flash-lite"],
        default_system_prompt=os.getenv("DEFAULT_SYSTEM_PROMPT") or DEFAULT_SYSTEM_PROMPT,
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
        cache_ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", "86400")),
        fallback_model=(os.getenv("FALLBACK_LLM_MODEL") or "").strip(),
        fallback_api_base=(os.getenv("FALLBACK_LLM_API_BASE") or "").strip(),
        fallback_api_key=(os.getenv("FALLBACK_LLM_API_KEY") or "").strip(),
        fallback_timeout_seconds=float(os.getenv("FALLBACK_LLM_TIMEOUT_SECONDS") or "120"),
    )
