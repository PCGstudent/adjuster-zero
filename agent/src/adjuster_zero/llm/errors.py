"""LLM-layer exceptions.

These exist so failure is explicit and bounded (thesis 3): a schema repair
either succeeds on the single retry or we escalate to a human — never a silent
retry loop.
"""

from __future__ import annotations


class EscalateToHuman(Exception):
    """Raised when the agent must hand a claim to a human. Carries a machine
    reason code so the executor can persist it and the UI can render it."""

    def __init__(self, reason_code: str, message: str, *, detail: object | None = None) -> None:
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code
        self.message = message
        self.detail = detail


class SchemaRepairFailed(EscalateToHuman):
    """LLM output failed schema validation twice (original + one repair)."""

    def __init__(self, errors: str, *, raw: str | None = None) -> None:
        super().__init__(
            reason_code="SCHEMA_VIOLATION",
            message="LLM output failed schema validation after one repair attempt",
            detail={"validation_errors": errors, "raw": raw},
        )
        self.errors = errors
        self.raw = raw
