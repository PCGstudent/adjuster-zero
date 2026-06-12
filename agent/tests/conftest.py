"""Test isolation: the suite must NEVER touch a real Supabase or Gemini, even
when the developer's .env is populated. We blank the relevant env vars and clear
the settings cache so every test uses the in-memory store + offline planner."""

from __future__ import annotations

import os

import pytest

from adjuster_zero.config import get_settings

_BLANK = [
    "DATABASE_URL", "SUPABASE_URL", "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY", "GEMINI_API_KEY", "LANGSMITH_API_KEY",
]


@pytest.fixture(autouse=True, scope="session")
def _hermetic_settings() -> None:
    for key in _BLANK:
        os.environ[key] = ""
    # Settings reads env > .env file; blanks override the populated .env.
    get_settings.cache_clear()
    get_settings()
