"""不存在帳號的登入失敗計數(Redis,規格審查 #7)。

存在的帳號把計數寫在 users 表——Redis 重啟就清空所有鎖定,那會是暴力破解防護的
一個可被主動觸發的旁路。不存在的帳號沒有列可以寫,只能放 Redis;但那些帳號本來
就沒有東西可以被破解,所以 Redis 不可用時 **fail-open**(§2.3),
與 10_錯誤處理與狀態規範.md 的限流採同一個取捨。

兩條路徑在外部無法區分:回應、錯誤碼、retry_after_seconds 都一致。
"""

import logging
from typing import Protocol

from app.domains.accounts.application.ports import LoginAttemptTracker

logger = logging.getLogger(__name__)

FAILURE_KEY = "login:fail:{email}"
LOCK_KEY = "login:lock:{email}"


class RedisLike(Protocol):
    """只用到的那幾個 Redis 指令。整個 redis 客戶端型別不該滲進來。"""

    async def incr(self, name: str) -> int: ...

    async def expire(self, name: str, time: int) -> bool: ...

    async def ttl(self, name: str) -> int: ...

    async def set(self, name: str, value: str, ex: int) -> bool | None: ...

    async def delete(self, *names: str) -> int: ...


class RedisLoginAttemptTracker(LoginAttemptTracker):
    def __init__(self, redis: RedisLike) -> None:
        self._redis = redis

    async def remaining_lockout_seconds(self, email: str) -> int:
        try:
            ttl = await self._redis.ttl(LOCK_KEY.format(email=email))
        except Exception:
            logger.warning("login attempt store unavailable; failing open")
            return 0
        # -2 = key 不存在,-1 = 沒有 TTL(不該發生,但別讓它變成負數秒數)
        return ttl if ttl > 0 else 0

    async def register_failure(
        self, email: str, *, max_attempts: int, lockout_seconds: int
    ) -> int:
        failure_key = FAILURE_KEY.format(email=email)
        try:
            count = await self._redis.incr(failure_key)
            if count == 1:
                # 計數窗從第一次失敗起算,與鎖定長度同步
                await self._redis.expire(failure_key, lockout_seconds)
            if count < max_attempts:
                return 0
            await self._redis.set(
                LOCK_KEY.format(email=email), "1", ex=lockout_seconds
            )
            await self._redis.delete(failure_key)
            return lockout_seconds
        except Exception:
            logger.warning("login attempt store unavailable; failing open")
            return 0
