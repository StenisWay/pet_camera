"""測試替身。每個 port 都有一個 fake,與正式實作跑同一份合約測試。

fake 刻意保留真實實作的重要行為(到期即消失、接管時舊 session 失效),
否則用 fake 寫出來的 use case 測試會漏掉真正會出事的情境。
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from app.core.rate_limit import RateLimitCounter
from app.domains.streaming.application.ports import (
    DeviceDirectory,
    SignalingEvents,
    TurnCredentialIssuer,
)
from app.domains.streaming.domain.entities import StreamSession
from app.domains.streaming.domain.repositories import StreamSessionRepository
from app.domains.streaming.domain.value_objects import DeviceSnapshot, TurnCredentials
from app.shared_kernel.errors import ServiceUnavailable
from app.shared_kernel.ports import Clock, IdGenerator


class FakeClock(Clock):
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


class FixedIdGenerator(IdGenerator):
    def __init__(self, *ids: uuid.UUID) -> None:
        self._ids = list(ids)

    def new_id(self) -> uuid.UUID:
        return self._ids.pop(0) if self._ids else uuid.uuid4()


class InMemoryStreamSessionRepository(StreamSessionRepository):
    """Redis 實作的記憶體版。

    TTL 以 session.expires_at 模擬(Redis 靠 key TTL),接管以裝置索引模擬
    (Redis 靠覆寫 stream:device:{id} 並刪除舊 key)。
    """

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self._sessions: dict[uuid.UUID, StreamSession] = {}
        self._device_index: dict[uuid.UUID, uuid.UUID] = {}

    async def get(self, session_id: uuid.UUID) -> StreamSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired(self.clock.now()):
            self._evict(session_id)
            return None
        # 回傳副本:Redis 的 get 一定是反序列化出來的新物件,不共用參照
        return deepcopy(session)

    async def get_active_for_device(self, device_id: uuid.UUID) -> StreamSession | None:
        session_id = self._device_index.get(device_id)
        if session_id is None:
            return None
        return await self.get(session_id)

    async def save(self, session: StreamSession) -> None:
        previous = self._device_index.get(session.device_id)
        if previous is not None and previous != session.id:
            self._sessions.pop(previous, None)
        self._sessions[session.id] = deepcopy(session)
        self._device_index[session.device_id] = session.id

    async def delete(self, session_id: uuid.UUID) -> None:
        self._evict(session_id)

    def _evict(self, session_id: uuid.UUID) -> None:
        session = self._sessions.pop(session_id, None)
        if session is not None and self._device_index.get(session.device_id) == session_id:
            del self._device_index[session.device_id]


class UnavailableStreamSessionRepository(StreamSessionRepository):
    """Redis 不可用。第 7 節:讀寫回 SRV_002,DELETE 例外採 fail-open。"""

    async def get(self, session_id: uuid.UUID) -> StreamSession | None:
        raise ServiceUnavailable()

    async def get_active_for_device(self, device_id: uuid.UUID) -> StreamSession | None:
        raise ServiceUnavailable()

    async def save(self, session: StreamSession) -> None:
        raise ServiceUnavailable()

    async def delete(self, session_id: uuid.UUID) -> None:
        raise ServiceUnavailable()


class FakeDeviceDirectory(DeviceDirectory):
    def __init__(self, *devices: DeviceSnapshot, unavailable: bool = False) -> None:
        self._by_id = {device.device_id: device for device in devices}
        self.unavailable = unavailable

    async def find(self, device_id: uuid.UUID) -> DeviceSnapshot | None:
        if self.unavailable:
            raise ServiceUnavailable()
        return self._by_id.get(device_id)


class FakeTurnCredentialIssuer(TurnCredentialIssuer):
    def __init__(self, *, ttl: timedelta = timedelta(seconds=600)) -> None:
        self.ttl = ttl
        self.issued_for: list[uuid.UUID] = []

    async def issue(self, session_id: uuid.UUID, now: datetime) -> TurnCredentials:
        self.issued_for.append(session_id)
        return TurnCredentials(
            urls=("turn:vm3.internal:3478?transport=udp",),
            username=f"{int((now + self.ttl).timestamp())}:{session_id}",
            credential="ZmFrZS1jcmVkZW50aWFs",
            expires_at=now + self.ttl,
        )


class FakeSignalingEvents(SignalingEvents):
    """以 asyncio.Event 模擬跨複本喚醒。

    on_wait_for_answer 讓測試安排「鏡頭端在觀看端開始等待之後才回覆」——這是真實
    的時序,先把 answer 寫好再 submit_offer 反而測不到東西(submit_offer 會作廢
    上一輪的 answer)。
    """

    def __init__(
        self,
        *,
        on_wait_for_answer: Callable[[uuid.UUID], Awaitable[None]] | None = None,
        on_wait_for_offer: Callable[[uuid.UUID], Awaitable[None]] | None = None,
    ) -> None:
        self.on_wait_for_answer = on_wait_for_answer
        self.on_wait_for_offer = on_wait_for_offer
        self.announced_answers: list[uuid.UUID] = []
        self.announced_offers: list[uuid.UUID] = []
        self.answer_waits: list[tuple[uuid.UUID, timedelta]] = []
        self.offer_waits: list[tuple[uuid.UUID, timedelta]] = []
        self._answers: dict[uuid.UUID, asyncio.Event] = {}
        self._offers: dict[uuid.UUID, asyncio.Event] = {}

    async def wait_for_answer(self, session_id: uuid.UUID, max_wait: timedelta) -> bool:
        self.answer_waits.append((session_id, max_wait))
        if self.on_wait_for_answer is not None:
            await self.on_wait_for_answer(session_id)
        return await self._wait(self._event(self._answers, session_id), max_wait)

    async def announce_answer(self, session_id: uuid.UUID) -> None:
        self.announced_answers.append(session_id)
        self._event(self._answers, session_id).set()

    async def wait_for_offer(self, device_id: uuid.UUID, max_wait: timedelta) -> bool:
        self.offer_waits.append((device_id, max_wait))
        if self.on_wait_for_offer is not None:
            await self.on_wait_for_offer(device_id)
        return await self._wait(self._event(self._offers, device_id), max_wait)

    async def announce_offer(self, device_id: uuid.UUID) -> None:
        self.announced_offers.append(device_id)
        self._event(self._offers, device_id).set()

    @staticmethod
    def _event(registry: dict[uuid.UUID, asyncio.Event], key: uuid.UUID) -> asyncio.Event:
        return registry.setdefault(key, asyncio.Event())

    @staticmethod
    async def _wait(event: asyncio.Event, max_wait: timedelta) -> bool:
        if event.is_set():
            return True
        try:
            await asyncio.wait_for(event.wait(), max_wait.total_seconds())
        except TimeoutError:
            return False
        return True


class FakeRateLimitCounter(RateLimitCounter):
    def __init__(self, *, unavailable: bool = False) -> None:
        self.counts: dict[str, int] = {}
        self.unavailable = unavailable

    async def hit(self, key: str, *, window_seconds: int) -> int:
        if self.unavailable:
            raise ConnectionError("redis down")
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)  # type: ignore[arg-type]
