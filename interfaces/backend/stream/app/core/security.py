"""存取權杖驗證與鏡頭身分驗證。

Stream 只**驗證** Auth 服務簽發的 access token,不簽發也不換發
(02_spec_登入註冊與密碼重設.md 第 2.3.2 節:簽發能力只存在於 Auth 服務)。
"""

import hmac
import uuid
from abc import ABC, abstractmethod
from typing import Annotated

import jwt
from fastapi import Depends, Header, Request

from app.core.config import Settings, get_settings
from app.shared_kernel.errors import AuthenticationRequired, PermissionDenied


class TokenExpired(AuthenticationRequired):
    """登入已逾時,請重新登入"""

    code = "AUTH_002"


class TokenInvalid(AuthenticationRequired):
    """請重新登入"""

    code = "AUTH_001"


def decode_access_token(token: str, *, secret: str, algorithm: str = "HS256") -> uuid.UUID:
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
        return uuid.UUID(str(payload["sub"]))
    except (ValueError, TypeError, KeyError) as exc:
        raise TokenInvalid() from exc


async def get_current_user_id(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> uuid.UUID:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise TokenInvalid()
    token = authorization.split(" ", 1)[1].strip()
    return decode_access_token(token, secret=settings.jwt_secret, algorithm=settings.jwt_algorithm)


CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]


class CameraAuthenticator(ABC):
    """驗證第 3.2 節的內部路由確實來自那支鏡頭。

    06_spec 第 9 節「待確認事項」:鏡頭端的認證機制尚未定案——`/devices/{id}/heartbeat`
    同樣沒寫鏡頭如何證明身分,這是跨規格書的共同缺口。這裡先用一個可替換的介面把位置
    留好,Device 服務決定機制(裝置 token / mTLS)後只需要換掉實作,其餘各層不受影響。
    """

    @abstractmethod
    async def authenticate(self, device_id: uuid.UUID, credential: str | None) -> None:
        """驗證失敗時拋 PermissionDenied。"""


class SharedSecretCameraAuthenticator(CameraAuthenticator):
    """暫時實作:比對共享金鑰。

    內部路由只走 VCN 私有網路、不經 Load Balancer(13_ADR 第 1 節),共享金鑰是第二道
    防線。這還**不足以**區分「是哪一支鏡頭」——拿到金鑰的任一鏡頭都能冒充其他鏡頭。
    待 Device 服務定案後換成逐裝置憑證。
    """

    def __init__(self, secret: str) -> None:
        self._secret = secret

    async def authenticate(self, device_id: uuid.UUID, credential: str | None) -> None:
        if not credential or not hmac.compare_digest(credential, self._secret):
            raise PermissionDenied()


def get_camera_authenticator(request: Request) -> CameraAuthenticator:
    return request.app.state.camera_authenticator


async def require_camera(
    device_id: uuid.UUID,
    authenticator: Annotated[CameraAuthenticator, Depends(get_camera_authenticator)],
    x_device_credential: Annotated[str | None, Header()] = None,
) -> uuid.UUID:
    await authenticator.authenticate(device_id, x_device_credential)
    return device_id


AuthenticatedDeviceId = Annotated[uuid.UUID, Depends(require_camera)]
