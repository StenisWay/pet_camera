"""application 層需要、但由外層實作的介面。"""

import uuid
from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.domains.album.application.dtos import AlbumPageResult
from app.domains.album.domain.repositories import AlbumItemRepository
from app.domains.album.domain.value_objects import DateRange, PageSize


class AlbumUnitOfWork(ABC):
    """交易邊界。use case 以 `async with uow:` 開啟,明確 commit;未 commit 離開即回滾。"""

    items: AlbumItemRepository

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


class AlbumQueries(ABC):
    """相簿列表的讀取端。

    純查詢、沒有業務規則,所以直接回傳 DTO 而不經過實體(CQRS 的讀取端)——
    列表一次 30 筆,為了顯示縮圖而把每一筆都組成完整實體沒有意義。
    """

    @abstractmethod
    async def list_page(
        self,
        owner_id: uuid.UUID,
        *,
        cursor: str | None,
        page_size: PageSize,
        date_range: DateRange,
    ) -> AlbumPageResult:
        """依 captured_at 由新到舊回傳一頁。

        回傳 processing / ready / failed 三種狀態的項目(規格審查 #1),
        由前端依 status 決定呈現方式。還有下一頁時 next_cursor 不為 None。
        """


class MediaObjectStorage(ABC):
    """Cloudflare R2。key 命名規則見 01_資料模型與儲存規格.md 第 3.1 節。"""

    @abstractmethod
    async def download(self, object_key: str) -> bytes:
        """取出物件內容。"""

    @abstractmethod
    async def delete(self, object_key: str) -> None:
        """刪除物件;物件不存在時不視為錯誤。"""

    @abstractmethod
    async def presigned_url(self, object_key: str) -> str:
        """產生一次性下載連結,效期 10 分鐘(01_資料模型與儲存規格.md 第 3.3 節)。"""
