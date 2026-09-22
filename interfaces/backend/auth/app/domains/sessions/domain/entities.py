"""sessions 領域的實體與值物件。

02_spec 第 2.6 節的平台差異表整張是這裡的業務規則:哪個平台發什麼 token、
發多久、怎麼展延、怎麼收回。時間由外部傳入,實體不自己取 now。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from app.shared_kernel.platform import Platform

# 02_spec 第 2.6 節平台差異表
WEB_ACCESS_TOKEN_TTL = timedelta(hours=1)
WEB_REFRESH_TOKEN_TTL = timedelta(days=30)
APP_ACCESS_TOKEN_TTL = timedelta(days=180)
# 02_spec 第 2.3.2 節:核發滿 7 天才展延
APP_EXTEND_AFTER = timedelta(days=7)

_ACCESS_TOKEN_TTL = {
    Platform.WEB: WEB_ACCESS_TOKEN_TTL,
    Platform.APP: APP_ACCESS_TOKEN_TTL,
}


class RevocationReason(str, Enum):
    """為什麼這個 refresh token 被撤銷。

    §2.3.1 的重放偵測只對 ROTATED 生效。其餘兩種是**我們主動**撤銷的,
    那個用戶端毫不知情,它下次送上來的舊 token 無辜,不該牽連整串 session。
    """

    ROTATED = "rotated"  # 換發新 token 時撤銷舊的
    LOGGED_OUT = "logged_out"  # 使用者自己登出(§2.5)
    SUPERSEDED = "superseded"  # 改密碼/重設密碼時連帶撤銷(05_spec 2.1、02_spec 2.4)


@dataclass(frozen=True)
class AccessToken:
    """一組 access token 的內容(claims),不含簽章。

    簽章是 infrastructure 的事(PyJWT);這裡只決定「裡面有什麼、活多久」。
    """

    user_id: uuid.UUID
    platform: Platform
    issued_at: datetime
    expires_at: datetime

    @classmethod
    def issue(
        cls, *, user_id: uuid.UUID, platform: Platform, now: datetime
    ) -> "AccessToken":
        return cls(
            user_id=user_id,
            platform=platform,
            issued_at=now,
            expires_at=now + _ACCESS_TOKEN_TTL[platform],
        )

    def claims(self) -> dict[str, str | int]:
        """02_spec 第 2.8 節定義的 claim 集合,其餘六個服務只認這四個。"""
        return {
            "sub": str(self.user_id),
            "iat": int(self.issued_at.timestamp()),
            "exp": int(self.expires_at.timestamp()),
            "platform": self.platform.value,
        }

    def needs_extension(self, *, now: datetime) -> bool:
        """App 專用的滑動展延判斷(§2.3.2)。Web 走 rotation,永遠不展延。"""
        if self.platform is not Platform.APP:
            return False
        return now - self.issued_at >= APP_EXTEND_AFTER


@dataclass
class RefreshToken:
    """Web 專用(§2.3.1)。資料庫只存雜湊值,明碼只回給用戶端一次。"""

    id: uuid.UUID
    user_id: uuid.UUID
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime
    revoked_reason: RevocationReason | None = None

    @classmethod
    def issue(
        cls, *, id: uuid.UUID, user_id: uuid.UUID, token_hash: str, now: datetime
    ) -> "RefreshToken":
        return cls(
            id=id,
            user_id=user_id,
            token_hash=token_hash,
            expires_at=now + WEB_REFRESH_TOKEN_TTL,
            revoked_at=None,
            created_at=now,
        )

    def is_usable(self, *, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now

    def looks_replayed(self) -> bool:
        """被 rotation 換掉之後又出現 = 外洩徵兆(§2.3.1)。

        我們主動撤銷的(登出、改密碼)不算:那個用戶端根本不知道自己被撤銷了。
        """
        return self.revoked_reason is RevocationReason.ROTATED
