"""刪除帳號時串聯移除該使用者名下所有裝置(規格審查 #8)。"""

import uuid

from app.domains.devices.application.code_issuing import issue_unique_code
from app.domains.devices.application.ports import (
    DevicesUnitOfWork,
    EventCleanup,
    PairingCodeFactory,
)
from app.shared_kernel.ports import Clock


class RemoveUserDevices:
    """由 Auth 服務在刪除 users 那一列**之前**呼叫。

    為什麼需要這個端點(審查 #8):01_資料模型 第 2.2 節把 devices.user_id 定成
    ON DELETE SET NULL,但同一節的 CHECK 又要求「status = 'pending' 與 user_id is null
    必須同時成立」。直接刪除 users 會讓該帳號名下 status = 'paired' 的裝置被設成
    user_id = null,當場違反 CHECK,刪除帳號那句 SQL 會失敗。而且 SET NULL 也不會重置
    status、不會重發配對碼、不會刪事件,語意上根本不等於「移除裝置」。

    對每台裝置執行與 RemoveDevice 相同的 fail-closed 流程:任何一台的事件清不掉,
    整個操作就失敗,Auth 不會繼續往下刪帳號。
    """

    def __init__(
        self,
        uow: DevicesUnitOfWork,
        events: EventCleanup,
        codes: PairingCodeFactory,
        clock: Clock,
    ) -> None:
        self.uow = uow
        self.events = events
        self.codes = codes
        self.clock = clock

    async def execute(self, user_id: uuid.UUID) -> int:
        now = self.clock.now()

        async with self.uow:
            device_ids = [d.id for d in await self.uow.devices.list_by_user(user_id)]

        if not device_ids:
            return 0

        for device_id in device_ids:
            await self.events.delete_device_events(device_id)

        async with self.uow:
            removed = 0
            for device_id in device_ids:
                device = await self.uow.devices.get(device_id)
                if device is None or not device.is_owned_by(user_id):
                    continue  # 同時被使用者自己移除了,當作已完成
                code = await issue_unique_code(
                    self.uow.devices, self.codes, now=now, max_attempts=3
                )
                device.unpair(code)
                await self.uow.devices.save(device)
                removed += 1
            await self.uow.commit()

        return removed
