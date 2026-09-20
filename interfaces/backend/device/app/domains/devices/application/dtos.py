"""application 層的輸入輸出。

用 frozen dataclass 而不是 Pydantic:這一層不依賴框架。Pydantic 只出現在 presentation,
負責 HTTP 的驗證與序列化。

也不把實體直接回傳給外層——否則 router 可以繞過 use case 呼叫實體方法改狀態。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.domains.devices.domain.entities import Device, DeviceStatus


@dataclass(frozen=True)
class RegisteredDevice:
    """POST /devices/register 的結果(03_spec 第 2.1 節、審查 #2、#3)。

    device_secret 是明碼,**只有在這個 DTO 裡出現過一次**,資料庫只存雜湊。
    已配對的鏡頭重開機再次註冊時 pairing_code 為 None:它不需要、也不該再拿到配對碼
    (審查 #3),鏡頭收到 None 就直接開始送心跳。
    """

    device_id: uuid.UUID
    status: DeviceStatus
    device_secret: str | None
    pairing_code: str | None
    pairing_code_expires_at: datetime | None


@dataclass(frozen=True)
class DeviceView:
    """使用者看到的一台裝置(04_spec 第 2.1 節)。

    刻意不含 pairing_code、secret_hash、user_id:配對憑證不外流,
    user_id 對呼叫者而言永遠是他自己,沒有回傳的必要。
    status 是 display_status() 推導出來的值,可能是 offline(審查 #6)。
    """

    id: uuid.UUID
    name: str
    status: DeviceStatus
    last_seen_at: datetime | None
    created_at: datetime

    @classmethod
    def of(cls, device: Device, *, now: datetime, offline_after_seconds: int) -> "DeviceView":
        return cls(
            id=device.id,
            name=device.name,
            status=device.display_status(now, offline_after_seconds=offline_after_seconds),
            last_seen_at=device.last_seen_at,
            created_at=device.created_at,
        )


@dataclass(frozen=True)
class DeviceSummaryView:
    """GET /internal/devices/{device_id} 的結果。

    給 Event 與 Push 服務用(見服務對外契約 interfaces/backend/device/__init__.py):
    events 表沒有 user_id,Event 必須問本服務才知道某個裝置屬於誰;
    Push 需要 name 來組通知標題。只公開這幾個欄位,不外流配對憑證。
    """

    id: uuid.UUID
    name: str
    user_id: uuid.UUID | None
    status: DeviceStatus

    @classmethod
    def of(
        cls, device: Device, *, now: datetime, offline_after_seconds: int
    ) -> "DeviceSummaryView":
        return cls(
            id=device.id,
            name=device.name,
            user_id=device.user_id,
            status=device.display_status(now, offline_after_seconds=offline_after_seconds),
        )
