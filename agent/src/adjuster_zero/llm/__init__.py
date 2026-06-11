"""LLM access layer. ALL Gemini calls go through GeminiClient (thesis: free-tier
discipline + structured-output validation). Never call the SDK directly."""

from .client import GeminiClient, LLMCallMeta, get_client
from .errors import EscalateToHuman, SchemaRepairFailed
from .models import EMBEDDING_MODEL, RPM_LIMITS, ModelName, TaskKind, model_for_task
from .rate_limiter import TokenBucket

__all__ = [
    "GeminiClient",
    "LLMCallMeta",
    "get_client",
    "EscalateToHuman",
    "SchemaRepairFailed",
    "EMBEDDING_MODEL",
    "RPM_LIMITS",
    "ModelName",
    "TaskKind",
    "model_for_task",
    "TokenBucket",
]
