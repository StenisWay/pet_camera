"""存取權杖驗證與內部呼叫把關。

Push 只**驗證** Auth 服務簽發的 access token,不簽發也不換發。

簽發能力只存在於 Auth 服務(02_spec_登入註冊與密碼重設.md 第 2.3.2 節):App 的
token 滑動展延由 Auth 的 `POST /auth/token/extend` 專責,七個服務共用密鑰驗證即可,
不必各自具備簽發能力,效期規則也只有一個實作位置。
"""

from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.shared_kernel.errors import AuthenticationRequired, PermissionDenied


class TokenExpired(AuthenticationRequired):
    """登入已逾時,請重新登入"""

    code = "AUTH_002"


class TokenInvalid(AuthenticationRequired):
    """請重新登入"""

    code = "AUTH_001"


def decode_access_token(token: str, *, secret: str, algorithm: str = "HS256") -> UUID:
    try:
        payload = jwt.decode(
            token,
            secret,
            # 明確指定演算法清單,擋掉 alg=none 與演算法混淆攻擊
            algorithms=[algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpired() from exc
    except jwt.PyJWTError as exc:
        raise TokenInvalid() from exc

    try:
        return UUID(str(payload["sub"]))
    except (ValueError, TypeError, KeyError) as exc:
        raise TokenInvalid() from exc


async def get_current_user_id(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> UUID:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise TokenInvalid()
    token = authorization.split(" ", 1)[1].strip()
    return decode_access_token(token, secret=settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def require_internal_caller(
    settings: Annotated[Settings, Depends(get_settings)],
    x_internal_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """跨服務內部端點(規格審查 #9)。

    只走 VCN 私有網路、不經 Load Balancer(13_ADR 第 1 節);共享金鑰是第二道防線。
    """
    if not x_internal_api_key or x_internal_api_key != settings.internal_api_key:
        raise PermissionDenied()


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
