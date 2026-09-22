"""sessions 的組裝點(composition root)。

每個 port 一個 provider 函式,測試用 app.dependency_overrides 換掉任何一個,
就能在不碰資料庫、Redis 的情況下測 HTTP 層。

時間、ID、亂數、資料庫連線等兩個領域共用的 provider 在 app/core/dependencies.py,
本檔只放 sessions 專屬的。api.py 刻意不在這裡出現——那是**給別的領域**的入口,
自己的 router 直接用 use case 就好。
"""

from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.core.dependencies import ClockDep, IdsDep, SessionFactoryDep, TokensDep
from app.domains.sessions.application.ports import AccessTokenSigner, SessionsUnitOfWork
from app.domains.sessions.application.use_cases.extend_app_token import ExtendAppToken
from app.domains.sessions.application.use_cases.issue_session import IssueSession
from app.domains.sessions.application.use_cases.logout import Logout
from app.domains.sessions.application.use_cases.refresh_session import RefreshSession
from app.domains.sessions.application.use_cases.revoke_user_sessions import (
    RevokeUserSessions,
)
from app.domains.sessions.infrastructure.token_signer import JwtAccessTokenSigner
from app.domains.sessions.infrastructure.unit_of_work import SqlAlchemySessionsUnitOfWork

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_sessions_uow(session_factory: SessionFactoryDep) -> SessionsUnitOfWork:
    return SqlAlchemySessionsUnitOfWork(session_factory)


def get_access_token_signer(settings: SettingsDep) -> AccessTokenSigner:
    return JwtAccessTokenSigner(
        secret=settings.jwt_secret, algorithm=settings.jwt_algorithm
    )


SignerDep = Annotated[AccessTokenSigner, Depends(get_access_token_signer)]
SessionsUowDep = Annotated[SessionsUnitOfWork, Depends(get_sessions_uow)]


def get_issue_session(
    uow: SessionsUowDep,
    signer: SignerDep,
    clock: ClockDep,
    ids: IdsDep,
    tokens: TokensDep,
) -> IssueSession:
    return IssueSession(uow, signer=signer, clock=clock, ids=ids, tokens=tokens)


def get_refresh_session(
    uow: SessionsUowDep,
    signer: SignerDep,
    clock: ClockDep,
    ids: IdsDep,
    tokens: TokensDep,
) -> RefreshSession:
    return RefreshSession(uow, signer=signer, clock=clock, ids=ids, tokens=tokens)


def get_extend_app_token(signer: SignerDep, clock: ClockDep) -> ExtendAppToken:
    return ExtendAppToken(signer=signer, clock=clock)


def get_logout(uow: SessionsUowDep, clock: ClockDep, tokens: TokensDep) -> Logout:
    return Logout(uow, clock=clock, tokens=tokens)


def get_revoke_user_sessions(
    uow: SessionsUowDep, clock: ClockDep, tokens: TokensDep
) -> RevokeUserSessions:
    return RevokeUserSessions(uow, clock=clock, tokens=tokens)
