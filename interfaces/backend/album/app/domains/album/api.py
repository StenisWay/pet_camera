"""album 領域對其他領域公開的唯一入口。

其他領域只能 import 這個模組,而且只能在自己的 infrastructure 層(adapter)中使用,
不能碰 album 的 domain、application 內部或資料表。目前的使用者是 drive_export:
它需要知道哪些項目可以匯出、取得檔案內容,以及回報匯出結果。
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.album.application.dtos import ExportPreparation
from app.domains.album.application.ports import MediaObjectStorage
from app.domains.album.application.use_cases.prepare_export import PrepareExport
from app.domains.album.application.use_cases.settle_export import SettleExport
from app.domains.album.infrastructure.unit_of_work import SqlAlchemyAlbumUnitOfWork
from app.shared_kernel.ports import Clock


class AlbumApi:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: MediaObjectStorage,
        clock: Clock,
    ) -> None:
        self._uow_factory = lambda: SqlAlchemyAlbumUnitOfWork(session_factory)
        self._storage = storage
        self._clock = clock

    async def prepare_export(
        self, owner_id: uuid.UUID, item_ids: list[uuid.UUID]
    ) -> ExportPreparation:
        """檢核擁有權與狀態,把通過的項目轉成 exporting,回傳上傳所需的資訊。"""
        return await PrepareExport(self._uow_factory(), self._clock).execute(owner_id, item_ids)

    async def complete_export(self, item_id: uuid.UUID, *, drive_file_id: str) -> None:
        await SettleExport(self._uow_factory(), self._clock).succeed(
            item_id, drive_file_id=drive_file_id
        )

    async def fail_export(self, item_id: uuid.UUID) -> None:
        await SettleExport(self._uow_factory(), self._clock).fail(item_id)

    async def read_object(self, object_key: str) -> bytes:
        return await self._storage.download(object_key)
