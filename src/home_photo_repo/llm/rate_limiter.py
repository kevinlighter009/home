"""Token-bucket rate limiter with injectable time/sleep for tests."""

from __future__ import annotations

import time as _time
from collections.abc import Callable


class TokenBucket:
    """Simple token-bucket rate limiter.

    `rate_per_minute` tokens refill continuously, up to `capacity`. Each
    `acquire(n)` call consumes n tokens, sleeping if necessary. The
    `clock`/`sleep` callables are injectable so tests don't actually sleep.
    """

    def __init__(
        self,
        *,
        rate_per_minute: float,
        capacity: int,
        clock: Callable[[], float] = _time.monotonic,
        sleep: Callable[[float], None] = _time.sleep,
    ) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._rate_per_sec = rate_per_minute / 60.0
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._last = clock()
        self._clock = clock
        self._sleep = sleep

    def acquire(self, n: int = 1) -> None:
        if n <= 0:
            raise ValueError("n must be positive")
        if n > self._capacity:
            raise ValueError(f"n={n} exceeds capacity={self._capacity}")
        self._refill()
        if self._tokens >= n:
            self._tokens -= n
            return
        deficit = n - self._tokens
        wait_sec = deficit / self._rate_per_sec
        self._sleep(wait_sec)
        self._refill()
        self._tokens -= n

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._last
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate_per_sec)
            self._last = now


__all__ = ["TokenBucket"]
