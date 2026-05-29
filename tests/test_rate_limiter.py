"""Token-bucket rate limiter tests with an injectable clock."""

from __future__ import annotations

from home_photo_repo.llm.rate_limiter import TokenBucket


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_burst_capacity_allows_immediate_n_calls() -> None:
    clock = FakeClock()
    b = TokenBucket(rate_per_minute=60, capacity=10, clock=clock.time, sleep=clock.sleep)
    for _ in range(10):
        b.acquire()
    assert clock.sleeps == []  # all 10 within burst, no sleep


def test_exceeding_capacity_sleeps_until_refill() -> None:
    clock = FakeClock()
    b = TokenBucket(rate_per_minute=60, capacity=1, clock=clock.time, sleep=clock.sleep)
    b.acquire()  # consume the one token
    b.acquire()  # must sleep ~1 second to refill at 60/min
    assert len(clock.sleeps) == 1
    assert 0.95 <= clock.sleeps[0] <= 1.05  # within rounding


def test_refill_recovers_tokens_over_time() -> None:
    clock = FakeClock()
    b = TokenBucket(rate_per_minute=120, capacity=2, clock=clock.time, sleep=clock.sleep)
    b.acquire()
    b.acquire()
    clock.now += 2.0  # 4 tokens accrued at 120/min, but capped at capacity=2
    b.acquire()
    b.acquire()
    assert clock.sleeps == []


def test_acquire_n_consumes_multiple() -> None:
    clock = FakeClock()
    b = TokenBucket(rate_per_minute=60, capacity=5, clock=clock.time, sleep=clock.sleep)
    b.acquire(3)
    b.acquire(2)
    assert clock.sleeps == []
    b.acquire(1)  # bucket now empty, must wait
    assert len(clock.sleeps) == 1
