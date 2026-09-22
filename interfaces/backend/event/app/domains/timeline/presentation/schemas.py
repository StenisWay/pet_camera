"""HTTP 的輸入輸出形狀。Pydantic 只在這一層出現。"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, PlainSerializer

from app.domains.timeline.application.dtos import TimelineItemResult, TimelinePageResult
from app.domains.timeline.domain.entities import EventStatus

# 對外的時間一律是 Unix timestamp(秒,整數,UTC 基準)。
# 儲存層維持 timestamptz(01_資料模型第 2.0 節),轉換只發生在這一層。
EpochSeconds = Annotated[datetime, PlainSerializer(lambda dt: int(dt.timestamp()), return_type=int)]
# numeric(3,2) 對外以數字呈現;內部一律 Decimal,不讓浮點誤差回流到比較邏輯
Score = Annotated[Decimal, PlainSerializer(lambda d: float(d), return_type=float)]


class TimelineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: EventStatus
    confidence_score: Score
    started_at: EpochSeconds
    ended_at: EpochSeconds | None
    duration_sec: int | None
    is_read: bool
    is_partial: bool
    thumbnail_url: str | None

    @classmethod
    def of(cls, item: TimelineItemResult) -> "TimelineItemOut":
        return cls.model_validate(item)


class TimelinePageOut(BaseModel):
    items: list[TimelineItemOut]
    next_cursor: str | None

    @classmethod
    def of(cls, page: TimelinePageResult) -> "TimelinePageOut":
        return cls(
            items=[TimelineItemOut.of(item) for item in page.items],
            next_cursor=page.next_cursor,
        )


class PlaybackUrlOut(BaseModel):
    url: str
    expires_in: int


class MarkReadIn(BaseModel):
    """08_spec 第 2.3 節:只接受 is_read。

    extra="forbid" 擋不住的欄位由 Pydantic 直接丟掉——這裡刻意用預設的忽略行為,
    讓前端多送欄位不會失敗,但那些欄位也絕對不會生效(規格審查 #10)。
    """

    is_read: bool


class ReadStateOut(BaseModel):
    id: UUID
    is_read: bool
