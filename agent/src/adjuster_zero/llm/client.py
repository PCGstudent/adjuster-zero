"""GeminiClient — the single funnel for every LLM call.

Responsibilities (CLAUDE.md free-tier rules + theses 3 & 9):
  * model tiering (flash vs flash-lite) via TaskKind
  * token-bucket rate limiting per model (never self-inflict a 429)
  * structured output validated against a Pydantic schema, with exactly ONE
    repair retry (validator errors fed back), then EscalateToHuman
  * 429 → exponential backoff → automatic flash→flash-lite downgrade, each step
    surfaced through an optional event sink so the claim timeline can show
    "rate-limited, retrying"
  * persisted daily RPD/token counters in llm_usage

The client is process-global (get_client) but takes an optional per-call event
sink so a running claim can route limiter events onto its own timeline.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .. import db
from ..config import get_settings
from .errors import EscalateToHuman, SchemaRepairFailed
from .models import EMBEDDING_MODEL, RPM_LIMITS, ModelName, TaskKind, downgrade, model_for_task
from .rate_limiter import TokenBucket

T = TypeVar("T", bound=BaseModel)

# Async event sink: (event_type, data) -> awaitable. Optional everywhere.
EventSink = Callable[[str, dict[str, Any]], Awaitable[None]]

_MAX_429_ATTEMPTS = 4
_BASE_BACKOFF_SEC = 1.0


@dataclass
class LLMCallMeta:
    """Everything the decision log needs about one LLM call (thesis 9)."""

    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    repaired: bool = False
    downgraded: bool = False
    rate_limited_waits: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class GeminiClient:
    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.gemini_api_key
        self._client: Any | None = None  # lazily created google.genai.Client
        self._buckets: dict[ModelName, TokenBucket] = {
            m: TokenBucket(rpm) for m, rpm in RPM_LIMITS.items()
        }

    # -- google-genai client is created lazily so the module imports without a key
    def _genai(self) -> Any:
        if self._client is None:
            if not self._api_key:
                raise EscalateToHuman(
                    "LLM_UNCONFIGURED", "GEMINI_API_KEY is not set; cannot call the model"
                )
            from google import genai  # imported lazily to keep import-time light

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def _emit(self, sink: EventSink | None, event_type: str, data: dict[str, Any]) -> None:
        if sink is not None:
            await sink(event_type, data)

    async def _invoke(
        self,
        model: ModelName,
        contents: Any,
        schema: type[BaseModel],
        system: str | None,
        temperature: float,
        sink: EventSink | None,
        meta: LLMCallMeta,
    ) -> str:
        """One generate_content call wrapped in rate-limiting + 429 backoff +
        downgrade. Returns the raw JSON text; validation happens in the caller
        so a schema failure can be distinguished from a transport failure."""
        from google.genai import errors as genai_errors
        from google.genai import types

        current = model
        for attempt in range(_MAX_429_ATTEMPTS):
            await self._buckets[current].acquire()
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                system_instruction=system,
                temperature=temperature,
            )
            try:
                resp = await self._genai().aio.models.generate_content(
                    model=current.value, contents=contents, config=config
                )
            except genai_errors.APIError as exc:
                status = getattr(exc, "code", None)
                retryable = status == 429 or (isinstance(status, int) and 500 <= status < 600)
                if not retryable or attempt == _MAX_429_ATTEMPTS - 1:
                    raise EscalateToHuman(
                        "LLM_TRANSPORT", f"Gemini call failed ({status})", detail=str(exc)
                    ) from exc
                meta.rate_limited_waits += 1
                backoff = _BASE_BACKOFF_SEC * (2**attempt)
                await self._emit(
                    sink, "llm.rate_limited",
                    {"model": current.value, "status": status, "retry_in_s": backoff},
                )
                # On the second strike, downgrade flash → flash-lite (more quota).
                if attempt >= 1 and current is ModelName.FLASH:
                    current = downgrade(current)
                    meta.downgraded = True
                    await self._emit(sink, "llm.downgraded", {"to": current.value})
                await asyncio.sleep(backoff)
                continue

            # success
            usage = getattr(resp, "usage_metadata", None)
            meta.model = current.value
            meta.tokens_in = getattr(usage, "prompt_token_count", 0) or 0
            meta.tokens_out = getattr(usage, "candidates_token_count", 0) or 0
            await db.increment_rpd(
                current.value, tokens_in=meta.tokens_in, tokens_out=meta.tokens_out
            )
            text = resp.text
            if text is None:
                raise EscalateToHuman("LLM_EMPTY", "Gemini returned no text")
            return text

        # Unreachable in practice (the final retryable attempt raises above);
        # kept so the function provably returns str on all paths.
        raise EscalateToHuman("LLM_RATE_LIMITED", "Exhausted 429 backoff attempts")

    async def generate_structured(
        self,
        task: TaskKind,
        prompt: str,
        schema: type[T],
        *,
        system: str | None = None,
        temperature: float = 0.0,
        event_sink: EventSink | None = None,
    ) -> tuple[T, LLMCallMeta]:
        """Generate JSON validated against ``schema``. Exactly one repair retry,
        then SchemaRepairFailed (an EscalateToHuman subclass)."""
        model = model_for_task(task)
        meta = LLMCallMeta(model=model.value)
        started = time.perf_counter()

        contents: Any = prompt
        last_errors = ""
        last_raw = ""
        # iteration 0 = original, iteration 1 = the single repair attempt
        for iteration in range(2):
            text = await self._invoke(model, contents, schema, system, temperature, event_sink, meta)
            last_raw = text
            try:
                obj = schema.model_validate_json(text)
                meta.latency_ms = int((time.perf_counter() - started) * 1000)
                meta.repaired = iteration > 0
                return obj, meta
            except ValidationError as exc:
                last_errors = exc.json()
                if iteration == 0:
                    await self._emit(
                        event_sink, "llm.schema_repair", {"task": task.value}
                    )
                    contents = (
                        f"{prompt}\n\nYour previous response was invalid JSON for the "
                        f"required schema. Validator errors:\n{last_errors}\n\n"
                        f"Previous response:\n{text}\n\n"
                        "Return ONLY corrected JSON that satisfies the schema."
                    )
        raise SchemaRepairFailed(last_errors, raw=last_raw)

    async def embed(
        self, texts: Sequence[str], *, task_type: str = "RETRIEVAL_DOCUMENT"
    ) -> list[list[float]]:
        """Embed texts with gemini-embedding-001 at EMBED_DIM (768) to match the
        pgvector column. <3072-dim outputs need re-normalizing for cosine."""
        import math

        from google.genai import types

        from ..rag.embed import EMBED_DIM

        await self._buckets[ModelName.FLASH_LITE].acquire()
        resp = await self._genai().aio.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=list(texts),
            config=types.EmbedContentConfig(
                task_type=task_type, output_dimensionality=EMBED_DIM
            ),
        )
        await db.increment_rpd(EMBEDDING_MODEL)
        out: list[list[float]] = []
        for e in resp.embeddings:
            v = list(e.values)
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out


_client: GeminiClient | None = None


def get_client() -> GeminiClient:
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client
