"""push_tokens 的實體。純 Python,不依賴框架與 ORM。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domains.push_tokens.domain.exceptions import BlankPushToken


class ClientPlatform(StrEnum):
    """01_資料模型與儲存規格.md 第 2.6 節的 platform 值域。"""

    APP = "app"
    WEB = "web"


@dataclass
class PushToken:
    """一個用戶端推播端點的登記(手機或瀏覽器),不是攝影機硬體。"""

    id: uuid.UUID
    user_id: uuid.UUID
    platform: ClientPlatform
    token: str
    created_at: datetime

    @classmethod
    def register(
        cls,
        *,
        id: uuid.UUID,
        user_id: uuid.UUID,
        platform: ClientPlatform,
        token: str,
        now: datetime,
    ) -> PushToken:
        if not token.strip():
            raise BlankPushToken()
        return cls(id=id, user_id=user_id, platform=platform, token=token, created_at=now)

    def rebind_to(self, user_id: uuid.UUID) -> None:
        """審查 #4:同一個端點換帳號登入時改綁新登入者,id 與 created_at 不變。"""
        self.user_id = user_id

    def is_owned_by(self, user_id: uuid.UUID) -> bool:
        return self.user_id == user_id
