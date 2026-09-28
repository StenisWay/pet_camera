"""鏡頭心跳回報(03_spec 第 2.3 節、規格審查 #2)。"""

import uuid

from app.domains.devices.application.ports import DeviceSecrets, DevicesUnitOfWork
from app.domains.devices.domain.exceptions import DeviceNotFound
from app.shared_kernel.ports import Clock


class RecordHeartbeat:
    """鏡頭每 30 秒回報一次,更新 last_seen_at。

    規格書沒有定義鏡頭如何驗證身分(審查 #2),等於任何人只要知道 device_id
    就能偽造心跳,讓一台實際已斷線的鏡頭在使用者的列表上永遠顯示「在線」——
    使用者會以為家裡還在錄影。這裡要求帶上 register 當時簽發的 secret。

    secret 不符時回 DeviceNotFound 而不是 401/403:回 401 等於告訴呼叫端
    「這個 device_id 確實存在,只是你沒有正確的憑證」,那是列舉裝置的起點。
    """

    def __init__(self, uow: DevicesUnitOfWork, secrets: DeviceSecrets, clock: Clock) -> None:
        self.uow = uow
        self.secrets = secrets
        self.clock = clock

    async def execute(self, *, device_id: uuid.UUID, device_secret: str) -> None:
        now = self.clock.now()

        async with self.uow:
            device = await self.uow.devices.get(device_id)
            if device is None or not self.secrets.verify(device_secret, device.secret_hash):
                raise DeviceNotFound()

            device.record_heartbeat(now)
            await self.uow.devices.save(device)
            await self.uow.commit()
