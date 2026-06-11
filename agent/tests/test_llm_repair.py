"""Tests for the structured-output repair contract (thesis 3): exactly ONE
repair retry on schema-validation failure, then EscalateToHuman. We stub the
transport (_invoke) so no network or DB is touched."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel, Field

from adjuster_zero.llm import TaskKind, get_client
from adjuster_zero.llm.client import GeminiClient
from adjuster_zero.llm.errors import SchemaRepairFailed


class Demo(BaseModel):
    label: str
    score: float = Field(ge=0, le=1)


def _make_client_returning(texts: list[str]) -> tuple[GeminiClient, list[int]]:
    client = GeminiClient(api_key="test-key")
    calls = [0]

    async def stub_invoke(model, contents, schema, system, temperature, sink, meta):  # type: ignore[no-untyped-def]
        i = calls[0]
        calls[0] += 1
        meta.model = model.value
        return texts[i]

    client._invoke = stub_invoke  # type: ignore[assignment]
    return client, calls


def test_valid_first_pass_no_repair() -> None:
    client, calls = _make_client_returning(['{"label": "ok", "score": 0.9}'])

    async def run() -> None:
        obj, meta = await client.generate_structured(TaskKind.DEBUG, "p", Demo)
        assert obj.label == "ok"
        assert meta.repaired is False
        assert calls[0] == 1  # no repair call

    asyncio.run(run())


def test_one_repair_then_success() -> None:
    client, calls = _make_client_returning(
        ['{"label": "bad"}', '{"label": "fixed", "score": 0.5}']
    )

    async def run() -> None:
        obj, meta = await client.generate_structured(TaskKind.DEBUG, "p", Demo)
        assert obj.label == "fixed"
        assert meta.repaired is True
        assert calls[0] == 2  # original + exactly one repair

    asyncio.run(run())


def test_two_failures_escalate_no_third_attempt() -> None:
    client, calls = _make_client_returning(['{}', '{"label": "still bad"}'])

    async def run() -> None:
        with pytest.raises(SchemaRepairFailed):
            await client.generate_structured(TaskKind.DEBUG, "p", Demo)
        assert calls[0] == 2  # never a third call

    asyncio.run(run())


def test_get_client_is_singleton() -> None:
    assert get_client() is get_client()
