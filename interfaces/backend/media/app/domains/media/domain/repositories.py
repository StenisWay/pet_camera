"""repository 介面:由 domain 定義「需要什麼」,infrastructure 與測試替身負責實作。

用 ABC 而非 Protocol:實作類別必須明確繼承,漏實作任何方法時在建立實例當下就失敗。
(對外契約 media/__init__.py 用 Protocol 是另一回事——那是給其他服務讀的形狀描述。)
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime

from app.domains.media.domain.entities import MediaItem


class MediaItemRepository(ABC):
    @abstractmethod
    async def get(self, item_id: uuid.UUID, *, owner_id: uuid.UUID) -> MediaItem | None:
        """取回本人的項目;不存在**或不屬於該使用者**時一律回傳 None(審查 #6)。

        回傳的是新的實體物件,修改後必須 save 才會保存。

        `updated_at` 由**儲存層**維護(資料模型第 2.0 節:trigger set_updated_at(),
        七個服務寫同一個庫,不依賴應用程式寫入),呼叫端不可假設它等於存進去時
        帶的值——只保證它反映最後一次寫入的時間,逾時掃描據此判定。
        """

    @abstractmethod
    async def get_internal(self, item_id: uuid.UUID) -> MediaItem | None:
        """不限擁有者的取回,僅供 worker 回呼與逾時掃描使用。

        worker 沒有使用者身分,回呼時只知道 media_item_id;這個方法不可掛在任何
        對外端點上。
        """

    @abstractmethod
    async def add(self, item: MediaItem) -> None:
        """新增一筆項目。id 由應用程式產生(UUIDv7),實際寫入在 commit 時生效。"""

    @abstractmethod
    async def save(self, item: MediaItem) -> None:
        """保存整個聚合(狀態、object key、長度)。實際寫入在 commit 時生效。"""

    @abstractmethod
    async def find_active_clip(
        self,
        *,
        owner_id: uuid.UUID,
        source_event_id: uuid.UUID,
        captured_at: datetime,
        duration_sec: int,
    ) -> MediaItem | None:
        """找出同一使用者對同一段範圍、仍 processing 或已 ready 的剪輯(審查 #10)。

        failed 的不算——使用者重送就是要重試。找不到時回傳 None。
        (captured_at + duration_sec 即可唯一識別範圍,不必為此加欄位。)
        """

    @abstractmethod
    async def list_stale_processing(self, *, changed_before: datetime) -> list[MediaItem]:
        """取出停留在 processing 且 updated_at 早於指定時點的項目(審查 #9)。

        沒有符合的項目時回傳空 list,不是 None。
        """
