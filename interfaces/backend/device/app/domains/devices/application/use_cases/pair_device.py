"""使用者輸入配對碼完成綁定(03_spec 第 2.2 節)。"""

import uuid

from app.domains.devices.application.dtos import DeviceView
from app.domains.devices.application.ports import DevicesUnitOfWork
from app.domains.devices.domain.exceptions import DeviceLimitReached, PairingCodeInvalid
from app.shared_kernel.ports import Clock


class PairDevice:
    """把一台 pending 裝置綁到目前登入的使用者。

    查不到配對碼就是 DEVICE_002。已配對的裝置 pairing_code 為 null,所以同樣查不到,
    自然落到 DEVICE_002——規格審查 #5 刪掉 DEVICE_003 的理由就在這裡:
    在「配對成功即清碼」的流程下,那個錯誤碼永遠沒有機會被觸發。
    """

    def __init__(
        self,
        uow: DevicesUnitOfWork,
        clock: Clock,
        *,
        offline_after_seconds: int,
        max_devices_per_user: int,
    ) -> None:
        self.uow = uow
        self.clock = clock
        self.offline_after_seconds = offline_after_seconds
        self.max_devices_per_user = max_devices_per_user

    async def execute(self, *, user_id: uuid.UUID, typed_code: str) -> DeviceView:
        now = self.clock.now()

        async with self.uow:
            device = await self.uow.devices.get_by_pairing_code(typed_code)
            if device is None:
                raise PairingCodeInvalid()

            # 審查 #13:上限擋在配對這一步。register 是匿名端點,不設上限的話
            # 會變成「任何人都能把無限多台裝置塞進某個帳號」的放大器。
            if await self.uow.devices.count_by_user(user_id) >= self.max_devices_per_user:
                raise DeviceLimitReached(f"每個帳號最多配對 {self.max_devices_per_user} 台裝置")

            device.pair(user_id=user_id, typed_code=typed_code, now=now)
            await self.uow.devices.save(device)
            await self.uow.commit()

        return DeviceView.of(device, now=now, offline_after_seconds=self.offline_after_seconds)
