import uuid

from app.domains.album.application.ports import AlbumUnitOfWork
from app.domains.album.domain.exceptions import AlbumItemNotFound
from app.shared_kernel.ports import Clock


class SettleExport:
    """記錄一次匯出的最終結果。由 drive_export 領域透過 album.api 呼叫。"""

    def __init__(self, uow: AlbumUnitOfWork, clock: Clock) -> None:
        self.uow = uow
        self.clock = clock

    async def succeed(self, item_id: uuid.UUID, *, drive_file_id: str) -> None:
        await self._settle(item_id, lambda item, now: item.complete_export(
            drive_file_id=drive_file_id, now=now
        ))

    async def fail(self, item_id: uuid.UUID) -> None:
        """DRIVE_002:匯出失敗只改匯出狀態,項目本身仍可正常瀏覽。"""
        await self._settle(item_id, lambda item, now: item.fail_export(now))

    async def _settle(self, item_id: uuid.UUID, apply) -> None:
        async with self.uow:
            item = await self.uow.items.get(item_id)
            if item is None:
                # 受理後、上傳完成前被使用者刪掉了:背景任務不該因此爆掉
                raise AlbumItemNotFound()
            apply(item, self.clock.now())
            await self.uow.items.save(item)
            await self.uow.commit()
