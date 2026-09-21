"""coturn REST API 認證(06_spec_即時串流.md 第 2.5 節)。

username = "{expiry_unix_ts}:{session_id}",expiry = 簽發時間 + 600 秒
credential = base64(HMAC_SHA1(TURN_STATIC_SECRET, username))

HMAC-SHA1 不是自己選的:coturn 的 use-auth-secret 就是這麼驗的,換演算法 TURN server
會拒絕。這裡的 SHA1 用於 HMAC(不靠碰撞抵抗),不是雜湊密碼。
"""

import base64
import hashlib
import hmac
import uuid
from datetime import datetime, timedelta

from app.domains.streaming.application.ports import TurnCredentialIssuer
from app.domains.streaming.domain.value_objects import TurnCredentials


class CoturnCredentialIssuer(TurnCredentialIssuer):
    def __init__(self, *, urls: tuple[str, ...], secret: str, ttl: timedelta) -> None:
        self._urls = urls
        self._secret = secret.encode()
        self._ttl = ttl

    async def issue(self, session_id: uuid.UUID, now: datetime) -> TurnCredentials:
        expires_at = now + self._ttl
        username = f"{int(expires_at.timestamp())}:{session_id}"
        digest = hmac.new(self._secret, username.encode(), hashlib.sha1).digest()
        return TurnCredentials(
            urls=self._urls,
            username=username,
            credential=base64.b64encode(digest).decode(),
            expires_at=expires_at,
        )
