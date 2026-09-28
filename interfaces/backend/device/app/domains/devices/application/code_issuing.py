"""發出一組不與現有配對碼碰撞的新碼。

register 與 unpair 都要發碼,所以抽在這裡共用。

為什麼需要重試:01_資料模型 第 2.2 節在 pairing_code 上有部分唯一索引
(`where pairing_code is not null`),碰撞會讓寫入直接違反約束。8 碼 Crockford Base32
的碰撞機率極低,但「極低」不等於「不會」,撞到時回 500 是說不過去的。
"""

from datetime import datetime

from app.domains.devices.application.ports import PairingCodeFactory
from app.domains.devices.domain.pairing_code import PairingCode
from app.domains.devices.domain.repositories import DeviceRepository
from app.shared_kernel.errors import ServiceUnavailable


async def issue_unique_code(
    devices: DeviceRepository,
    codes: PairingCodeFactory,
    *,
    now: datetime,
    max_attempts: int,
) -> PairingCode:
    """產生新碼並確認目前沒有別台裝置在用。

    這裡的檢查是「先問一次」,不是最終保證——真正的把關是資料庫的部分唯一索引,
    兩個請求同時產生同一組碼時仍會有一方寫入失敗。這一層只是讓那種情況更罕見。
    """
    for _ in range(max_attempts):
        candidate = codes.new_code(now)
        if await devices.get_by_pairing_code(candidate.code) is None:
            return candidate
    raise ServiceUnavailable("目前無法產生配對碼,請稍後再試")
