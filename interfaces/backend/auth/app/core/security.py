"""Access token 的驗證,以及內部呼叫把關。

**簽發**不在這裡:token 的效期與 claim 規則屬於 sessions 領域的業務規則
(02_spec 第 2.3、2.8 節),實作在 app/domains/sessions/。本模組只做
「拿到一個 token,它是誰、還有效嗎」——這是每個受保護端點都要做的事,
與 album 等其他服務的 core/security.py 是同一份邏輯。
"""

from dataclasses import dataclass
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


@dataclass(frozen=True)
class AccessTokenClaims:
    """02_spec 第 2.8 節定義的 claim 集合。

    `issued_at` / `platform` 是展延判斷需要的(第 2.3.2 節),所以這裡回傳完整
    claims 而不只是 user_id;只要 user_id 的呼叫端用 get_current_user_id。
    """

    user_id: UUID
    issued_at: int
    expires_at: int
    platform: str


def decode_access_token(
    token: str, *, secret: str, algorithm: str = "HS256"
) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            secret,
            # 明確指定演算法清單,擋掉 alg=none 與演算法混淆攻擊
            algorithms=[algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpired() from exc
    except jwt.PyJWTError as exc:
        raise TokenInvalid() from exc

    try:
        return AccessTokenClaims(
            user_id=UUID(str(payload["sub"])),
            issued_at=int(payload["iat"]),
            expires_at=int(payload["exp"]),
            platform=str(payload.get("platform", "")),
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise TokenInvalid() from exc


async def get_access_token_claims(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> AccessTokenClaims:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise TokenInvalid()
    token = authorization.split(" ", 1)[1].strip()
    return decode_access_token(token, secret=settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def get_current_user_id(
    claims: Annotated[AccessTokenClaims, Depends(get_access_token_claims)],
) -> UUID:
    return claims.user_id


async def require_internal_caller(
    settings: Annotated[Settings, Depends(get_settings)],
    x_internal_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """跨服務內部端點的第二道防線;第一道是只走 VCN 私有網路(13_ADR 第 1 節)。"""
    if not x_internal_api_key or x_internal_api_key != settings.internal_api_key:
        raise PermissionDenied()


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
CurrentClaims = Annotated[AccessTokenClaims, Depends(get_access_token_claims)]
