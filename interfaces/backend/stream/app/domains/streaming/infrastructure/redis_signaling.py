"""SignalingEvents 的 Redis Pub/Sub 實作。

為什麼需要:VM-1 與 VM-2 各跑一份複本,LB 以請求為單位分流(13_ADR 第 1.1 節)。
觀看端的 offer 與鏡頭端的 answer 很可能落在不同複本,單純 await 本機的 asyncio.Event
永遠等不到對方。

Pub/Sub 不補送:訊息在訂閱之前發布就遺失了。因此 use case **不把通知當成真相**——
等待結束後一律重讀一次 Redis 裡的 session,通知只是「可以早點去看」的提示。
"""

import asyncio
import uuid
from datetime import timedelta

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.domains.streaming.application.ports import SignalingEvents
from app.shared_kernel.errors import ServiceUnavailable

ANSWER_CHANNEL = "stream:answer:{session_id}"
OFFER_CHANNEL = "stream:offer:{device_id}"


class RedisSignalingEvents(SignalingEvents):
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    async def wait_for_answer(self, session_id: uuid.UUID, max_wait: timedelta) -> bool:
        return await self._wait(ANSWER_CHANNEL.format(session_id=session_id), max_wait)

    async def announce_answer(self, session_id: uuid.UUID) -> None:
        await self._publish(ANSWER_CHANNEL.format(session_id=session_id))

    async def wait_for_offer(self, device_id: uuid.UUID, max_wait: timedelta) -> bool:
        return await self._wait(OFFER_CHANNEL.format(device_id=device_id), max_wait)

    async def announce_offer(self, device_id: uuid.UUID) -> None:
        await self._publish(OFFER_CHANNEL.format(device_id=device_id))

    async def _wait(self, channel: str, max_wait: timedelta) -> bool:
        try:
            pubsub = self._client.pubsub()
            await pubsub.subscribe(channel)
        except RedisError as exc:
            raise ServiceUnavailable() from exc

        loop = asyncio.get_running_loop()
        deadline = loop.time() + max_wait.total_seconds()
        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return False
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=remaining
                )
                if message is not None:
                    return True
        except RedisError as exc:
            raise ServiceUnavailable() from exc
        finally:
            await _quietly_close(pubsub, channel)

    async def _publish(self, channel: str) -> None:
        try:
            await self._client.publish(channel, "1")
        except RedisError as exc:
            raise ServiceUnavailable() from exc


async def _quietly_close(pubsub: redis.client.PubSub, channel: str) -> None:
    """收尾失敗不該蓋掉真正的結果——連線已經壞了的話,呼叫端下一次操作自然會發現。"""
    try:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
    except (RedisError, OSError):
        pass
