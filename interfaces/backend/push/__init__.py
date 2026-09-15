"""Push 服務——涵蓋 F4(推播通知)。擁有 push_tokens 表。
注意:這是使用者「用戶端裝置」(手機/瀏覽器)的推播接收端點,
與 Device 服務的攝影機硬體是不同概念,不可混用。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel


class ClientPlatform(str, Enum):
    APP = "app"
    WEB = "web"


class PushToken(BaseModel):
    id: UUID
    user_id: UUID
    platform: ClientPlatform
    token: str  # FCM/APNs registration token,或 Web Push subscription(JSON 字串)
    created_at: datetime


class PushTokenRepository(Protocol):
    async def list_by_user(self, user_id: UUID) -> list[PushToken]:
        """發送推播時,取出該使用者名下所有用戶端裝置的 token。"""
        ...

    async def upsert(self, user_id: UUID, platform: ClientPlatform, token: str) -> PushToken:
        """PUT /push-tokens:同一 (user_id, platform, token) 已存在則視為更新。"""
        ...

    async def delete(self, push_token_id: UUID) -> None:
        """DELETE /push-tokens/{id}:使用者關閉通知或登出時呼叫。"""
        ...

    async def mark_invalid(self, push_token_id: UUID) -> None:
        """PUSH_003:推播服務回報 token 失效時呼叫,等同刪除。"""
        ...

    async def delete_all_by_user(self, user_id: UUID) -> None:
        """由 Auth 服務跨服務呼叫(刪除帳號時串聯清除)。"""
        ...
