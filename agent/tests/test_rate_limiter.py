"""Unit tests for the token-bucket rate limiter (Phase 0 acceptance: 'make test
includes at least rate-limiter unit tests'). The clock is faked so no real time
passes."""

from __future__ import annotations

import asyncio

import pytest

from adjuster_zero.llm.rate_limiter import TokenBucket


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_initial_burst_up_to_capacity() -> None:
    clock = FakeClock()
    b = TokenBucket(60, clock=clock)  # 60/min -> capacity 60, 1 token/sec
    for _ in range(60):
        assert b.try_acquire() is True
    # bucket now empty
    assert b.try_acquire() is False


def test_refill_is_time_proportional() -> None:
    clock = FakeClock()
    b = TokenBucket(60, clock=clock)  # 1 token/sec
    for _ in range(60):
        assert b.try_acquire()
    assert b.try_acquire() is False
    clock.advance(5.0)  # 5 tokens back
    for _ in range(5):
        assert b.try_acquire() is True
    assert b.try_acquire() is False


def test_capacity_caps_accumulation() -> None:
    clock = FakeClock()
    b = TokenBucket(60, clock=clock)
    clock.advance(10_000)  # would overfill, but capacity caps at 60
    assert b.tokens <= 60
    taken = sum(1 for _ in range(100) if b.try_acquire())
    assert taken == 60


def test_time_until_available_math() -> None:
    clock = FakeClock()
    b = TokenBucket(60, clock=clock)  # 1 token/sec
    for _ in range(60):
        b.try_acquire()
    # need 1 token, refill 1/sec -> ~1s
    assert b.time_until_available(1) == pytest.approx(1.0, abs=1e-6)
    # need 3 tokens -> ~3s
    assert b.time_until_available(3) == pytest.approx(3.0, abs=1e-6)


def test_flash_vs_flash_lite_limits() -> None:
    from adjuster_zero.llm.models import RPM_LIMITS, ModelName

    assert RPM_LIMITS[ModelName.FLASH] == 10
    assert RPM_LIMITS[ModelName.FLASH_LITE] == 15


def test_acquire_waits_and_reports_elapsed() -> None:
    clock = FakeClock()
    slept: list[float] = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)
        clock.advance(s)  # advancing the clock refills the bucket

    async def run() -> float:
        b = TokenBucket(60, clock=clock)
        for _ in range(60):
            b.try_acquire()
        # now empty; acquiring 2 should sleep ~2s total (possibly in chunks)
        return await b.acquire(2, sleep=fake_sleep)

    waited = asyncio.run(run())
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert sum(slept) == pytest.approx(2.0, abs=1e-6)


def test_zero_rate_rejected() -> None:
    with pytest.raises(ValueError):
        TokenBucket(0)
