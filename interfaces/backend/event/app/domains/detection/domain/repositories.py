"""events 聚合的存取介面。實作在 infrastructure,測試替身在 tests。

用 ABC 而不是 Protocol:實作類別明確繼承,漏實作任何方法時建立實例當下就失敗,
讀程式碼的人也一眼看得出這個類別實作的是哪份合約。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from app.domains.detection.domain.entities import Event


@dataclass(frozen=True)
class PurgedEvents:
    """串聯清除的結果。

    筆數與 key 不是同一件事:processing / failed 的事件沒有任何 object key,
    只回傳 key 的話就數不出真正刪了幾筆,而內部端點要回報的是筆數。
    """

    deleted_count: int
    object_keys: list[str]


class EventRepository(ABC):
    """以聚合為單位。列表查詢不在這裡,那是 timeline 的讀取端。"""

    @abstractmethod
    async def get(self, event_id: UUID) -> Event | None:
        """取回單一事件;不存在時回傳 None。

        回傳的是新的實體物件,修改後必須 save 才會保存。
        """

    @abstractmethod
    async def save(self, event: Event) -> None:
        """新增或更新整個聚合。實際寫入在 UnitOfWork.commit() 時生效。"""

    @abstractmethod
    async def delete_all_by_device(self, device_id: UUID) -> PurgedEvents:
        """刪除該裝置所有事件,回傳刪除筆數與對應的 R2 object key(影片 + 縮圖)。

        01_資料模型與儲存規格.md 第 6 節的串聯清除。R2 物件由呼叫端(use case)清除——
        repository 只管資料列,但它是唯一知道有哪些 key 的地方,所以負責把 key 交出來。
        沒有任何事件時回傳 deleted_count = 0 與空 list,不視為錯誤。
        """
