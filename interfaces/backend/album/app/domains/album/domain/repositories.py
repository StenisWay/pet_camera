"""repository 介面:由 domain 定義「需要什麼」,infrastructure 與測試替身負責實作。

用 ABC 而非 Protocol:實作類別必須明確繼承,漏實作任何方法時在建立實例當下就失敗。
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime

from app.domains.album.domain.entities import AlbumItem


class AlbumItemRepository(ABC):
    @abstractmethod
    async def get(self, item_id: uuid.UUID) -> AlbumItem | None:
        """取回單一項目;不存在時回傳 None。

        回傳的是新的實體物件,修改後必須 save 才會保存。
        """

    @abstractmethod
    async def get_many(self, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, AlbumItem]:
        """一次取回多個項目,以 id 為鍵;查不到的 id 不會出現在結果中。

        匯出一次最多 50 筆(規格審查 #6),逐筆 get 會變成 50 次往返。
        """

    @abstractmethod
    async def save(self, item: AlbumItem) -> None:
        """更新項目中由 Album 服務負責的欄位(匯出狀態)。

        Album 不建立 media_items(那是 Media 服務的職責),所以這裡只更新不新增。
        實際寫入在 UnitOfWork.commit() 時生效。
        """

    @abstractmethod
    async def delete(self, item_id: uuid.UUID) -> None:
        """刪除單一項目;R2 物件由呼叫端另行清除。實際生效在 commit() 時。"""

    @abstractmethod
    async def delete_all_owned_by(self, owner_id: uuid.UUID) -> list[str]:
        """刪除該使用者所有項目,回傳被刪項目對應的 R2 object key(含縮圖)。

        由 Auth 服務在刪除帳號時觸發(01_資料模型與儲存規格.md 第 6 節)。
        回傳 key 而不是讓呼叫端自己分頁掃一遍整個相簿。
        """

    @abstractmethod
    async def list_stale_exports(self, *, changed_before: datetime) -> list[AlbumItem]:
        """取出停留在 exporting 且狀態變更時間早於指定時點的項目(規格審查 #7)。"""
