"""sessions 對其他領域公開的唯一入口。

accounts 只能經由這個模組跟 sessions 往來,而且只能在它的 infrastructure 層
(adapter)呼叫——tools/check_layers.py 會檢查這件事。這樣 sessions 的內部結構
(實體、repository、UnitOfWork)可以自由重構,accounts 不受影響。

公開的是**能力**,不是型別:回傳 SessionTokens 這個 DTO,不回傳實體。
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.sessions.application.dtos import SessionTokens
from app.domains.sessions.application.use_cases.issue_session import IssueSession
from app.domains.sessions.application.use_cases.revoke_user_sessions import (
    RevokeUserSessions,
)
from app.domains.sessions.infrastructure.token_signer import JwtAccessTokenSigner
from app.domains.sessions.infrastructure.unit_of_work import (
    SqlAlchemySessionsUnitOfWork,
)
from app.shared_kernel.platform import Platform
from app.shared_kernel.ports import Clock, IdGenerator, OpaqueTokenFactory


class SessionsApi:
    def __init__(self, issue: IssueSession, revoke: RevokeUserSessions) -> None:
        self._issue = issue
        self._revoke = revoke

    async def issue(self, user_id: uuid.UUID, platform: Platform) -> SessionTokens:
        """簽發一組 session。Web 含 refresh token 明碼,App 的為 None。"""
        return await self._issue.execute(user_id, platform)

    async def revoke_all(
        self, user_id: uuid.UUID, *, except_refresh_token: str | None = None
    ) -> int:
        """撤銷該使用者所有未撤銷的 refresh token,回傳筆數。

        except_refresh_token 是明碼:呼叫端手上只有用戶端送來的那個字串。
        """
        return await self._revoke.execute(
            user_id, except_refresh_token=except_refresh_token
        )


def build_sessions_api(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    clock: Clock,
    ids: IdGenerator,
    tokens: OpaqueTokenFactory,
    jwt_secret: str,
    jwt_algorithm: str = "HS256",
) -> SessionsApi:
    """從原始依賴組出 SessionsApi。

    放在 api.py 而不是讓呼叫端自己組:別的領域只准 import 這個模組
    (tools/check_layers.py 規則 4),所以「怎麼組」也必須由這裡提供,
    否則 accounts 就得 import sessions 的 application 與 infrastructure。
    """
    uow = SqlAlchemySessionsUnitOfWork(session_factory)
    signer = JwtAccessTokenSigner(secret=jwt_secret, algorithm=jwt_algorithm)
    return SessionsApi(
        IssueSession(uow, signer=signer, clock=clock, ids=ids, tokens=tokens),
        RevokeUserSessions(uow, clock=clock, tokens=tokens),
    )
