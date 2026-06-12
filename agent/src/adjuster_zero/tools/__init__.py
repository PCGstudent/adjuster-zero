"""Typed tool layer (blueprint Part 4). A registry maps tool name → schemas +
risk tier + handler; the executor validates args before invoke and result after,
enforces workflow allow-lists and idempotency, and returns a uniform envelope.

We never use framework "auto" tool-calling: the executor disposes (thesis 1)."""

from .base import (
    RiskTier,
    Tool,
    ToolError,
    ToolFailure,
    ToolResult,
)
from .executor import IdempotencyStore, InMemoryIdempotencyStore, ToolExecutor
from .registry import build_registry
from .workflows import WORKFLOW_ALLOWLISTS, tool_allowed

__all__ = [
    "RiskTier",
    "Tool",
    "ToolError",
    "ToolFailure",
    "ToolResult",
    "ToolExecutor",
    "IdempotencyStore",
    "InMemoryIdempotencyStore",
    "build_registry",
    "WORKFLOW_ALLOWLISTS",
    "tool_allowed",
]
