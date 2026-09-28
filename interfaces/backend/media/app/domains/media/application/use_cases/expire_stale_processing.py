"""審查 #9:把卡住的 processing 改判 failed,讓狀態機有終止保證。"""

from datetime import timedelta

from app.domains.media.application.ports import MediaUnitOfWork
from app.shared_kernel.ports import Clock


class ExpireStaleProcessing:
    def __init__(self, uow: MediaUnitOfWork, clock: Clock, *, stale_after: timedelta) -> None:
        self.uow = uow
        self.clock = clock
        self.stale_after = stale_after

    async def execute(self) -> int:
        """回傳被改判的項目數。"""
        now = self.clock.now()
        async with self.uow:
            stuck = await self.uow.media.list_stale_processing(
                changed_before=now - self.stale_after
            )
            if not stuck:
                return 0
            for item in stuck:
                item.mark_failed(now=now)
                await self.uow.media.save(item)
            await self.uow.commit()
        return len(stuck)
