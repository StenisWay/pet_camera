"""HTTP 的輸入驗證與輸出序列化。Pydantic 只出現在這一層。

Pydantic 的驗證是「快速失敗、給使用者友善的錯誤」;業務規則的權威仍在 domain
(例如名稱長度,實體自己也會驗)。兩處都驗不是重複,是不同責任:
這裡擋的是格式,實體擋的是規則。
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domains.devices.domain.entities import DeviceStatus


class RegisterDeviceIn(BaseModel):
    """鏡頭註冊。hardware_id 由鏡頭端持久化,重開機時帶同一個值(審查 #3)。"""

    model_config = ConfigDict(extra="forbid")

    hardware_id: str = Field(min_length=1, max_length=128)


class RegisterDeviceOut(BaseModel):
    device_id: uuid.UUID
    status: DeviceStatus
    # 明碼只在這裡出現一次,鏡頭必須自行保存;資料庫只有雜湊(審查 #2)
    device_secret: str | None
    pairing_code: str | None
    # 審查 #15:給鏡頭知道何時該重新取碼
    pairing_code_expires_at: datetime | None


class PairDeviceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pairing_code: str = Field(min_length=1, max_length=32)


class RenameDeviceIn(BaseModel):
    """審查 #12:只接受 name。

    extra="forbid" 擋下 mass assignment——規格書沒有限定 PATCH 可改哪些欄位,
    不擋的話使用者可以在 body 夾帶 status、user_id、pairing_code。
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=30)


class DeviceOut(BaseModel):
    """對使用者公開的裝置。沒有 pairing_code、secret_hash、user_id。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: DeviceStatus
    last_seen_at: datetime | None
    created_at: datetime


class DeviceSummaryOut(BaseModel):
    """GET /internal/devices/{device_id},對應服務契約的 DeviceSummary。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    user_id: uuid.UUID | None
    status: DeviceStatus


class RemovedDevicesOut(BaseModel):
    removed: int
