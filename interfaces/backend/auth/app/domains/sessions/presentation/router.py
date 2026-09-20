"""sessions 的 HTTP 端點(02_spec 第 3 節)。

三個端點都不要求 access token 有效:

- refresh / logout 的前提正是 access token 已經過期(§2.3.1、§2.5)。
- extend 需要知道 token 的 iat 與 platform,所以要能解碼,但由本模組自己解,
  失敗時回 AUTH_001/AUTH_002。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.security import CurrentClaims
from app.domains.sessions.application.dtos import ExtendTokenCommand
from app.domains.sessions.application.use_cases.extend_app_token import ExtendAppToken
from app.domains.sessions.application.use_cases.logout import Logout
from app.domains.sessions.application.use_cases.refresh_session import RefreshSession
from app.domains.sessions.presentation.dependencies import (
    get_extend_app_token,
    get_logout,
    get_refresh_session,
)
from app.domains.sessions.presentation.schemas import (
    LogoutIn,
    RefreshTokenIn,
    SessionTokensOut,
)
from app.shared_kernel.platform import Platform

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token/refresh", response_model=SessionTokensOut)
async def refresh_token(
    payload: RefreshTokenIn,
    use_case: Annotated[RefreshSession, Depends(get_refresh_session)],
) -> SessionTokensOut:
    result = await use_case.execute(payload.refresh_token)
    return SessionTokensOut(
        access_token=result.access_token, refresh_token=result.refresh_token
    )


@router.post("/token/extend", response_model=SessionTokensOut | None)
async def extend_token(
    claims: CurrentClaims,
    response: Response,
    use_case: Annotated[ExtendAppToken, Depends(get_extend_app_token)],
) -> SessionTokensOut | None:
    from datetime import UTC, datetime

    result = await use_case.execute(
        ExtendTokenCommand(
            user_id=claims.user_id,
            platform=Platform(claims.platform),
            issued_at=datetime.fromtimestamp(claims.issued_at, tz=UTC),
        )
    )
    if result is None:
        # 還不需要展延:App 沿用原 token(§2.3.2)
        response.status_code = status.HTTP_204_NO_CONTENT
        return None
    return SessionTokensOut(access_token=result.access_token, refresh_token=None)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: LogoutIn,
    use_case: Annotated[Logout, Depends(get_logout)],
) -> None:
    # 冪等:未知或已撤銷的 token 一樣回 204(§2.5)
    await use_case.execute(payload.refresh_token)
