"""HTTP 的輸入輸出形狀。Pydantic 只出現在這一層。

輸入 schema 只接受使用者能指定的欄位——owner_id 來自 access token,status、
object_key 由後端決定,不接受從 request body 帶入(mass assignment)。
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domains.media.application.dtos import MediaItemResult


class EventScreenshotIn(BaseModel):
    """審查 #5:時間點一律用相對事件開始的整數秒。"""

    offset_sec: int


class ClipIn(BaseModel):
    start_sec: int
    end_sec: int


class ClipDoneIn(BaseModel):
    """worker 轉檔完成的回呼內容。"""

    object_key: str
    thumbnail_object_key: str | None = None


class MediaItemOut(BaseModel):
    """對外回應。不含 object_key——R2 的位置是內部細節,對外只給 presigned URL。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    status: str
    captured_at: datetime
    source_event_id: uuid.UUID | None
    duration_sec: int | None
    content_url: str | None
    thumbnail_url: str | None

    @classmethod
    def of(cls, result: MediaItemResult) -> "MediaItemOut":
        return cls.model_validate(result)
