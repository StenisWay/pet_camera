"""驗證相關的原語。刻意不 import FastAPI——HTTP 的部分在 presentation 層組裝。

三種呼叫者,三套驗證方式:

| 呼叫者 | 端點 | 驗證方式 |
|---|---|---|
| 使用者(App/Web) | /devices、/devices/pair 等 | Auth 服務簽發的 JWT(本服務只驗證,不簽發) |
| 鏡頭硬體 | /devices/{id}/heartbeat | register 當時簽發的 device secret(審查 #2) |
| 其他服務 | /internal/* | 共用的 X-Internal-Api-Key(審查 #7、#8) |
"""

import hashlib
import hmac
import secrets
import uuid

import jwt

from app.shared_kernel.errors import AuthenticationRequired

_SECRET_BYTES = 32
_SALT_BYTES = 16
_ALGORITHM_TAG = "sha256"


def decode_user_id(token: str, *, jwt_secret: str, algorithm: str) -> uuid.UUID:
    """從 Auth 服務簽發的 access token 取出使用者 id。

    過期與簽章錯誤都轉成 AuthenticationRequired(401),對應 10_錯誤處理 第 3 節的
    AUTH_002 / AUTH_001。本服務不簽發 token,也不負責 App 的滑動展延
    (02_spec 第 2.3.2 節)——那需要簽發能力,屬於 Auth 服務,見 README 已知限制。
    """
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=[algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationRequired("登入已逾時,請重新登入") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationRequired("請重新登入") from exc

    subject = payload.get("sub")
    if not subject:
        raise AuthenticationRequired("請重新登入")
    try:
        return uuid.UUID(str(subject))
    except ValueError as exc:
        raise AuthenticationRequired("請重新登入") from exc


def generate_device_secret() -> str:
    return secrets.token_urlsafe(_SECRET_BYTES)


def hash_device_secret(plaintext: str, *, salt: str | None = None) -> str:
    """以加鹽 SHA-256 雜湊鏡頭憑證,輸出 `sha256$鹽$摘要`。

    這裡不用 bcrypt/argon2 是刻意的:device secret 是本服務用 CSPRNG 產生的
    256-bit 亂數,不是人選的密碼,沒有字典攻擊的空間,慢雜湊只會讓每次心跳
    (每台鏡頭 30 秒一次)白白多燒 CPU。使用者密碼由 Auth 服務處理,不在這裡。
    """
    salt = salt or secrets.token_hex(_SALT_BYTES)
    digest = hashlib.sha256(f"{salt}{plaintext}".encode()).hexdigest()
    return f"{_ALGORITHM_TAG}${salt}${digest}"


def verify_device_secret(plaintext: str, secret_hash: str) -> bool:
    """常數時間比對,避免以回應時間差推敲出正確的 secret。"""
    try:
        tag, salt, _ = secret_hash.split("$", 2)
    except ValueError:
        return False
    if tag != _ALGORITHM_TAG:
        return False
    return hmac.compare_digest(hash_device_secret(plaintext, salt=salt), secret_hash)


def verify_internal_api_key(provided: str | None, expected: str) -> None:
    """內部端點的把關。只走 VCN 私有網路,不經過 Load Balancer(13_ADR 第 1.1 節)。"""
    if not provided or not hmac.compare_digest(provided, expected):
        raise AuthenticationRequired("內部端點驗證失敗")
