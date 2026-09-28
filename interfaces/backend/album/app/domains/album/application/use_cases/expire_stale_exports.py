from datetime import timedelta

from app.domains.album.application.ports import AlbumUnitOfWork
from app.shared_kernel.ports import Clock


class ExpireStaleExports:
    """規格審查 #7:把卡在 exporting 的項目改判 failed,讓匯出狀態機有終止保證。"""

    def __init__(self, uow: AlbumUnitOfWork, clock: Clock, *, stale_after: timedelta) -> None:
        self.uow = uow
        self.clock = clock
        self.stale_after = stale_after

    async def execute(self) -> int:
        now = self.clock.now()
        async with self.uow:
            candidates = await self.uow.items.list_stale_exports(
                changed_before=now - self.stale_after
            )
            stale = [i for i in candidates if i.is_export_stale(now=now, after=self.stale_after)]
            for item in stale:
                item.fail_export(now)
                await self.uow.items.save(item)
            await self.uow.commit()
        return len(stale)
