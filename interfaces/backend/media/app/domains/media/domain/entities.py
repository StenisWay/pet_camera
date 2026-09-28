"""media 領域的實體與值物件:純 Python,業務規則的所在地。

不知道資料庫、HTTP 或 Pydantic 的存在。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.domains.media.domain.exceptions import (
    ClipRangeInvalid,
    ClipSourceExpired,
    ClipSourceNotReady,
    ClipTooLong,
    MediaItemNotFound,
    MediaItemNotProcessing,
)

# 11_spec 第 2.2 節 + 審查 #4:對齊 F2 的單一事件錄影上限
MAX_CLIP_SECONDS = 60


class MediaItemStatus(StrEnum):
    """01_資料模型與儲存規格.md 第 5 節的相簿項目狀態機。"""

    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MediaItemType(StrEnum):
    PHOTO = "photo"
    CLIP = "clip"


@dataclass(frozen=True)
class ClipRange:
    """剪輯範圍,以來源事件開始時間為基準的秒數(審查 #5)。"""

    start_sec: int
    end_sec: int

    def __post_init__(self) -> None:
        if self.start_sec < 0 or self.end_sec <= self.start_sec:
            raise ClipRangeInvalid()
        if self.duration_sec > MAX_CLIP_SECONDS:
            raise ClipTooLong()

    @property
    def duration_sec(self) -> int:
        return self.end_sec - self.start_sec

    def ensure_within(self, *, source_duration_sec: int) -> None:
        """確認範圍落在來源影片長度內(11_spec 第 2.2 節:不支援跨事件合併剪輯)。"""
        if self.end_sec > source_duration_sec:
            raise ClipRangeInvalid()


@dataclass(frozen=True)
class SourceEvent:
    """來源事件的快照,由 Event 服務提供(審查 #7)。

    這是別的服務擁有的資料,Media 只取自己判斷得到的欄位,不持久化。
    """

    id: uuid.UUID
    owner_id: uuid.UUID
    device_id: uuid.UUID
    status: str
    started_at: datetime
    duration_sec: int

    def is_owned_by(self, user_id: uuid.UUID) -> bool:
        return self.owner_id == user_id

    def is_video_expired(self, *, now: datetime, retention: timedelta) -> bool:
        """審查 #8:以 started_at 推算,不打 R2。

        R2 的 lifecycle rule 是每日批次,實際刪除可能晚於第 7 天;以此推算會比實際
        保守(可能把還在的影片判為過期)。這個方向是對的——同步回 410 比讓 worker
        跑到一半才發現檔案不見、再走 CLIP_002 對使用者好。
        """
        return self.started_at < now - retention

    def moment_of(self, offset_sec: int) -> datetime:
        """事件內某個秒數對應的絕對時間(審查 #11:相簿依此分組)。"""
        return self.started_at + timedelta(seconds=offset_sec)

    def ensure_covers(self, offset_sec: int) -> None:
        """確認時間點落在這段影片內(審查 #5:offset 以事件開始為基準)。"""
        if offset_sec < 0 or offset_sec > self.duration_sec:
            raise ClipRangeInvalid()

    def ensure_usable_by(
        self, user_id: uuid.UUID, *, now: datetime, retention: timedelta
    ) -> None:
        """確認這個事件可以當剪輯/回放截圖的來源。

        順序有意義:先擋擁有權(不洩漏存在性),再談狀態與保留期。
        """
        if not self.is_owned_by(user_id):
            raise MediaItemNotFound()
        if self.status != "ready":
            raise ClipSourceNotReady()
        if self.is_video_expired(now=now, retention=retention):
            raise ClipSourceExpired()


@dataclass
class MediaItem:
    """media_items 的聚合根。Media 服務負責建立與推進處理狀態。"""

    id: uuid.UUID
    owner_id: uuid.UUID
    device_id: uuid.UUID
    type: MediaItemType
    status: MediaItemStatus
    captured_at: datetime
    source_event_id: uuid.UUID | None = None
    object_key: str | None = None
    thumbnail_object_key: str | None = None
    duration_sec: int | None = None
    updated_at: datetime | None = None

    # --- 建立 ---

    @classmethod
    def start_photo(
        cls,
        *,
        item_id: uuid.UUID,
        owner_id: uuid.UUID,
        device_id: uuid.UUID,
        captured_at: datetime,
        now: datetime,
        source_event_id: uuid.UUID | None = None,
    ) -> "MediaItem":
        """11_spec 第 2.1 節:建立 media_items 紀錄,status = processing。

        photo 沒有 duration_sec(資料模型 §2.4)。
        """
        return cls(
            id=item_id,
            owner_id=owner_id,
            device_id=device_id,
            type=MediaItemType.PHOTO,
            status=MediaItemStatus.PROCESSING,
            captured_at=captured_at,
            source_event_id=source_event_id,
            updated_at=now,
        )

    @classmethod
    def start_clip(
        cls,
        *,
        item_id: uuid.UUID,
        owner_id: uuid.UUID,
        event: SourceEvent,
        clip_range: ClipRange,
        now: datetime,
    ) -> "MediaItem":
        """11_spec 第 2.2 節:剪輯請求受理,先建立 processing 紀錄再派工。

        captured_at 取來源事件的時間而非按鈕按下的時間(審查 #11)。
        """
        clip_range.ensure_within(source_duration_sec=event.duration_sec)
        return cls(
            id=item_id,
            owner_id=owner_id,
            device_id=event.device_id,
            type=MediaItemType.CLIP,
            status=MediaItemStatus.PROCESSING,
            captured_at=event.moment_of(clip_range.start_sec),
            source_event_id=event.id,
            duration_sec=clip_range.duration_sec,
            updated_at=now,
        )

    # --- 查詢 ---

    def is_owned_by(self, user_id: uuid.UUID) -> bool:
        return self.owner_id == user_id

    @property
    def is_ready(self) -> bool:
        return self.status is MediaItemStatus.READY

    @property
    def object_keys(self) -> list[str]:
        """對應的 R2 物件(內容 + 縮圖);processing 期間還沒有東西。"""
        return [k for k in (self.object_key, self.thumbnail_object_key) if k]

    def is_stale_processing(self, *, now: datetime, after: timedelta) -> bool:
        """審查 #9:卡住的 processing 判定,與 F6 的 exporting 15 分鐘規則對稱。"""
        if self.status is not MediaItemStatus.PROCESSING:
            return False
        if self.updated_at is None:
            return True
        return self.updated_at < now - after

    # --- 狀態轉移 ---

    def _ensure_processing(self) -> None:
        if self.status is not MediaItemStatus.PROCESSING:
            raise MediaItemNotProcessing()

    def mark_ready(
        self, *, object_key: str, thumbnail_object_key: str | None, now: datetime
    ) -> None:
        """處理完成,內容可於相簿瀏覽播放(資料模型第 5 節)。"""
        self._ensure_processing()
        self.status = MediaItemStatus.READY
        self.object_key = object_key
        self.thumbnail_object_key = thumbnail_object_key
        self.updated_at = now

    def mark_failed(self, *, now: datetime) -> None:
        """CLIP_002 / SCREENSHOT_001:不建立可用內容,只改狀態。"""
        self._ensure_processing()
        self.status = MediaItemStatus.FAILED
        self.updated_at = now
