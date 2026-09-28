"""Row ↔ Entity 的轉換。

實體不繼承 Base:實體描述業務,資料列描述儲存。分開的代價就是這個檔案,
價值是資料表可以依 postgres-db-master 的規範自由演進(加稽核欄位、改索引、
換主鍵型別)而不動到業務模型。
"""

from app.domains.devices.domain.entities import Device, DeviceStatus
from app.domains.devices.domain.pairing_code import PairingCode
from app.domains.devices.infrastructure.orm import DeviceRow


def to_entity(row: DeviceRow) -> Device:
    pairing_code = None
    if row.pairing_code is not None and row.pairing_code_expires_at is not None:
        pairing_code = PairingCode(
            code=row.pairing_code, expires_at=row.pairing_code_expires_at
        )

    return Device(
        id=row.id,
        hardware_id=row.hardware_id,
        name=row.name,
        secret_hash=row.device_secret_hash,
        status=DeviceStatus(row.status),
        created_at=row.created_at,
        user_id=row.user_id,
        pairing_code=pairing_code,
        last_seen_at=row.last_seen_at,
    )


def to_new_row(device: Device) -> DeviceRow:
    row = DeviceRow(
        id=device.id,
        hardware_id=device.hardware_id,
        name=device.name,
        device_secret_hash=device.secret_hash,
        status=device.status.value,
        user_id=device.user_id,
        created_at=device.created_at,
    )
    apply_to_row(device, row)
    return row


def apply_to_row(device: Device, row: DeviceRow) -> None:
    """只同步可變欄位。id、hardware_id、created_at、secret_hash 建立後不再改變。"""
    row.name = device.name
    row.status = device.status.value
    row.user_id = device.user_id
    row.last_seen_at = device.last_seen_at
    row.pairing_code = device.pairing_code.code if device.pairing_code else None
    row.pairing_code_expires_at = (
        device.pairing_code.expires_at if device.pairing_code else None
    )
