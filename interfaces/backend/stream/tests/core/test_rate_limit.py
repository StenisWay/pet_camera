"""限流與它的 fail-open 取捨(10_錯誤處理與狀態規範.md 第 3 節、13_ADR 第 4 節)。"""

import pytest

from app.core.rate_limit import RATE_LIMIT_KEY, RateLimiter
from app.shared_kernel.errors import RateLimited
from tests.domains.streaming.fakes import FakeRateLimitCounter

ENDPOINT = "POST /devices/{id}/stream/session"


async def test_allows_up_to_the_limit() -> None:
    limiter = RateLimiter(FakeRateLimitCounter(), limit=10, window_seconds=60)

    for _ in range(10):
        await limiter.check("alice", endpoint=ENDPOINT)


async def test_rejects_beyond_the_limit() -> None:
    limiter = RateLimiter(FakeRateLimitCounter(), limit=10, window_seconds=60)
    for _ in range(10):
        await limiter.check("alice", endpoint=ENDPOINT)

    with pytest.raises(RateLimited):
        await limiter.check("alice", endpoint=ENDPOINT)


async def test_counts_per_identity_and_endpoint() -> None:
    """一位使用者用滿額度,不該影響另一位,也不該影響其他端點。"""
    counter = FakeRateLimitCounter()
    limiter = RateLimiter(counter, limit=1, window_seconds=60)

    await limiter.check("alice", endpoint=ENDPOINT)
    await limiter.check("bob", endpoint=ENDPOINT)
    await limiter.check("alice", endpoint="DELETE /devices/{id}/stream/session/{sid}")

    assert set(counter.counts) == {
        RATE_LIMIT_KEY.format(identity="alice", endpoint=ENDPOINT),
        RATE_LIMIT_KEY.format(identity="bob", endpoint=ENDPOINT),
        RATE_LIMIT_KEY.format(
            identity="alice", endpoint="DELETE /devices/{id}/stream/session/{sid}"
        ),
    }


async def test_store_outage_fails_open() -> None:
    """限流是保護機制,不該讓它自己的故障變成阻斷使用者看直播的原因。

    這與 session 讀寫的 fail-closed 是刻意的不同取捨:限流失效只是少一層保護,
    session 讀錯卻會把使用者接到別人的連線上。
    """
    limiter = RateLimiter(FakeRateLimitCounter(unavailable=True), limit=1, window_seconds=60)

    for _ in range(5):
        await limiter.check("alice", endpoint=ENDPOINT)
