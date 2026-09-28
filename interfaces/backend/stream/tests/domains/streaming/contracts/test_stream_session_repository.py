"""StreamSessionRepository 的合約測試。

domain/repositories.py 的 docstring 就是合約,這裡逐條驗證。fake 與 Redis 兩個實作
跑同一份——用 fake 寫出來的 use case 測試才有意義。

Redis 版需要真實 Redis,標記 integration,預設不執行
(uv run pytest -m integration,需 TEST_REDIS_URL)。
"""

import os
import uuid
from datetime import timedelta

import pytest

from app.domains.streaming.domain.entities import Peer, StreamSession
from app.domains.streaming.domain.repositories import StreamSessionRepository
from tests.domains.streaming.builders import (
    ALICE,
    DEVICE_A,
    NOW,
    SESSION_A,
    SESSION_TTL,
    a_candidate,
    turn_credentials,
)
from tests.domains.streaming.fakes import FakeClock, InMemoryStreamSessionRepository


def a_session(
    *,
    id: uuid.UUID = SESSION_A,
    device_id: uuid.UUID = DEVICE_A,
    ttl: timedelta = SESSION_TTL,
) -> StreamSession:
    return StreamSession.open(
        id=id,
        device_id=device_id,
        owner_id=ALICE,
        turn_credentials=turn_credentials(),
        now=NOW,
        ttl=ttl,
    )


class StreamSessionRepositoryContract:
    """兩個實作共用的合約。子類別只需要提供 repository 與 clock。"""

    @pytest.fixture
    def clock(self) -> FakeClock:
        raise NotImplementedError

    @pytest.fixture
    def repository(self, clock: FakeClock) -> StreamSessionRepository:
        raise NotImplementedError

    async def test_get_returns_none_for_unknown_session(
        self, repository: StreamSessionRepository
    ) -> None:
        assert await repository.get(uuid.uuid4()) is None

    async def test_saved_session_round_trips_with_its_signaling_state(
        self, repository: StreamSessionRepository
    ) -> None:
        """序列化必須保住 SDP 與 candidate,否則跨複本讀回來的 session 是半殘的。"""
        session = a_session()
        session.submit_offer("v=0 offer", NOW)
        session.add_candidate(Peer.VIEWER, a_candidate("viewer-1"), NOW)
        await repository.save(session)

        loaded = await repository.get(session.id)

        assert loaded is not None
        assert loaded.id == session.id
        assert loaded.device_id == session.device_id
        assert loaded.owner_id == session.owner_id
        assert loaded.offer_sdp == "v=0 offer"
        assert loaded.state is session.state
        assert loaded.expires_at == session.expires_at
        assert loaded.turn_credentials == session.turn_credentials
        assert loaded.candidates_for(Peer.VIEWER, since=0) == [a_candidate("viewer-1")]

    async def test_mutating_the_returned_session_does_not_leak_back(
        self, repository: StreamSessionRepository
    ) -> None:
        """「回傳的是新的物件,對它的修改必須再 save 才會保存」"""
        await repository.save(a_session())

        loaded = await repository.get(SESSION_A)
        assert loaded is not None
        loaded.submit_offer("v=0 not-saved", NOW)

        reloaded = await repository.get(SESSION_A)
        assert reloaded is not None
        assert reloaded.offer_sdp is None

    async def test_device_index_points_at_the_active_session(
        self, repository: StreamSessionRepository
    ) -> None:
        await repository.save(a_session())

        active = await repository.get_active_for_device(DEVICE_A)

        assert active is not None
        assert active.id == SESSION_A

    async def test_get_active_for_unknown_device_is_none(
        self, repository: StreamSessionRepository
    ) -> None:
        assert await repository.get_active_for_device(uuid.uuid4()) is None

    async def test_saving_a_second_session_takes_over_the_device(
        self, repository: StreamSessionRepository
    ) -> None:
        """第 2.4 節接管語意:舊 session_id 之後必須讀不到。"""
        newer = uuid.UUID("00000000-0000-0000-0000-000000005e52")
        await repository.save(a_session())
        await repository.save(a_session(id=newer))

        assert await repository.get(SESSION_A) is None
        active = await repository.get_active_for_device(DEVICE_A)
        assert active is not None and active.id == newer

    async def test_sessions_of_other_devices_survive_a_takeover(
        self, repository: StreamSessionRepository
    ) -> None:
        other_device = uuid.UUID("00000000-0000-0000-0000-0000000de72c")
        other_session = uuid.UUID("00000000-0000-0000-0000-000000005e53")
        await repository.save(a_session())
        await repository.save(a_session(id=other_session, device_id=other_device))

        assert await repository.get(SESSION_A) is not None
        assert await repository.get(other_session) is not None

    async def test_expired_session_disappears(
        self, repository: StreamSessionRepository, clock: FakeClock
    ) -> None:
        """TTL 300 秒(第 2.4 節)。到期後 session 與裝置索引都要消失。"""
        await repository.save(a_session(ttl=timedelta(seconds=1)))

        clock.advance(timedelta(seconds=2))

        assert await repository.get(SESSION_A) is None
        assert await repository.get_active_for_device(DEVICE_A) is None

    async def test_delete_removes_session_and_device_index(
        self, repository: StreamSessionRepository
    ) -> None:
        await repository.save(a_session())

        await repository.delete(SESSION_A)

        assert await repository.get(SESSION_A) is None
        assert await repository.get_active_for_device(DEVICE_A) is None

    async def test_delete_is_idempotent(self, repository: StreamSessionRepository) -> None:
        """第 3.1 節:重複 DELETE 一律 204,不存在時視為成功。"""
        await repository.delete(SESSION_A)
        await repository.delete(SESSION_A)


class TestInMemoryStreamSessionRepository(StreamSessionRepositoryContract):
    @pytest.fixture
    def clock(self) -> FakeClock:
        return FakeClock(NOW)

    @pytest.fixture
    def repository(self, clock: FakeClock) -> StreamSessionRepository:
        return InMemoryStreamSessionRepository(clock)


@pytest.mark.integration
class TestRedisStreamSessionRepository(StreamSessionRepositoryContract):
    """同一份合約跑在真實 Redis 上。

    到期測試用真的 TTL,所以 clock 前進時要一併等待——這正是 fake 不可能測到、
    而正式實作最容易出錯的地方(key 到期了但裝置索引沒有)。
    """

    @pytest.fixture
    def clock(self) -> FakeClock:
        return FakeClock(NOW)

    @pytest.fixture
    async def repository(self, clock: FakeClock):  # type: ignore[no-untyped-def]
        import redis.asyncio as redis

        from app.domains.streaming.infrastructure.redis_session_repository import (
            RedisStreamSessionRepository,
        )

        url = os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
        client = redis.from_url(url, decode_responses=True)
        await client.flushdb()
        try:
            yield RedisStreamSessionRepository(client, clock)
        finally:
            await client.flushdb()
            await client.aclose()

    @pytest.mark.skip(reason="真實 Redis 用自己的 TTL,不受 FakeClock 影響;由下面那則取代")
    async def test_expired_session_disappears(self, repository, clock) -> None:  # type: ignore[no-untyped-def]
        ...

    async def test_expired_session_disappears_by_real_ttl(
        self, repository: StreamSessionRepository
    ) -> None:
        import asyncio

        await repository.save(a_session(ttl=timedelta(seconds=1)))
        await asyncio.sleep(1.2)

        assert await repository.get(SESSION_A) is None
        assert await repository.get_active_for_device(DEVICE_A) is None
