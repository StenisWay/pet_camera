"""限流的降級行為(13_ADR 第 4 節)。

限流計數在 VM-3 的共用 Redis 上,而服務複本跑在 VM-1/VM-2——跨機連線是常態風險。
規格明定這裡 fail-open:限流是保護機制,不該讓它自己的故障變成阻斷全站的原因
(與 OAuth state 的 fail-closed 是刻意的不同取捨)。
"""

import pytest

from app.core.rate_limit import RateLimitCounter, RateLimiter
from app.shared_kernel.errors import RateLimited
from tests.domains.media.fakes import FakeRateLimitCounter


class BrokenCounter(RateLimitCounter):
    async def hit(self, key: str, *, window_seconds: int) -> int:
        raise ConnectionError("redis unreachable")


async def test_requests_within_the_budget_pass():
    limiter = RateLimiter(FakeRateLimitCounter(), limit=2, window_seconds=60)

    await limiter.check("user-1", endpoint="screenshot")
    await limiter.check("user-1", endpoint="screenshot")


async def test_exceeding_the_budget_is_rejected():
    limiter = RateLimiter(FakeRateLimitCounter(), limit=2, window_seconds=60)
    for _ in range(2):
        await limiter.check("user-1", endpoint="screenshot")

    with pytest.raises(RateLimited):
        await limiter.check("user-1", endpoint="screenshot")


async def test_budgets_are_counted_per_user_and_endpoint():
    """key 形狀見 01_資料模型與儲存規格.md 第 7.1 節。"""
    counter = FakeRateLimitCounter()
    limiter = RateLimiter(counter, limit=1, window_seconds=60)

    await limiter.check("user-1", endpoint="screenshot")
    await limiter.check("user-2", endpoint="screenshot")
    await limiter.check("user-1", endpoint="clip")

    assert set(counter.counts) == {
        "ratelimit:user-1:screenshot",
        "ratelimit:user-2:screenshot",
        "ratelimit:user-1:clip",
    }


async def test_unreachable_redis_fails_open():
    """13_ADR 第 4 節:連不到 Redis 時直接放行,不因限流機制本身故障而阻斷服務。"""
    limiter = RateLimiter(BrokenCounter(), limit=1, window_seconds=60)

    for _ in range(5):
        await limiter.check("user-1", endpoint="screenshot")
