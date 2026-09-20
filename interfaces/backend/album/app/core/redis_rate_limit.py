"""RateLimitCounter 的 Redis 實作。

key 形狀見 01_資料模型與儲存規格.md 第 7.1 節:ratelimit:{user_id 或 ip}:{endpoint}。
fail-open 的判斷在 core/rate_limit.py,這裡只負責計數。
"""

import redis.asyncio as redis

from app.core.rate_limit import RateLimitCounter


class RedisRateLimitCounter(RateLimitCounter):
    def __init__(self, url: str) -> None:
        self._client = redis.from_url(url, decode_responses=True)

    async def hit(self, key: str, *, window_seconds: int) -> int:
        pipeline = self._client.pipeline()
        pipeline.incr(key)
        # nx:只在 key 還沒有 TTL 時設定,讓計數窗從第一次請求起算,不被後續請求延長
        pipeline.expire(key, window_seconds, nx=True)
        count, _ = await pipeline.execute()
        return int(count)

    async def aclose(self) -> None:
        await self._client.aclose()
