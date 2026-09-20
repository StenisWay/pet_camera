"""移除裝置(04_spec 第 2.3 節、01_資料模型 第 6 節、規格審查 #7、#9)。"""

import uuid

from app.domains.devices.application.code_issuing import issue_unique_code
from app.domains.devices.application.ports import (
    DevicesUnitOfWork,
    EventCleanup,
    PairingCodeFactory,
)
from app.domains.devices.domain.exceptions import DeviceNotFound
from app.shared_kernel.ports import Clock


class RemoveDevice:
    """把裝置從使用者名下移除,並清掉它的所有事件與影片。

    這是一個跨服務、沒有共同交易保護的多步驟操作,順序是刻意的(審查 #9):

        1. 驗證擁有者
        2. 請 Event 服務刪掉該裝置的事件與 R2 影片縮圖
        3. 成功之後才 unpair 並 commit

    fail-closed:第 2 步失敗就整個失敗,裝置維持原狀讓使用者重試。反過來做
    (先 unpair 再刪事件)的話,刪事件失敗會留下「事件還在、裝置已回到 pending」的
    狀態,下一位配對者就會看到前一位使用者的寵物活動紀錄——那正是
    01_資料模型 第 6 節寫明要避免的事。刪事件本身是冪等的,所以重試是安全的。

    外部呼叫刻意放在交易之外:不在交易中間等一個跨機的 HTTP 往返。
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

    async def execute(self, *, device_id: uuid.UUID, requester_id: uuid.UUID) -> None:
        now = self.clock.now()

        async with self.uow:
            device = await self.uow.devices.get(device_id)
            if device is None or not device.is_owned_by(requester_id):
                raise DeviceNotFound()

        await self.events.delete_device_events(device_id)

        async with self.uow:
            device = await self.uow.devices.get(device_id)
            if device is None or not device.is_owned_by(requester_id):
                raise DeviceNotFound()

            code = await issue_unique_code(self.uow.devices, self.codes, now=now, max_attempts=3)
            device.unpair(code)
            await self.uow.devices.save(device)
            await self.uow.commit()
