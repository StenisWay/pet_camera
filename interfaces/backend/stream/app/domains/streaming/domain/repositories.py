"""Repository 介面。實作是 Redis-backed(本服務不擁有任何 Postgres 資料表,
見 13_ADR_微服務與三節點部署.md 第 1 節),但這一層不知道那件事。

docstring 就是合約:contracts/ 底下的合約測試逐條驗證這些承諾,fake 與 Redis
兩個實作都要通過。
"""

import uuid
from abc import ABC, abstractmethod

from app.domains.streaming.domain.entities import StreamSession


class StreamSessionRepository(ABC):
    @abstractmethod
    async def get(self, session_id: uuid.UUID) -> StreamSession | None:
        """取回 session;不存在或已超過效期時回傳 None。

        回傳的是新的物件,對它的修改必須再 save 才會保存。
        """

    @abstractmethod
    async def get_active_for_device(self, device_id: uuid.UUID) -> StreamSession | None:
        """回傳該裝置目前的 session(供接管判斷);沒有則 None。

        同一支裝置至多一個 session——這是第 2.4 節接管語意的直接結果。
        """

    @abstractmethod
    async def save(self, session: StreamSession) -> None:
        """新增或覆寫 session,並把裝置索引指向它。

        接管語意(last-writer-wins):同一裝置既有的 session 會被這個取代,
        之後用舊 session_id 呼叫 get 必須回 None。
        效期以 session.expires_at 為準,到期後自動消失。
        """

    @abstractmethod
    async def delete(self, session_id: uuid.UUID) -> None:
        """刪除 session 與其裝置索引。

        不存在時視為成功(冪等)——第 3.1 節規定重複 DELETE 一律 204。
        """
