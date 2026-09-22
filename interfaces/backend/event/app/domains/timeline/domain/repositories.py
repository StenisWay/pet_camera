"""時間軸的單筆存取介面。"""

from abc import ABC, abstractmethod
from uuid import UUID

from app.domains.timeline.domain.entities import TimelineEvent


class TimelineEventRepository(ABC):
    """只提供業務需要的操作,不做泛用 CRUD。

    timeline 對 events 表幾乎只讀,唯一會寫的是 is_read——那是 F3 自己的閱讀狀態,
    不是 F2 的事件生命週期(狀態機由 detection 推進)。
    """

    @abstractmethod
    async def get(self, event_id: UUID) -> TimelineEvent | None:
        """取回單一事件的唯讀視圖;不存在時回傳 None。

        回傳的是新的物件,修改後必須 save 才會保存。
        """

    @abstractmethod
    async def save_read_state(self, event: TimelineEvent) -> None:
        """只保存 is_read 欄位。

        刻意不是通用的 save:讓 timeline 意外改到 status 或 object key 的路徑
        從介面層級就不存在(08_spec 第 2.3 節只允許改這一個欄位)。
        實際寫入在 UnitOfWork.commit() 時生效。
        """
