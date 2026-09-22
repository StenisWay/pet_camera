"""時間軸的唯讀視圖。"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.domains.timeline.domain.exceptions import (
    EventNotReady,
    EventProcessingFailed,
    VideoExpired,
)

VIDEO_RETENTION = timedelta(days=7)
THUMBNAIL_RETENTION = timedelta(days=30)


class EventStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass
class TimelineEvent:
    id: UUID
    device_id: UUID
    status: EventStatus
    confidence_score: Decimal
    started_at: datetime
    duration_sec: int | None
    is_read: bool
    is_partial: bool
    ended_at: datetime | None = None
    video_object_key: str | None = None
    thumbnail_object_key: str | None = None

    def ensure_playable(self, now: datetime) -> None:
        """可否換發播放連結(08_spec 第 2.2 節)。

        順序是刻意的:先看狀態再看保留期。一筆還在 processing 的舊事件,使用者要做的
        是等待而不是放棄,回「已過期」會把他導向錯的復原路徑。
        """
        if self.status is EventStatus.PROCESSING:
            raise EventNotReady()
        if self.status is EventStatus.FAILED:
            raise EventProcessingFailed()
        if self.video_object_key is None:
            # 資料表的 ready_requires_media CHECK 擋得住,但讀取端遇到髒資料時
            # 該回一個使用者看得懂的狀態,而不是讓 None 一路往下變成 500。
            raise EventNotReady()
        if now >= self.started_at + VIDEO_RETENTION:
            raise VideoExpired()

    def playable_video_key(self, now: datetime) -> str:
        """通過 ensure_playable 之後的影片 key。

        讓呼叫端拿到的是 str 而不是 str | None:可播放性與「key 存在」本來就是
        同一件事,分成兩步會逼每個呼叫端再檢查一次 None。
        """
        self.ensure_playable(now)
        key = self.video_object_key
        if key is None:  # ensure_playable 已經擋掉,這裡只是讓型別收斂
            raise EventNotReady()
        return key

    def thumbnail_key_if_available(self, now: datetime) -> str | None:
        """還在保留期內的縮圖 key,否則 None(前端顯示佔位圖示)。"""
        return self.thumbnail_object_key if self.thumbnail_available(now) else None

    def thumbnail_available(self, now: datetime) -> bool:
        """縮圖是否已產生且還在 30 天保留期內(第 4 節)。

        影片過期後縮圖仍在,時間軸卡片因此還看得到圖;30 天後才換成佔位圖示
        (TIMELINE_004)。
        """
        if self.thumbnail_object_key is None:
            return False
        return now < self.started_at + THUMBNAIL_RETENTION

    def mark_read(self, is_read: bool) -> None:
        """標記已讀/未讀(第 2.3 節)。只有這一個欄位可由用戶端改。"""
        self.is_read = is_read
