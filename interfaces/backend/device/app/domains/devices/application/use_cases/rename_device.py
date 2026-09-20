"""重新命名裝置(04_spec 第 2.2 節)。"""

import uuid

from app.domains.devices.application.dtos import DeviceView
from app.domains.devices.application.ports import DevicesUnitOfWork
from app.domains.devices.domain.exceptions import DeviceNotFound
from app.shared_kernel.ports import Clock


class RenameDevice:
    """改名。名稱規則由實體把關(審查 #11),這裡只負責權限與交易。

    非本人的裝置一律回 DeviceNotFound(審查 #1):規格書原本完全沒提擁有者驗證,
    等於任何登入者帶別人的 device_id 就能改對方鏡頭的名字。
    """

    def __init__(
        self,
        uow: DevicesUnitOfWork,
        clock: Clock,
        *,
        offline_after_seconds: int,
        name_max_length: int,
    ) -> None:
        self.uow = uow
        self.clock = clock
        self.offline_after_seconds = offline_after_seconds
        self.name_max_length = name_max_length

    async def execute(
        self, *, device_id: uuid.UUID, requester_id: uuid.UUID, name: str
    ) -> DeviceView:
        now = self.clock.now()

        async with self.uow:
            device = await self.uow.devices.get(device_id)
            if device is None or not device.is_owned_by(requester_id):
                raise DeviceNotFound()

            device.rename(name, max_length=self.name_max_length)
            await self.uow.devices.save(device)
            await self.uow.commit()

        return DeviceView.of(device, now=now, offline_after_seconds=self.offline_after_seconds)
