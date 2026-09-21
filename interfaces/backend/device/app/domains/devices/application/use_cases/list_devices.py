"""裝置列表(04_spec 第 2.1 節)。"""

import uuid

from app.domains.devices.application.dtos import DeviceView
from app.domains.devices.application.ports import DevicesUnitOfWork
from app.shared_kernel.ports import Clock


class ListDevices:
    """使用者名下所有已配對裝置,含即時推導的線上/離線狀態。

    純讀取,不開寫入交易也不 commit。回傳順序由 repository 保證(created_at 由舊到新,
    審查 #13),不分頁——一般家庭 1~5 台,配對上限 20 台。
    """

    def __init__(
        self, uow: DevicesUnitOfWork, clock: Clock, *, offline_after_seconds: int
    ) -> None:
        self.uow = uow
        self.clock = clock
        self.offline_after_seconds = offline_after_seconds

    async def execute(self, user_id: uuid.UUID) -> list[DeviceView]:
        now = self.clock.now()

        async with self.uow:
            devices = await self.uow.devices.list_by_user(user_id)

        return [
            DeviceView.of(d, now=now, offline_after_seconds=self.offline_after_seconds)
            for d in devices
        ]
