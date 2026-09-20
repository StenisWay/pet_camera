"""application 需要、但由外層實作的介面。以 timeline 自己的語言命名。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import TracebackType
from typing import Self
from uuid import UUID

from app.domains.timeline.domain.entities import TimelineEvent
from app.domains.timeline.domain.repositories import TimelineEventRepository
from app.domains.timeline.domain.value_objects import DateRange, PageSize, TimelineCursor


class TimelineUnitOfWork(ABC):
    """交易邊界。use case 以 `async with uow:` 開啟,明確 commit;未 commit 離開即回滾。"""

    events: TimelineEventRepository

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


@dataclass(frozen=True)
class TimelinePage:
    items: list[TimelineEvent]
    next_cursor: TimelineCursor | None


class TimelineQueries(ABC):
    """列表的讀取端。

    純查詢、沒有業務規則,所以不經過聚合也不經過 UnitOfWork(CQRS 的讀取端)——
    一頁 20 筆只是為了顯示,把每一筆都組成完整聚合沒有意義。
    """

    @abstractmethod
    async def list_by_device(
        self,
        device_id: UUID,
        *,
        cursor: TimelineCursor | None,
        page_size: PageSize,
        date_range: DateRange,
    ) -> TimelinePage:
        """依 started_at 由新到舊回傳一頁,含 processing / ready / failed 三種狀態。

        還有下一頁時 next_cursor 不為 None。資料層不可用時丟 ServiceUnavailable,
        **不可回空列表**(13_ADR 第 4 節:Event 的讀取選一致性)。
        """


class DeviceOwnership(ABC):
    """Device 服務的 GET /internal/devices/{device_id}(04_spec 第 3 節)。

    events 沒有 user_id、devices 表也不屬於本服務,但三個對外端點都要驗證擁有者,
    否則任何登入者都能看別人的寵物影片(規格審查 #2)。
    """

    @abstractmethod
    async def is_owned_by(self, device_id: UUID, user_id: UUID) -> bool:
        """該裝置目前是否屬於這個使用者。

        裝置不存在、未配對、或屬於別人一律回 False——呼叫端會一律轉成 404,
        回 403 等於承認這個 id 存在。
        """


class MediaUrlIssuer(ABC):
    """R2 的讀取側:換發短效下載連結(08_spec 第 2.2 節)。"""

    @abstractmethod
    async def presigned_url(self, object_key: str) -> str:
        """有效期 10 分鐘。

        注意:presigned URL 無法做到真正的一次性,有效期內可重複使用——
        規格上的承諾因此是「短效」而不是「一次性」。
        """
