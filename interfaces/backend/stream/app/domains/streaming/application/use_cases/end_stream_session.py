"""結束直播 session(第 3.1 節:冪等,一律 204)。"""

import logging
import uuid

from app.domains.streaming.domain.exceptions import DeviceNotFound
from app.domains.streaming.domain.repositories import StreamSessionRepository
from app.shared_kernel.errors import ServiceUnavailable

logger = logging.getLogger(__name__)


class EndStreamSession:
    def __init__(self, sessions: StreamSessionRepository) -> None:
        self.sessions = sessions

    async def execute(
        self, *, device_id: uuid.UUID, session_id: uuid.UUID, requester_id: uuid.UUID
    ) -> None:
        try:
            session = await self.sessions.get(session_id)
        except ServiceUnavailable:
            # 第 7 節例外條款:DELETE 採 fail-open。session 本來就會因 TTL 自動消失,
            # 讓使用者在離開頁面時收到 503 沒有意義。
            logger.warning("session store unavailable on delete, failing open")
            return

        # 已經不在了就當作成功——TTL 到期、被接管、或重複 DELETE 都走這條
        if session is None:
            return
        if session.device_id != device_id or not session.is_owned_by(requester_id):
            # 別人的 session 不能被刪掉。這裡不能 fail-open 成 204,
            # 否則就變成「試到有回應就代表刪掉了」的探測管道。
            raise DeviceNotFound()

        try:
            await self.sessions.delete(session_id)
        except ServiceUnavailable:
            logger.warning("session store unavailable on delete, failing open")
