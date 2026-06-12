"""Tool-layer contracts: risk tiers, the uniform result envelope, and the Tool
registry entry."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import IntEnum
from typing import Any

from pydantic import BaseModel


class RiskTier(IntEnum):
    """T0 read-only · T1 reversible writes · T2 money / external comms."""

    T0 = 0
    T1 = 1
    T2 = 2


class ToolError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ToolResult(BaseModel):
    """Uniform envelope returned by every tool execution."""

    ok: bool
    data: dict[str, Any] | None = None
    error: ToolError | None = None
    cached: bool = False

    @classmethod
    def success(cls, data: dict[str, Any], *, cached: bool = False) -> ToolResult:
        return cls(ok=True, data=data, cached=cached)

    @classmethod
    def failure(cls, code: str, message: str, *, retryable: bool = False) -> ToolResult:
        return cls(ok=False, error=ToolError(code=code, message=message, retryable=retryable))


class ToolFailure(Exception):
    """Raised by a handler to signal a business failure (mapped to the envelope)."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.retryable = retryable


class Tool(BaseModel):
    """A registry entry. Handlers are async: (args_model) -> result_model, or
    raise ToolFailure."""

    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str
    args_schema: type[BaseModel]
    result_schema: type[BaseModel]
    risk_tier: RiskTier
    idempotent: bool = False
    handler: Callable[[Any], Awaitable[BaseModel]]
