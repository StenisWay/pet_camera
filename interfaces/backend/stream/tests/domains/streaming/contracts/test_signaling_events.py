"""SignalingEvents 的合約測試。

fake 與 Redis Pub/Sub 兩個實作跑同一份。Redis 版需要真實 Redis,標記 integration,
預設不執行(uv run pytest -m integration,需 TEST_REDIS_URL)。

合約刻意**不**保證「通知一定送達」——Pub/Sub 不補送。保證的只有:
有人在等、而且通知發生在等待期間時,等待會提早結束。use case 因此不把通知當成真相,
等待結束後一律重讀 session(見 submit_offer.py)。
"""

import asyncio
import os
from datetime import timedelta

import pytest

from app.domains.streaming.application.ports import SignalingEvents
from tests.domains.streaming.builders import DEVICE_A, SESSION_A
from tests.domains.streaming.fakes import FakeSignalingEvents

SHORT = timedelta(milliseconds=50)
LONG = timedelta(seconds=2)


class SignalingEventsContract:
    @pytest.fixture
    def events(self) -> SignalingEvents:
        raise NotImplementedError

    async def test_waiting_for_an_answer_that_never_comes_times_out(
        self, events: SignalingEvents
    ) -> None:
        assert await events.wait_for_answer(SESSION_A, SHORT) is False

    async def test_waiting_for_an_offer_that_never_comes_times_out(
        self, events: SignalingEvents
    ) -> None:
        assert await events.wait_for_offer(DEVICE_A, SHORT) is False

    async def test_an_answer_announced_while_waiting_wakes_the_waiter(
        self, events: SignalingEvents
    ) -> None:
        waiter = asyncio.create_task(events.wait_for_answer(SESSION_A, LONG))
        await asyncio.sleep(0.05)  # 確定訂閱已經生效再發布
        await events.announce_answer(SESSION_A)

        assert await waiter is True

    async def test_an_offer_announced_while_waiting_wakes_the_waiter(
        self, events: SignalingEvents
    ) -> None:
        waiter = asyncio.create_task(events.wait_for_offer(DEVICE_A, LONG))
        await asyncio.sleep(0.05)
        await events.announce_offer(DEVICE_A)

        assert await waiter is True

    async def test_announcing_with_nobody_waiting_is_not_an_error(
        self, events: SignalingEvents
    ) -> None:
        """觀看端可能已經放棄了,鏡頭端仍會回 answer。這不該炸掉鏡頭端的請求。"""
        await events.announce_answer(SESSION_A)
        await events.announce_offer(DEVICE_A)


class TestFakeSignalingEvents(SignalingEventsContract):
    @pytest.fixture
    def events(self) -> SignalingEvents:
        return FakeSignalingEvents()


@pytest.mark.integration
class TestRedisSignalingEvents(SignalingEventsContract):
    @pytest.fixture
    async def events(self):  # type: ignore[no-untyped-def]
        import redis.asyncio as redis

        from app.domains.streaming.infrastructure.redis_signaling import RedisSignalingEvents

        url = os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
        client = redis.from_url(url, decode_responses=True)
        try:
            yield RedisSignalingEvents(client)
        finally:
            await client.aclose()

    async def test_a_notification_published_before_subscribing_is_lost(self, events) -> None:  # type: ignore[no-untyped-def]
        """Pub/Sub 不補送——這是刻意記錄下來的限制,不是缺陷。

        正因為如此,use case 等待結束後一律重讀 session:通知只是「可以早點去看」
        的提示,真相在 Redis 的 session key 裡。
        """
        await events.announce_answer(SESSION_A)

        assert await events.wait_for_answer(SESSION_A, SHORT) is False
