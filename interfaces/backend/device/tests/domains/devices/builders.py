"""測試資料 builder 與固定 ID。

只寫出每個測試真正在乎的欄位,其餘給合理預設——測試才讀得出意圖。
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.domains.devices.domain.entities import Device, DeviceStatus
from app.domains.devices.domain.pairing_code import PairingCode

ALICE = uuid.UUID("00000000-0000-0000-0000-00000000a11c")
BOB = uuid.UUID("00000000-0000-0000-0000-0000000000b0")
DEVICE_ID = uuid.UUID("00000000-0000-0000-0000-0000000d0001")

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
HARDWARE_ID = "pi-zero-2w-0001"
SECRET_HASH = "hashed-secret"
VALID_CODE = "ABCD1234"


def a_pairing_code(code: str = VALID_CODE, *, expires_in: timedelta | None = None) -> PairingCode:
    return PairingCode(code=code, expires_at=NOW + (expires_in or timedelta(minutes=10)))


def a_pending_device(
    *,
    id: uuid.UUID = DEVICE_ID,
    hardware_id: str = HARDWARE_ID,
    name: str = "未命名鏡頭",
    pairing_code: PairingCode | None = None,
    created_at: datetime = NOW,
) -> Device:
    return Device(
        id=id,
        hardware_id=hardware_id,
        name=name,
        secret_hash=SECRET_HASH,
        status=DeviceStatus.PENDING,
        created_at=created_at,
        user_id=None,
        pairing_code=pairing_code if pairing_code is not None else a_pairing_code(),
        last_seen_at=None,
    )


def a_paired_device(
    *,
    id: uuid.UUID = DEVICE_ID,
    hardware_id: str = HARDWARE_ID,
    name: str = "客廳",
    user_id: uuid.UUID = ALICE,
    last_seen_at: datetime | None = NOW,
    created_at: datetime = NOW,
) -> Device:
    return Device(
        id=id,
        hardware_id=hardware_id,
        name=name,
        secret_hash=SECRET_HASH,
        status=DeviceStatus.PAIRED,
        created_at=created_at,
        user_id=user_id,
        pairing_code=None,
        last_seen_at=last_seen_at,
    )
