"""F5 §2.1:即時畫面截圖。"""

import uuid

from app.domains.media.application.dtos import MediaItemResult
from app.domains.media.application.ports import (
    DeviceDirectory,
    FrameSource,
    MediaStorage,
    MediaUnitOfWork,
)
from app.domains.media.application.use_cases._screenshot import ScreenshotWorkflow
from app.domains.media.domain.entities import MediaItem
from app.domains.media.domain.exceptions import (
    MediaItemNotFound,
    ScreenshotSourceUnavailable,
)
from app.shared_kernel.ports import Clock, IdGenerator


class TakeLiveScreenshot:
    def __init__(
        self,
        uow: MediaUnitOfWork,
        devices: DeviceDirectory,
        frames: FrameSource,
        storage: MediaStorage,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self.devices = devices
        self.frames = frames
        self.clock = clock
        self.ids = ids
        self.workflow = ScreenshotWorkflow(uow, storage, clock)

    async def execute(self, device_id: uuid.UUID, *, requester_id: uuid.UUID) -> MediaItemResult:
        device = await self.devices.get(device_id)
        if device is None or device.owner_id != requester_id:
            # 審查 #6:非本人與不存在不可區分
            raise MediaItemNotFound()
        if not device.is_online:
            # 鏡頭沒有畫面可擷取(SCREENSHOT_001)
            raise ScreenshotSourceUnavailable()

        now = self.clock.now()
        item = MediaItem.start_photo(
            item_id=self.ids.new_id(),
            owner_id=requester_id,
            device_id=device_id,
            captured_at=now,
            now=now,
        )
        return await self.workflow.run(item, lambda: self.frames.capture_live_frame(device_id))
