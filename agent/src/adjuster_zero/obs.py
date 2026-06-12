"""Observability wiring. Our own decision log (agent_decisions) + event log are
the primary trace; LangSmith is optional and env-gated. When enabled, LangGraph
auto-traces graph runs via the LANGCHAIN_* env vars set here. Our `trace_id` is
minted at intake and propagated into every claim_events row regardless.
"""

from __future__ import annotations

import os

from .config import get_settings


def configure_tracing() -> bool:
    """Enable LangSmith tracing if configured. Returns whether it was enabled."""
    s = get_settings()
    if not (s.langsmith_tracing and s.langsmith_api_key):
        return False
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", s.langsmith_api_key)
    os.environ.setdefault("LANGCHAIN_PROJECT", s.langsmith_project)
    return True
