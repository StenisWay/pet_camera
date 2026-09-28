"""worker 完成/失敗回呼(審查 #3)。

worker 在 VM-3、沒有使用者身分,回呼時只知道 media_item_id。這兩個 use case 因此
走 get_internal,只能掛在共享金鑰把關的內部端點上,不可出現在對外路由。
"""

import uuid

from app.domains.media.application.ports import MediaUnitOfWork
from app.domains.media.domain.exceptions import MediaItemNotFound
from app.shared_kernel.ports import Clock


class CompleteMediaItem:
    def __init__(self, uow: MediaUnitOfWork, clock: Clock) -> None:
        self.uow = uow
        self.clock = clock

    async def execute(
        self, item_id: uuid.UUID, *, object_key: str, thumbnail_object_key: str | None
    ) -> None:
        async with self.uow:
            item = await self.uow.media.get_internal(item_id)
            if item is None:
                raise MediaItemNotFound()
            # 已 ready/failed 時 mark_ready 會拒絕:worker 重試的重複回呼不該翻案
            item.mark_ready(
                object_key=object_key,
                thumbnail_object_key=thumbnail_object_key,
                now=self.clock.now(),
            )
            await self.uow.media.save(item)
            await self.uow.commit()


class FailMediaItem:
    def __init__(self, uow: MediaUnitOfWork, clock: Clock) -> None:
        self.uow = uow
        self.clock = clock

    async def execute(self, item_id: uuid.UUID) -> None:
        async with self.uow:
            item = await self.uow.media.get_internal(item_id)
            if item is None:
                raise MediaItemNotFound()
            item.mark_failed(now=self.clock.now())
            await self.uow.media.save(item)
            await self.uow.commit()
