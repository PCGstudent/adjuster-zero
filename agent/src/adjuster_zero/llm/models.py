"""Model tiering map and free-tier rate limits (CLAUDE.md fixed stack).

flash-lite is the default (extraction, classification, fraud signals); flash is
reserved for planning, R-06 tiebreaks, and customer letters — the few places
where quality is worth the scarcer quota.
"""

from __future__ import annotations

from enum import StrEnum


class ModelName(StrEnum):
    FLASH = "gemini-2.5-flash"
    FLASH_LITE = "gemini-2.5-flash-lite"


EMBEDDING_MODEL = "gemini-embedding-001"

# Free-tier requests-per-minute ceilings the token bucket enforces.
RPM_LIMITS: dict[ModelName, int] = {
    ModelName.FLASH: 10,
    ModelName.FLASH_LITE: 15,
}


class TaskKind(StrEnum):
    EXTRACT = "extract"
    CLASSIFY = "classify"
    FRAUD = "fraud"
    PLAN = "plan"
    TIEBREAK = "tiebreak"
    LETTER = "letter"
    DEBUG = "debug"


# The tiering policy in one table so it is auditable and testable.
_TASK_MODEL: dict[TaskKind, ModelName] = {
    TaskKind.EXTRACT: ModelName.FLASH_LITE,
    TaskKind.CLASSIFY: ModelName.FLASH_LITE,
    TaskKind.FRAUD: ModelName.FLASH_LITE,
    TaskKind.DEBUG: ModelName.FLASH_LITE,
    TaskKind.PLAN: ModelName.FLASH,
    TaskKind.TIEBREAK: ModelName.FLASH,
    TaskKind.LETTER: ModelName.FLASH,
}


def model_for_task(task: TaskKind) -> ModelName:
    return _TASK_MODEL[task]


def downgrade(_model: ModelName) -> ModelName:
    """Downgrade target on repeated rate-limiting. flash-lite is the cheapest
    tier and the only downgrade destination; the caller stops downgrading once
    it reaches flash-lite (see client._invoke)."""
    return ModelName.FLASH_LITE
