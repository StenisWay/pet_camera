"""F5 §2.1:歷史事件回放截圖。"""

import uuid
from datetime import timedelta

from app.domains.media.application.dtos import MediaItemResult
from app.domains.media.application.ports import (
    EventSource,
    FrameSource,
    MediaStorage,
    MediaUnitOfWork,
)
from app.domains.media.application.use_cases._screenshot import ScreenshotWorkflow
from app.domains.media.domain.entities import MediaItem
from app.domains.media.domain.exceptions import MediaItemNotFound
from app.shared_kernel.ports import Clock, IdGenerator


class TakeEventScreenshot:
    def __init__(
        self,
        uow: MediaUnitOfWork,
        events: EventSource,
        frames: FrameSource,
        storage: MediaStorage,
        clock: Clock,
        ids: IdGenerator,
        *,
        retention: timedelta,
    ) -> None:
        self.events = events
        self.frames = frames
        self.clock = clock
        self.ids = ids
        self.retention = retention
        self.workflow = ScreenshotWorkflow(uow, storage, clock)

    async def execute(
        self, event_id: uuid.UUID, *, offset_sec: int, requester_id: uuid.UUID
    ) -> MediaItemResult:
        event = await self.events.get(event_id)
        if event is None:
            raise MediaItemNotFound()
        now = self.clock.now()
        event.ensure_usable_by(requester_id, now=now, retention=self.retention)
        event.ensure_covers(offset_sec)

        item = MediaItem.start_photo(
            item_id=self.ids.new_id(),
            owner_id=requester_id,
            device_id=event.device_id,
            captured_at=event.started_at + timedelta(seconds=offset_sec),
            source_event_id=event.id,
            now=now,
        )
        return await self.workflow.run(
            item, lambda: self.frames.capture_event_frame(event_id, offset_sec=offset_sec)
        )
