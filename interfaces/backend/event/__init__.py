"""Event 服務——涵蓋 F2(事件偵測,背景 worker,不對外提供 API)+ F3(時間軸讀取 API)。
擁有 events 表。兩者合併成一個服務的理由見
rule_doc/功能需求/13_ADR_微服務與雙節點部署.md 第 1 節(同一張表不可被兩個服務分別宣稱擁有)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Protocol
from uuid import UUID

from pydantic import BaseModel


class EventType(str, Enum):
    MOTION = "motion"


class EventStatus(str, Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Event(BaseModel):
    id: UUID
    device_id: UUID
    event_type: EventType
    confidence_score: float
    status: EventStatus
    video_object_key: Optional[str] = None
    thumbnail_object_key: Optional[str] = None
    duration_sec: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    is_read: bool = False
    created_at: datetime


@dataclass
class EventPage:
    items: list[Event]
    next_cursor: Optional[str]  # (started_at, id) 組合游標,見 08_spec 第 2.1 節


class EventRepository(Protocol):
    async def get_by_id(self, event_id: UUID) -> Optional[Event]: ...

    async def list_by_device(
        self,
        device_id: UUID,
        *,
        cursor: Optional[str] = None,
        limit: int = 20,
        date: Optional[str] = None,
    ) -> EventPage: ...

    async def create_processing(self, device_id: UUID, started_at: datetime) -> Event:
        """偵測 worker 觸發錄影當下建立,status=processing。"""
        ...

    async def mark_ready(
        self,
        event_id: UUID,
        *,
        video_object_key: str,
        thumbnail_object_key: str,
        confidence_score: float,
        duration_sec: int,
        ended_at: datetime,
    ) -> None: ...

    async def mark_failed(self, event_id: UUID) -> None: ...

    async def mark_read(self, event_id: UUID) -> None: ...

    async def delete_all_by_device(self, device_id: UUID) -> None:
        """由 Device 服務跨服務呼叫(裝置移除時串聯清除,見資料模型文件第 6 節);
        呼叫端需另外刪除對應的 R2 影片/縮圖物件。"""
        ...
