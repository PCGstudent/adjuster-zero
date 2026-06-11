"""A small async token-bucket rate limiter.

One bucket per model enforces the free-tier RPM ceiling so we never *cause* a
429 ourselves (we still handle provider-side 429s with backoff in the client).
The clock is injectable so the limiter is unit-testable without sleeping.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable


class TokenBucket:
    def __init__(
        self,
        rate_per_min: float,
        *,
        capacity: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate_per_min <= 0:
            raise ValueError("rate_per_min must be positive")
        self.refill_per_sec = rate_per_min / 60.0
        self.capacity = float(capacity) if capacity is not None else float(rate_per_min)
        self.tokens = self.capacity
        self._clock = clock
        self._last = clock()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._last = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)

    def try_acquire(self, n: float = 1.0) -> bool:
        """Non-blocking; returns True if ``n`` tokens were available and taken."""
        self._refill()
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False

    def time_until_available(self, n: float = 1.0) -> float:
        """Seconds until ``n`` tokens would be available (0.0 if available now)."""
        self._refill()
        if self.tokens >= n:
            return 0.0
        return (n - self.tokens) / self.refill_per_sec

    async def acquire(
        self,
        n: float = 1.0,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> float:
        """Block until ``n`` tokens are available. Returns seconds waited."""
        waited = 0.0
        async with self._lock:
            while not self.try_acquire(n):
                delay = self.time_until_available(n)
                waited += delay
                await sleep(delay)
        return waited
