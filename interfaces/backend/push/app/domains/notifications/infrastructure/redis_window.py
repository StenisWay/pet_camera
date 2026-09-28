"""NotificationWindow 的 Redis 實作(09_spec 第 2.3 節)。

key 形狀見 01_資料模型與儲存規格.md 第 7.1 節:push:window:{device_id},TTL 5 分鐘。
INCR 是原子操作,VM-1/VM-2 兩份複本同時處理同一裝置的事件也不會算錯。
Redis 連不到時的降級(視為首發)在 use case,這裡只負責計數。
"""

from __future__ import annotations

import uuid
from typing import Any

import redis.asyncio as redis

from app.domains.notifications.application.ports import NotificationWindow

WINDOW_KEY = "push:window:{device_id}"


class RedisNotificationWindow(NotificationWindow):
    def __init__(self, url: str, *, window_seconds: int) -> None:
        self._client: Any = redis.from_url(url, decode_responses=True)
        self._window_seconds = window_seconds

    @classmethod
    def with_client(cls, client: Any, *, window_seconds: int) -> RedisNotificationWindow:
        window = cls.__new__(cls)
        window._client = client
        window._window_seconds = window_seconds
        return window

    async def register(self, device_id: uuid.UUID) -> int:
        key = WINDOW_KEY.format(device_id=device_id)
        pipeline = self._client.pipeline(transaction=True)
        pipeline.incr(key)
        # nx:只在 key 還沒有 TTL 時設定,窗口從第一個事件起算,不被後續事件延長
        pipeline.expire(key, self._window_seconds, nx=True)
        count, _ = await pipeline.execute()
        return int(count)

    async def aclose(self) -> None:
        await self._client.aclose()
