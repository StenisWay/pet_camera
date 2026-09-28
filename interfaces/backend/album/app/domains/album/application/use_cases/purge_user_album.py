import uuid

from app.domains.album.application.ports import AlbumUnitOfWork, MediaObjectStorage
from app.domains.album.application.use_cases.delete_album_item import purge_objects


class PurgeUserAlbum:
    """刪除帳號時的串聯清除(01_資料模型與儲存規格.md 第 6 節)。

    由 Auth 服務跨服務呼叫,見 presentation/internal_router.py。
    """

    def __init__(self, uow: AlbumUnitOfWork, storage: MediaObjectStorage) -> None:
        self.uow = uow
        self.storage = storage

    async def execute(self, owner_id: uuid.UUID) -> int:
        async with self.uow:
            object_keys = await self.uow.items.delete_all_owned_by(owner_id)
            await self.uow.commit()
        await purge_objects(self.storage, object_keys, context=f"user {owner_id}")
        return len(object_keys)
