"""建立直播 session(06_spec_即時串流.md 第 2.1、2.4 節)。"""

import uuid
from datetime import timedelta

from app.domains.streaming.application.ports import DeviceDirectory, TurnCredentialIssuer
from app.domains.streaming.domain.entities import StreamSession
from app.domains.streaming.domain.exceptions import DeviceNotFound, DeviceOffline
from app.domains.streaming.domain.repositories import StreamSessionRepository
from app.shared_kernel.ports import Clock, IdGenerator


class OpenStreamSession:
    def __init__(
        self,
        sessions: StreamSessionRepository,
        devices: DeviceDirectory,
        turn: TurnCredentialIssuer,
        clock: Clock,
        ids: IdGenerator,
        *,
        ttl: timedelta,
    ) -> None:
        self.sessions = sessions
        self.devices = devices
        self.turn = turn
        self.clock = clock
        self.ids = ids
        self.ttl = ttl

    async def execute(self, device_id: uuid.UUID, requester_id: uuid.UUID) -> StreamSession:
        now = self.clock.now()

        device = await self.devices.find(device_id)
        # 不存在、未配對、不屬於呼叫者一律同一個 404(第 3.3 節)
        if device is None or not device.is_owned_by(requester_id):
            raise DeviceNotFound()
        if not device.is_online(now):
            raise DeviceOffline()

        session_id = self.ids.new_id()
        credentials = await self.turn.issue(session_id, now)
        session = StreamSession.open(
            id=session_id,
            device_id=device_id,
            owner_id=requester_id,
            turn_credentials=credentials,
            now=now,
            ttl=self.ttl,
        )
        # 第 2.4 節接管:save 是 last-writer-wins,舊 session 由 repository 一併清掉。
        # 不先查再刪再建,是為了讓「同一裝置只有一個 session」落在單一 key 的覆寫上,
        # 兩個並發的建立請求不需要分散式鎖。
        await self.sessions.save(session)
        return session
