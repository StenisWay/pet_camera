"""application 需要、但由外層實作的介面。以 detection 自己的語言命名。"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from types import TracebackType
from typing import Self
from uuid import UUID

from app.domains.detection.application.dtos import EncodedClip
from app.domains.detection.domain.recording import Frame, RecordingSession
from app.domains.detection.domain.repositories import EventRepository


class DetectionUnitOfWork(ABC):
    """交易邊界。use case 以 `async with uow:` 開啟,明確 commit;未 commit 離開即回滾。"""

    events: EventRepository

    @abstractmethod
    async def __aenter__(self) -> Self: ...

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """未 commit 的變更一律回滾。"""

    @abstractmethod
    async def commit(self) -> None: ...


class MediaUploader(ABC):
    """R2 的寫入側(01_資料模型與儲存規格.md 第 3 節)。

    只宣告 detection 用得到的兩個動作:換發播放連結是 timeline 的事,不放在這裡。
    """

    @abstractmethod
    async def upload(self, key: str, data: bytes, *, content_type: str) -> None:
        """上傳物件。失敗時丟 UploadFailed,由 use case 決定要不要重試。"""

    @abstractmethod
    async def delete_many(self, keys: list[str]) -> None:
        """刪除多個物件;不存在的 key 不視為錯誤(冪等)。"""


class Backoff(ABC):
    """重試之間的等待。抽成 port 是為了讓測試不必真的睡 1、2、4 秒。"""

    @abstractmethod
    async def wait(self, attempt: int) -> None:
        """第 attempt 次失敗後的等待(指數退避,07_spec 第 3 節邊界案例)。"""


class PushNotifier(ABC):
    """Push 服務的 POST /internal/notifications/event-ready(09_spec 第 3 節)。"""

    @abstractmethod
    async def notify_event_ready(
        self,
        *,
        device_id: UUID,
        event_id: UUID,
        confidence_score: Decimal,
        thumbnail_object_key: str | None,
        started_at: datetime,
    ) -> None:
        """觸發推播。參數對應 Push 服務的 EventReadyNotification(push/__init__.py)。

        縮圖 key 與 started_at 由本服務夾帶——Push 沒有 events 表,只給 event_id
        它組不出 R2 key(key 含事件日期)。但**不夾帶裝置名稱**:那是 Device 的資料,
        由 Push 自己取即時值,使用者剛改過的鏡頭名稱才會立刻反映在通知標題上。

        防洗版計數窗也由 Push 負責,本服務每次 ready 都照常呼叫。
        失敗不該回頭改事件狀態:事件已經 ready 是事實,推播沒送出是另一回事。
        """


class FrameSource(ABC):
    """鏡頭的影格串流(RTSP + 移動偵測模型)。

    以 async iterator 表達,worker 的迴圈因此不必知道影格從哪來、多久一張;
    測試餵固定腳本,正式環境接 RTSP。串流中斷時丟 CameraDisconnected。
    """

    @abstractmethod
    def frames(self) -> AsyncIterator["Frame"]:
        """持續產出影格,直到串流結束或斷線。"""


class ClipEncoder(ABC):
    """把錄下的畫面轉成可上傳的檔案(ffmpeg)。"""

    @abstractmethod
    async def encode(self, session: "RecordingSession", ended_at: datetime) -> "EncodedClip":
        """產生影片與縮圖(07_spec 第 3.2 節)。"""
