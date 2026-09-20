"""跨服務查詢裝置摘要(服務對外契約 GET /internal/devices/{device_id})。"""

import uuid

from app.domains.devices.application.dtos import DeviceSummaryView
from app.domains.devices.application.ports import DevicesUnitOfWork
from app.domains.devices.domain.exceptions import DeviceNotFound
from app.shared_kernel.ports import Clock


class GetDeviceSummary:
    """給 Event 與 Push 服務用的唯讀查詢。

    devices 表屬於本服務,其他服務不可直接讀(13_ADR 第 1 節)。Event 需要知道某個裝置
    屬於誰(events 表沒有 user_id),Push 需要 name 來組通知標題。
    """

    def __init__(
        self, uow: DevicesUnitOfWork, clock: Clock, *, offline_after_seconds: int
    ) -> None:
        self.uow = uow
        self.clock = clock
        self.offline_after_seconds = offline_after_seconds

    async def execute(self, device_id: uuid.UUID) -> DeviceSummaryView:
        now = self.clock.now()

        async with self.uow:
            device = await self.uow.devices.get(device_id)
            if device is None:
                raise DeviceNotFound()

        return DeviceSummaryView.of(
            device, now=now, offline_after_seconds=self.offline_after_seconds
        )
