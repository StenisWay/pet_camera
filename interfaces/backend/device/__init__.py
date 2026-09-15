"""Device 服務——涵蓋 F0.2(裝置配對)+ F0.3(裝置管理)。擁有 devices 表。
注意:這裡的「裝置」是攝影機硬體,與 push 服務的用戶端裝置 token 是不同概念。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, Protocol
from uuid import UUID

from pydantic import BaseModel


class DeviceStatus(str, Enum):
    PENDING = "pending"
    PAIRED = "paired"
    OFFLINE = "offline"


class Device(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    name: str
    pairing_code: Optional[str] = None
    pairing_code_expires_at: Optional[datetime] = None
    status: DeviceStatus
    last_seen_at: Optional[datetime] = None
    created_at: datetime


class DeviceRepository(Protocol):
    async def get_by_id(self, device_id: UUID) -> Optional[Device]: ...

    async def get_by_pairing_code(self, pairing_code: str) -> Optional[Device]: ...

    async def list_by_user(self, user_id: UUID) -> list[Device]: ...

    async def create_pending(self, pairing_code: str, pairing_code_expires_at: datetime) -> Device:
        """鏡頭呼叫 POST /devices/register 時建立,狀態為 pending。"""
        ...

    async def pair(self, device_id: UUID, user_id: UUID) -> None:
        """綁定 user_id、status 改為 paired、清除 pairing_code。"""
        ...

    async def rename(self, device_id: UUID, name: str) -> None: ...

    async def update_heartbeat(self, device_id: UUID, last_seen_at: datetime) -> None: ...

    async def update_status(self, device_id: UUID, status: DeviceStatus) -> None: ...

    async def unpair(self, device_id: UUID, new_pairing_code: str) -> None:
        """移除裝置:status 重置為 pending、user_id 清空、重新產生 pairing_code。
        呼叫前 service 層需已請 Event 服務清空該裝置的事件與 R2 影片/縮圖
        (跨服務呼叫,見 rule_doc/功能需求/01_資料模型與儲存規格.md 第 6 節)。"""
        ...
