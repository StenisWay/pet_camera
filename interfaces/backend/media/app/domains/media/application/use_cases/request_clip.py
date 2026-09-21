"""F5 §2.2:從歷史事件剪輯。"""

import uuid
from datetime import timedelta

from app.domains.media.application.dtos import MediaItemResult
from app.domains.media.application.ports import ClipWorker, EventSource, MediaUnitOfWork
from app.domains.media.domain.entities import ClipRange, MediaItem
from app.domains.media.domain.exceptions import ClipDispatchFailed, MediaItemNotFound
from app.domains.media.domain.object_keys import content_key, thumbnail_key
from app.shared_kernel.ports import Clock, IdGenerator


class RequestClip:
    def __init__(
        self,
        uow: MediaUnitOfWork,
        events: EventSource,
        worker: ClipWorker,
        clock: Clock,
        ids: IdGenerator,
        *,
        retention: timedelta,
    ) -> None:
        self.uow = uow
        self.events = events
        self.worker = worker
        self.clock = clock
        self.ids = ids
        self.retention = retention

    async def execute(
        self, event_id: uuid.UUID, *, start_sec: int, end_sec: int, requester_id: uuid.UUID
    ) -> MediaItemResult:
        event = await self.events.get(event_id)
        if event is None:
            raise MediaItemNotFound()
        now = self.clock.now()
        event.ensure_usable_by(requester_id, now=now, retention=self.retention)

        clip_range = ClipRange(start_sec=start_sec, end_sec=end_sec)
        clip_range.ensure_within(source_duration_sec=event.duration_sec)

        async with self.uow:
            existing = await self.uow.media.find_active_clip(
                owner_id=requester_id,
                source_event_id=event.id,
                captured_at=event.moment_of(clip_range.start_sec),
                duration_sec=clip_range.duration_sec,
            )
            if existing is not None:
                # 審查 #10:同一段範圍已在處理或已完成,回既有項目,不重複派工
                return MediaItemResult.from_entity(existing)

            item = MediaItem.start_clip(
                item_id=self.ids.new_id(),
                owner_id=requester_id,
                event=event,
                clip_range=clip_range,
                now=now,
            )
            await self.uow.media.add(item)
            await self.uow.commit()

        try:
            # key 由本服務算好交給 worker(資料模型 §3.1),不讓 worker 自己決定位置
            await self.worker.dispatch(
                media_item_id=item.id,
                source_event_id=event.id,
                start_sec=clip_range.start_sec,
                end_sec=clip_range.end_sec,
                object_key=content_key(item),
                thumbnail_object_key=thumbnail_key(item),
            )
        except Exception as exc:
            item.mark_failed(now=self.clock.now())
            async with self.uow:
                await self.uow.media.save(item)
                await self.uow.commit()
            raise ClipDispatchFailed() from exc

        return MediaItemResult.from_entity(item)
