"""repository 介面:由 domain 定義「需要什麼」,infrastructure 與測試替身負責實作。

用 ABC 而非 Protocol:實作類別必須明確繼承,漏實作任何方法時在建立實例當下就失敗。
"""

import uuid
from abc import ABC, abstractmethod

from app.domains.push_tokens.domain.entities import ClientPlatform, PushToken


class PushTokenRepository(ABC):
    @abstractmethod
    async def get(self, push_token_id: uuid.UUID) -> PushToken | None:
        """取回單筆登記;不存在時回傳 None。

        DELETE /push-tokens/{id} 刪除前驗證擁有者用(審查 #5)。回傳的是新的實體物件,
        修改後必須 save 才會保存。
        """

    @abstractmethod
    async def find_by_endpoint(self, platform: ClientPlatform, token: str) -> PushToken | None:
        """以 (platform, token) 找出既有登記;不存在時回傳 None。

        這是唯一鍵(01_資料模型與儲存規格.md 第 2.6 節),不含 user_id——同一個端點
        只會有一筆,不論目前綁在誰名下(審查 #4)。
        """

    @abstractmethod
    async def list_by_user(self, user_id: uuid.UUID) -> list[PushToken]:
        """該使用者名下所有登記,依 created_at 由舊到新。

        發送推播時取出收件端點,也供 GET /push-tokens 還原設定頁開關(審查 #11)。
        """

    @abstractmethod
    async def save(self, push_token: PushToken) -> PushToken:
        """新增或更新一筆登記,回傳實際保存的登記。實際寫入在 UnitOfWork.commit() 時生效。

        同一個 (platform, token) 若已被另一筆登記佔用(兩個請求同時登記同一端點),
        不新增第二筆,而是把既有那筆改綁到 push_token.user_id,回傳既有那筆——
        id 與 created_at 以既有的為準。
        """

    @abstractmethod
    async def delete(self, push_token_id: uuid.UUID) -> None:
        """刪除一筆登記;不存在時不視為錯誤。實際生效在 commit() 時。

        使用者解除登記(審查 #5 驗過擁有者後),以及推播服務回報端點失效(PUSH_003,
        審查 #9)都走這裡。
        """
