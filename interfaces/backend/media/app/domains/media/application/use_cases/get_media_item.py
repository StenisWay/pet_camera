"""F5 §3:查詢單一項目的處理狀態與內容。"""

import uuid

from app.domains.media.application.dtos import MediaItemResult
from app.domains.media.application.ports import MediaStorage, MediaUnitOfWork
from app.domains.media.domain.exceptions import MediaItemNotFound


class GetMediaItem:
    def __init__(self, uow: MediaUnitOfWork, storage: MediaStorage) -> None:
        self.uow = uow
        self.storage = storage

    async def execute(self, item_id: uuid.UUID, *, requester_id: uuid.UUID) -> MediaItemResult:
        async with self.uow:
            # repository 以 owner_id 過濾:非本人與不存在都回 None(審查 #6)
            item = await self.uow.media.get(item_id, owner_id=requester_id)
        if item is None:
            raise MediaItemNotFound()

        # 12_spec 第 2.1 節:非 ready 的項目不提供內容連結。
        # 一併擋掉「ready 但沒有 object_key」——實體與 DB 約束都保證不會發生,
        # 真的發生也不該回一個指向空物件的連結。
        if not item.is_ready or item.object_key is None:
            return MediaItemResult.from_entity(item)

        return MediaItemResult.from_entity(
            item,
            content_url=await self.storage.presigned_url(item.object_key),
            thumbnail_url=(
                await self.storage.presigned_url(item.thumbnail_object_key)
                if item.thumbnail_object_key
                else None
            ),
        )
