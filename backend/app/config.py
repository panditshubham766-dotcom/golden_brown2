"""
LexiGuard — application configuration.

All settings come from environment variables (or a .env file that is NEVER committed).
No secret ever appears in source code.
"""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LEXIGUARD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8000

    # ── Auth ──────────────────────────────────────────────────────────────────
    # Per-launch bearer token, generated at startup — never set in env.
    # The env var is here only so tests can inject a known value.
    launch_token: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    # One-time launch code lives for this many seconds.
    launch_code_ttl_seconds: int = 60

    # ── Storage ───────────────────────────────────────────────────────────────
    data_dir: Path = Path("data/docs")

    # ── Upload limits ─────────────────────────────────────────────────────────
    max_upload_bytes: int = 50 * 1024 * 1024   # 50 MB
    max_pages: int = 500
    max_text_bytes: int = 10 * 1024 * 1024     # 10 MB extracted text

    # ── Parser sandbox ────────────────────────────────────────────────────────
    parser_timeout_seconds: float = 120.0
    parser_output_cap_bytes: int = 20 * 1024 * 1024  # 20 MB JSON

    # ── TXT virtual pages ─────────────────────────────────────────────────────
    txt_virtual_page_chars: int = 3_000

    # ── FTS5 ─────────────────────────────────────────────────────────────────
    fts_max_chunks_per_call: int = 12

    # ── Language gate thresholds (no ML) ──────────────────────────────────────
    # Share of letters outside Latin script → mark page UNREAD_LANGUAGE
    lang_nonlatin_threshold: float = 0.15
    # Share of common English function words needed (pages ≥ 40 tokens)
    lang_english_fn_threshold: float = 0.08
    # Min token count to apply function-word test
    lang_min_tokens_for_fn_test: int = 40

    # ── Local LLM (Tier 0 Ollama) ─────────────────────────────────────────────
    ollama_base_url: str = "http://127.0.0.1:11434"
    model_tag: str = "gemma4:e2b-it-q4_K_M"

    # ── Environment ───────────────────────────────────────────────────────────
    environment: Literal["development", "production", "test"] = "development"

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, v: object) -> Path:
        return Path(str(v)).expanduser().resolve()


# Module-level singleton — import and use `get_settings()` so tests can patch.
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
