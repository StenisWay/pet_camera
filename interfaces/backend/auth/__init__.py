"""Auth 服務——涵蓋 F0.1(登入註冊密碼重設)+ F0.4(帳號設定)。
擁有 users、refresh_tokens 兩張表。F0.4 併入本服務而非獨立成一個服務,
理由見 rule_doc/功能需求/13_ADR_微服務與雙節點部署.md 第 1 節。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol
from uuid import UUID

from pydantic import BaseModel


class User(BaseModel):
    id: UUID
    email: str
    password_hash: str
    created_at: datetime


class RefreshToken(BaseModel):
    """僅 Web 平台使用(見 02_spec_登入註冊與密碼重設.md 第 2.3.1 節)。"""

    id: UUID
    user_id: UUID
    token_hash: str
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    created_at: datetime


class UserRepository(Protocol):
    async def get_by_id(self, user_id: UUID) -> Optional[User]: ...

    async def get_by_email(self, email: str) -> Optional[User]: ...

    async def create(self, email: str, password_hash: str) -> User: ...

    async def update_password_hash(self, user_id: UUID, password_hash: str) -> None: ...

    async def delete(self, user_id: UUID) -> None:
        """僅刪除 users 這筆紀錄;呼叫前 service 層需已完成資料模型文件第 6 節的
        其餘串聯清除(裝置、事件、相簿、push_tokens)。"""
        ...


class RefreshTokenRepository(Protocol):
    async def get_by_token_hash(self, token_hash: str) -> Optional[RefreshToken]: ...

    async def create(self, user_id: UUID, token_hash: str, expires_at: datetime) -> RefreshToken: ...

    async def revoke(self, refresh_token_id: UUID) -> None:
        """登出,或 rotation 換發新 token 時,將舊紀錄標記撤銷。"""
        ...

    async def delete_all_by_user(self, user_id: UUID) -> None:
        """刪除帳號時串聯清除。"""
        ...
