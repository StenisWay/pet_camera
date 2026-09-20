"""鏡頭註冊(03_spec 第 2.1 節、規格審查 #3)。"""

from app.domains.devices.application.code_issuing import issue_unique_code
from app.domains.devices.application.dtos import RegisteredDevice
from app.domains.devices.application.ports import (
    DeviceSecrets,
    DevicesUnitOfWork,
    PairingCodeFactory,
)
from app.domains.devices.domain.entities import Device, DeviceStatus
from app.shared_kernel.ports import Clock, IdGenerator


class RegisterDevice:
    """鏡頭開機時呼叫,取得配對碼。

    規格書只寫了「鏡頭開機後呼叫 /devices/register」,沒有處理「已配對的鏡頭重開機也會
    開機」這件事(審查 #3)。若每次開機都建一筆新列,同一台實體鏡頭會在 devices 表裡
    累積多筆,使用者列表指向舊的 device_id、事件寫到舊的 device_id,新那筆變成孤兒。

    因此以鏡頭自己持久化的 hardware_id 當冪等鍵,分三種情況:

    | 既有紀錄 | 行為 |
    |---|---|
    | 沒有 | 建立 pending 列,簽發 secret 與配對碼 |
    | pending | 沿用同一列,只換一組新配對碼並延長效期 |
    | paired | 什麼都不發,只回 device_id,鏡頭直接開始送心跳 |

    secret 只在**建立新列**時簽發一次。已存在的裝置不重發:hardware_id 不是秘密,
    否則任何知道 hardware_id 的人都能呼叫這個匿名端點換走一組有效憑證,
    等於接管那台鏡頭的身分。鏡頭遺失 secret 需要回復原廠設定(見 README 已知限制)。
    """

    def __init__(
        self,
        uow: DevicesUnitOfWork,
        codes: PairingCodeFactory,
        secrets: DeviceSecrets,
        clock: Clock,
        ids: IdGenerator,
        *,
        default_name: str,
        max_code_attempts: int,
    ) -> None:
        self.uow = uow
        self.codes = codes
        self.secrets = secrets
        self.clock = clock
        self.ids = ids
        self.default_name = default_name
        self.max_code_attempts = max_code_attempts

    async def execute(self, hardware_id: str) -> RegisteredDevice:
        now = self.clock.now()

        async with self.uow:
            existing = await self.uow.devices.get_by_hardware_id(hardware_id)

            if existing is not None and existing.status is DeviceStatus.PAIRED:
                return RegisteredDevice(
                    device_id=existing.id,
                    status=existing.status,
                    device_secret=None,
                    pairing_code=None,
                    pairing_code_expires_at=None,
                )

            code = await issue_unique_code(
                self.uow.devices, self.codes, now=now, max_attempts=self.max_code_attempts
            )

            if existing is not None:
                existing.reissue_pairing_code(code)
                device = existing
                secret = None
            else:
                secret, secret_hash = self.secrets.issue()
                device = Device.register(
                    id=self.ids.new_id(),
                    hardware_id=hardware_id,
                    secret_hash=secret_hash,
                    pairing_code=code,
                    name=self.default_name,
                    now=now,
                )

            await self.uow.devices.save(device)
            await self.uow.commit()

        return RegisteredDevice(
            device_id=device.id,
            status=device.status,
            device_secret=secret,
            pairing_code=code.code,
            pairing_code_expires_at=code.expires_at,
        )
