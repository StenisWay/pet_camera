"""全站請求限流(10_錯誤處理與狀態規範.md 第 3 節,RATE_001)。

計數放在 VM-3 的共用 Redis,key 形狀見 01_資料模型與儲存規格.md 第 7.1 節。
Redis 連不到時 **fail-open** 直接放行——限流是保護機制,不該讓它自己的故障變成阻斷
全站的原因(13_ADR 第 4 節)。

Media 的限流額度比其他服務嚴格(規格審查 #15):擷幀與 ffmpeg 轉碼吃的是 VM-3 的
2 OCPU,而那是全系統唯一的瓶頸(13_ADR 第 6 節)。
"""

import logging
from abc import ABC, abstractmethod

from app.shared_kernel.errors import RateLimited

logger = logging.getLogger(__name__)

RATE_LIMIT_KEY = "ratelimit:{identity}:{endpoint}"


class RateLimitCounter(ABC):
    @abstractmethod
    async def hit(self, key: str, *, window_seconds: int) -> int:
        """遞增並回傳目前計數;key 不存在時一併設定 TTL,計數窗從第一次請求起算。"""


class RateLimiter:
    def __init__(self, counter: RateLimitCounter, *, limit: int, window_seconds: int) -> None:
        self.counter = counter
        self.limit = limit
        self.window_seconds = window_seconds

    async def check(self, identity: str, *, endpoint: str) -> None:
        key = RATE_LIMIT_KEY.format(identity=identity, endpoint=endpoint)
        try:
            count = await self.counter.hit(key, window_seconds=self.window_seconds)
        except Exception:
            logger.warning("rate limit store unavailable, failing open for %s", endpoint)
            return
        if count > self.limit:
            raise RateLimited()
