"""存取權杖驗證與內部呼叫把關。

Media 只**驗證** Auth 服務簽發的 access token,不簽發也不換發——簽章金鑰與 token
生命週期規則(02_spec 第 2.3 節)屬於 Auth 服務的職責。

內部端點(worker 完成回呼,規格審查 #3)只走 VCN 私有網路、不經 Load Balancer,
另以共享金鑰標頭把關。
"""

import hmac
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
    # 定時比對,避免從回應時間逐字元猜出金鑰;比 bytes 是因為 compare_digest 遇到
    # 非 ASCII 的 str 會拋 TypeError,變成 500 而不是 403
    if not x_internal_api_key or not hmac.compare_digest(
        x_internal_api_key.encode(), settings.internal_api_key.encode()
    ):
        raise PermissionDenied()


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
