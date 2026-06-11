"""Typed runtime settings, loaded from environment / .env.

The human provides all secret values (see repo `.env.example`). We never invent
credential values; absence simply degrades features (e.g. no DATABASE_URL means
the debug DB endpoints report unconfigured rather than crashing on import).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Load the repo-root .env when present; ignore unknown keys (the web app
        # shares the example file but has its own NEXT_PUBLIC_* vars).
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Gemini ---
    gemini_api_key: str = ""

    # --- Supabase / Postgres ---
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    database_url: str = ""

    # --- Observability ---
    langsmith_api_key: str = ""
    langsmith_tracing: bool = False
    langsmith_project: str = "adjuster-zero"

    # --- Runtime ---
    port: int = 8080
    claim_token_budget: int = 120_000
    max_replans: int = 2

    @property
    def db_configured(self) -> bool:
        return bool(self.database_url)

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
