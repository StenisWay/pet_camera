"""application 需要、但由外層實作的介面。以 detection 自己的語言命名。"""

from abc import ABC, abstractmethod
from decimal import Decimal
from types import TracebackType
from typing import Self
from uuid import UUID

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
    """Push 服務(09_spec 第 3.1 節)。"""

    @abstractmethod
    async def notify_event_ready(
        self, *, device_id: UUID, event_id: UUID, confidence_score: Decimal
    ) -> None:
        """觸發推播。

        裝置名稱與防洗版計數窗由 Push 服務負責——devices 表不屬於本服務。
        失敗不該回頭改事件狀態:事件已經 ready 是事實,推播沒送出是另一回事。
        """
