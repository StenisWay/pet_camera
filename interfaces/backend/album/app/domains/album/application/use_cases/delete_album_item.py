import logging
import uuid

from app.domains.album.application.ports import AlbumUnitOfWork, MediaObjectStorage
from app.domains.album.domain.exceptions import AlbumItemNotFound

logger = logging.getLogger(__name__)


class DeleteAlbumItem:
    """12_spec 第 2.2 節:刪除 media_items 紀錄,連同對應 R2 物件一併刪除。"""

    def __init__(self, uow: AlbumUnitOfWork, storage: MediaObjectStorage) -> None:
        self.uow = uow
        self.storage = storage

    async def execute(self, item_id: uuid.UUID, requester_id: uuid.UUID) -> None:
        async with self.uow:
            item = await self.uow.items.get(item_id)
            # 不存在與非本人回相同錯誤,避免洩漏資源存在性(規格審查 #4)
            if item is None or not item.is_owned_by(requester_id):
                raise AlbumItemNotFound()
            object_keys = item.object_keys
            await self.uow.items.delete(item.id)
            await self.uow.commit()

        # 交易外才動 R2:外部呼叫不放在交易內,而且 DB 紀錄已經刪掉,
        # 使用者看到的相簿狀態已經正確
        await purge_objects(self.storage, object_keys, context=f"media item {item_id}")


async def purge_objects(
    storage: MediaObjectStorage, object_keys: list[str], *, context: str
) -> None:
    """R2 刪除失敗不讓整個請求失敗。

    media/ 沒有 lifecycle rule(01_資料模型與儲存規格.md 第 3.2 節),刪不掉的物件
    不會自己過期,所以要記下來供後續清理。
    """
    for key in object_keys:
        try:
            await storage.delete(key)
        except Exception:
            logger.warning(
                "orphan R2 object left behind after deleting %s: %s", context, key, exc_info=True
            )
