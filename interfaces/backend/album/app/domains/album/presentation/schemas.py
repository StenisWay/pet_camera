"""相簿 API 的 Pydantic 模型。只在 presentation 層使用。

回應刻意不含 object_key、user_id、device_id:R2 key 是內部細節,而且 key 內含
user_id(01_資料模型與儲存規格.md 第 3.1 節),外流等於給人推敲的線索。
內容一律以 10 分鐘效期的 presigned URL 提供(同文件第 3.3 節)。
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class AlbumItemOut(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    captured_at: datetime
    duration_sec: int | None = None
    drive_export_status: str
    drive_file_id: str | None = None
    url: str | None = None  # status != ready 時沒有可播放內容
    thumbnail_url: str | None = None


class AlbumPageOut(BaseModel):
    items: list[AlbumItemOut]
    next_cursor: str | None = None


class CascadeDeleteOut(BaseModel):
    deleted_object_count: int
