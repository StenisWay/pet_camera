"""R2 key 命名規則。01_資料模型與儲存規格.md 第 3.1 節。

    videos/{device_id}/{yyyy}/{mm}/{dd}/{event_id}.mp4
    thumbnails/{device_id}/{yyyy}/{mm}/{dd}/{event_id}.jpg

日期分層以**事件開始時間**為準(UTC,與儲存的 timestamptz 同一個基準)。
08_spec 第 2.2 節的保留期判定也用 started_at,兩者刻意一致——否則跨日的事件會
出現「key 在某一天的資料夾、過期判定卻用另一天」的錯位。
"""

from datetime import datetime
from uuid import UUID


def _date_path(started_at: datetime) -> str:
    return f"{started_at:%Y/%m/%d}"


def video_key(*, device_id: UUID, event_id: UUID, started_at: datetime) -> str:
    return f"videos/{device_id}/{_date_path(started_at)}/{event_id}.mp4"


def thumbnail_key(*, device_id: UUID, event_id: UUID, started_at: datetime) -> str:
    return f"thumbnails/{device_id}/{_date_path(started_at)}/{event_id}.jpg"
