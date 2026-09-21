import pytest

from app.core.rate_limit import RateLimiter
from app.shared_kernel.errors import RateLimited
from tests.fakes import InMemoryRateLimitCounter


@pytest.fixture
def counter() -> InMemoryRateLimitCounter:
    return InMemoryRateLimitCounter()


async def test_requests_under_the_limit_pass(counter):
    limiter = RateLimiter(counter, limit=3, window_seconds=60)

    for _ in range(3):
        await limiter.check("user-1", endpoint="PUT /push-tokens")


async def test_request_over_the_limit_is_rejected(counter):
    limiter = RateLimiter(counter, limit=2, window_seconds=60)
    for _ in range(2):
        await limiter.check("user-1", endpoint="PUT /push-tokens")

    with pytest.raises(RateLimited) as exc:
        await limiter.check("user-1", endpoint="PUT /push-tokens")
    assert exc.value.code == "RATE_001"


async def test_counting_is_per_identity_and_endpoint(counter):
    """01_資料模型與儲存規格.md 第 7.1 節:ratelimit:{user_id 或 ip}:{endpoint}。"""
    limiter = RateLimiter(counter, limit=1, window_seconds=60)
    await limiter.check("user-1", endpoint="PUT /push-tokens")

    await limiter.check("user-2", endpoint="PUT /push-tokens")
    await limiter.check("user-1", endpoint="GET /push-tokens")


async def test_store_failure_fails_open(counter):
    """13_ADR 第 4 節:限流是保護機制,故障時不應讓限流本身變成阻斷全站的原因。"""
    limiter = RateLimiter(counter, limit=1, window_seconds=60)
    counter.available = False

    for _ in range(10):
        await limiter.check("user-1", endpoint="PUT /push-tokens")
