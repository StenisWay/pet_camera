"""把 accounts 的 SessionService port 接到 sessions 領域。

這是 accounts 裡**唯一**知道 sessions 存在的檔案,而且它在 infrastructure 層
(tools/check_layers.py 規則 4)。accounts 的 domain 與 application 只看得到
自己定義的 SessionService 介面。
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.accounts.application.ports import IssuedSession, SessionService
from app.domains.sessions.api import SessionsApi, build_sessions_api
from app.shared_kernel.platform import Platform
from app.shared_kernel.ports import Clock, IdGenerator, OpaqueTokenFactory


class SessionsApiAdapter(SessionService):
    def __init__(self, api: SessionsApi) -> None:
        self._api = api

    async def issue(self, user_id: uuid.UUID, platform: Platform) -> IssuedSession:
        tokens = await self._api.issue(user_id, platform)
        # 翻譯成 accounts 自己的 DTO:兩邊的型別不綁在一起
        return IssuedSession(
            access_token=tokens.access_token, refresh_token=tokens.refresh_token
        )

    async def revoke_all(
        self, user_id: uuid.UUID, *, except_refresh_token: str | None = None
    ) -> None:
        await self._api.revoke_all(user_id, except_refresh_token=except_refresh_token)


def build_session_service(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    clock: Clock,
    ids: IdGenerator,
    tokens: OpaqueTokenFactory,
    jwt_secret: str,
    jwt_algorithm: str = "HS256",
) -> SessionService:
    """accounts 的組裝點要的成品:一個 SessionService。

    只認得 sessions.api 這一個模組——sessions 內部怎麼組、用哪個 UnitOfWork、
    簽章怎麼實作,accounts 都不需要也不應該知道。
    """
    return SessionsApiAdapter(
        build_sessions_api(
            session_factory=session_factory,
            clock=clock,
            ids=ids,
            tokens=tokens,
            jwt_secret=jwt_secret,
            jwt_algorithm=jwt_algorithm,
        )
    )
