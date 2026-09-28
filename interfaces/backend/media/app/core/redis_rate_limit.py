"""RateLimitCounter 的 Redis 實作(01_資料模型與儲存規格.md 第 7.1 節)。

計數窗從第一次請求起算:INCR 後若回傳 1,代表這個 key 是新建的,才設 TTL。
連不到 Redis 時由 RateLimiter 的 fail-open 接手(13_ADR 第 4 節)——限流是保護機制,
不該讓它自己的故障變成阻斷全站的原因。
"""

from redis.asyncio import Redis

from app.core.rate_limit import RateLimitCounter


class RedisRateLimitCounter(RateLimitCounter):
    def __init__(self, redis_url: str) -> None:
        self._redis: Redis = Redis.from_url(redis_url)

    async def hit(self, key: str, *, window_seconds: int) -> int:
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, window_seconds)
        return int(count)

    async def aclose(self) -> None:
        await self._redis.aclose()
