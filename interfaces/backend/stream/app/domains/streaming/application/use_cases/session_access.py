"""載入 session 並驗證呼叫者。

第 3.3 節:所有帶 session_id 的端點都要驗證呼叫者是不是這條連線的持有人。
把它集中在這裡,是因為規格審查 #3 記錄的 IDOR 正是「三個端點都沒做這件事」——
散在各個 use case 裡就會再漏一次。
"""

import uuid

from app.domains.streaming.domain.entities import StreamSession
from app.domains.streaming.domain.exceptions import DeviceNotFound, SessionExpired
from app.domains.streaming.domain.repositories import StreamSessionRepository


async def load_session(
    sessions: StreamSessionRepository,
    session_id: uuid.UUID,
    *,
    device_id: uuid.UUID,
    requester_id: uuid.UUID | None = None,
) -> StreamSession:
    """requester_id 為 None 代表呼叫者是鏡頭端,身分已由裝置憑證驗過。

    找不到 session 回 STREAM_002(已失效或被接管);找得到但不屬於呼叫者、
    或掛在別的裝置底下,回 DEVICE_005——與「裝置不存在」同一個 404,
    不洩漏 session 或裝置的存在性。
    """
    session = await sessions.get(session_id)
    if session is None:
        raise SessionExpired()
    if session.device_id != device_id:
        raise DeviceNotFound()
    if requester_id is not None and not session.is_owned_by(requester_id):
        raise DeviceNotFound()
    return session
