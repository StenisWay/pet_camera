"""兩種截圖共用的流程。

順序是重點(審查 #1):先把 processing 紀錄落地拿到 id,才算得出含 media_item_id 的
R2 key;先上傳再寫 DB 會在 DB 失敗時留下無法追蹤來源的孤兒檔案(13_ADR 第 4 節)。
任何一步失敗都要把項目收斂成 failed,否則相簿卡片會一直轉圈到 15 分鐘的逾時掃描
才收掉(審查 #9)。
"""

from collections.abc import Awaitable, Callable

from app.domains.media.application.dtos import MediaItemResult
from app.domains.media.application.ports import CapturedFrame, MediaStorage, MediaUnitOfWork
from app.domains.media.domain.entities import MediaItem
from app.domains.media.domain.exceptions import ScreenshotSourceUnavailable
from app.domains.media.domain.object_keys import content_key, thumbnail_key
from app.shared_kernel.ports import Clock

Capture = Callable[[], Awaitable[CapturedFrame]]


class ScreenshotWorkflow:
    def __init__(self, uow: MediaUnitOfWork, storage: MediaStorage, clock: Clock) -> None:
        self.uow = uow
        self.storage = storage
        self.clock = clock

    async def run(self, item: MediaItem, capture: Capture) -> MediaItemResult:
        async with self.uow:
            await self.uow.media.add(item)
            await self.uow.commit()

        try:
            frame = await capture()
            keys = (content_key(item), thumbnail_key(item))
            await self.storage.put_image(keys[0], frame.image)
            await self.storage.put_image(keys[1], frame.thumbnail)
        except Exception as exc:
            await self._abandon(item)
            raise ScreenshotSourceUnavailable() from exc

        item.mark_ready(
            object_key=keys[0], thumbnail_object_key=keys[1], now=self.clock.now()
        )
        await self._persist(item)
        # 已經是 ready,依審查 #12 一併附上 presigned URL,前端不必再打一次 GET
        return MediaItemResult.from_entity(
            item,
            content_url=await self.storage.presigned_url(keys[0]),
            thumbnail_url=await self.storage.presigned_url(keys[1]),
        )

    async def _abandon(self, item: MediaItem) -> None:
        item.mark_failed(now=self.clock.now())
        await self._persist(item)

    async def _persist(self, item: MediaItem) -> None:
        async with self.uow:
            await self.uow.media.save(item)
            await self.uow.commit()
