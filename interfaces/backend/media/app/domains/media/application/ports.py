"""application 需要的介面。以**本領域的語言**命名,不是外部系統的完整 API。

實作都在外層(infrastructure 的 adapter)與測試替身,依賴方向永遠指向內層。
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Self

from app.domains.media.domain.entities import SourceEvent
from app.domains.media.domain.repositories import MediaItemRepository


@dataclass(frozen=True)
class SourceDevice:
    """鏡頭的快照,由 Device 服務提供。"""

    id: uuid.UUID
    owner_id: uuid.UUID
    is_online: bool


class MediaUnitOfWork(ABC):
    media: MediaItemRepository

    @abstractmethod
    async def __aenter__(self) -> Self: ...

    @abstractmethod
    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        """未 commit 的變更一律回滾。"""

    @abstractmethod
    async def commit(self) -> None:
        """送出這個交易。ADR 第 4 節:Media 的寫入選 C,連不到 Postgres 就失敗。"""


class DeviceDirectory(ABC):
    """Device 服務。比照 stream/__init__.py 的先例:不直接讀對方的資料表。"""

    @abstractmethod
    async def get(self, device_id: uuid.UUID) -> SourceDevice | None:
        """查不到時回傳 None(呼叫端一律轉成 MediaItemNotFound,不洩漏存在性)。

        Device 服務連不上或回 5xx 時拋 ServiceUnavailable。
        """


class EventSource(ABC):
    """Event 服務的 GET /internal/events/{id}(審查 #7)。"""

    @abstractmethod
    async def get(self, event_id: uuid.UUID) -> SourceEvent | None:
        """取得來源事件;查不到時回傳 None。

        回應含 owner_id——events 表本身沒有 user_id,Media 無法自行判斷擁有者。
        Event 服務連不上或回 5xx 時拋 ServiceUnavailable。
        """


@dataclass(frozen=True)
class CapturedFrame:
    """worker 擷回來的一幀。

    縮圖一併產生(審查 #17):相簿網格一次顯示數十個項目,沒有縮圖就得載原圖。
    資料模型 §2.4 原本規定 photo 的 thumbnail_object_key 必為 null,這是規格審查
    後放寬的部分,已同步回寫 rule_doc。
    """

    image: bytes
    thumbnail: bytes


class FrameSource(ABC):
    """VM-3 worker 的擷幀能力(審查 #2)。

    即時畫面走 WebRTC 直達前端、不經過本服務,唯一持有鏡頭影像的是直連 RTSP 的
    偵測 worker。
    """

    @abstractmethod
    async def capture_live_frame(self, device_id: uuid.UUID) -> CapturedFrame:
        """擷取鏡頭當下的一幀 JPEG(含縮圖)。

        來源不存在、鏡頭沒有畫面或 worker 無回應時拋 ScreenshotSourceUnavailable。
        """

    @abstractmethod
    async def capture_event_frame(
        self, event_id: uuid.UUID, *, offset_sec: int
    ) -> CapturedFrame:
        """從事件影片的指定秒數擷取一幀 JPEG(含縮圖)。失敗條件同上。"""


class ClipWorker(ABC):
    """VM-3 worker 的轉碼派工(審查 #3)。

    不引入工作佇列:ADR 第 1.1 節把共用 Redis 的用途限定在三項,不含佇列。
    """

    @abstractmethod
    async def dispatch(
        self,
        *,
        media_item_id: uuid.UUID,
        source_event_id: uuid.UUID,
        start_sec: int,
        end_sec: int,
        object_key: str,
        thumbnail_object_key: str,
    ) -> None:
        """請 worker 裁切並上傳。受理即回,完成後 worker 回呼本服務的內部端點。

        派不出去時拋例外,呼叫端負責把項目標成 failed。
        """


class MediaStorage(ABC):
    """R2(資料模型第 3 節)。"""

    @abstractmethod
    async def put_image(self, object_key: str, content: bytes) -> None:
        """上傳截圖內容。失敗時拋例外。"""

    @abstractmethod
    async def presigned_url(self, object_key: str) -> str:
        """換發一次性下載連結,效期 10 分鐘(資料模型第 3.3 節)。"""
