"""Event 聚合。"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.domains.detection.domain.exceptions import EventAlreadyFinalised


class EventType(StrEnum):
    MOTION = "motion"


class EventStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class UploadedMedia:
    video_object_key: str
    thumbnail_object_key: str
    confidence_score: Decimal
    duration_sec: int
    ended_at: datetime
    is_partial: bool = False


@dataclass
class Event:
    id: UUID
    device_id: UUID
    started_at: datetime
    event_type: EventType = EventType.MOTION
    status: EventStatus = EventStatus.PROCESSING
    confidence_score: Decimal = Decimal("0.00")
    video_object_key: str | None = None
    thumbnail_object_key: str | None = None
    duration_sec: int | None = None
    ended_at: datetime | None = None
    is_read: bool = False
    is_partial: bool = False

    @classmethod
    def begin(cls, *, id: UUID, device_id: UUID, started_at: datetime) -> "Event":
        return cls(id=id, device_id=device_id, started_at=started_at)

    def mark_ready(self, media: UploadedMedia) -> None:
        """上傳成功,轉 ready(07_spec 第 3.4 節)。

        confidence_score 取事件期間最高值,duration_sec 為實際長度。
        is_partial 為真時仍然是 ready——斷線的片段可以播放,只是不完整(EVENT_003)。
        """
        self._ensure_not_finalised()
        self.status = EventStatus.READY
        self.video_object_key = media.video_object_key
        self.thumbnail_object_key = media.thumbnail_object_key
        self.confidence_score = media.confidence_score
        self.duration_sec = media.duration_sec
        self.ended_at = media.ended_at
        self.is_partial = media.is_partial

    def mark_failed(self) -> None:
        """重試 UPLOAD_MAX_ATTEMPTS 次後仍上傳失敗,轉 failed(第 3.5 節)。

        不寫入任何 object key:規格要求「不建立可播放內容」,留著半個 key 會讓
        時間軸以為有東西可以放。
        """
        self._ensure_not_finalised()
        self.status = EventStatus.FAILED

    def _ensure_not_finalised(self) -> None:
        """終態不可再改寫:worker 重試或訊息重複投遞時,結果必須維持第一次的定案。"""
        if self.is_finalised:
            raise EventAlreadyFinalised()

    @property
    def is_finalised(self) -> bool:
        return self.status is not EventStatus.PROCESSING

    def object_keys(self) -> list[str]:
        """刪除事件時要一併清掉的 R2 物件;未上傳的不列入。"""
        return [k for k in (self.video_object_key, self.thumbnail_object_key) if k]
