"""devices 領域的實體。

純 Python,不依賴 FastAPI / SQLAlchemy / Pydantic。時間與 ID 一律由外部傳入,
實體不自己呼叫 datetime.now() 或產生 UUID,這樣所有業務規則都能被確定性地測試。

對應規格:03_spec_裝置配對.md(F0.2)、04_spec_裝置管理.md(F0.3)、
01_資料模型與儲存規格.md 第 2.2、6 節。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.domains.devices.domain.exceptions import (
    DeviceAlreadyPaired,
    DeviceNotPaired,
    InvalidDeviceName,
    PairingCodeExpired,
    PairingCodeInvalid,
)
from app.domains.devices.domain.pairing_code import PairingCode


class DeviceStatus(StrEnum):
    """裝置狀態。

    規格審查 #6:**只有 PENDING 與 PAIRED 會寫進資料庫**(devices.status 的 CHECK
    約束只允許這兩個值)。OFFLINE 是由 last_seen_at 推導出來的顯示用狀態,
    由 display_status() 產生。

    原因:03_spec 第 2.3 節的「超過 90 秒未回報即視為 offline」如果要落盤,就需要一個
    背景掃描任務去改寫狀態,但 Device 服務在 VM-1/VM-2 各跑一份複本(13_ADR 第 1 節),
    兩份都掃會互相打架,而系統並沒有可用的單例排程器。改成衍生狀態後不需要背景任務,
    而且 Stream 服務(06_spec STREAM_001)與本服務用的是同一條判定規則,
    不會對同一台鏡頭有不同看法。
    """

    PENDING = "pending"
    PAIRED = "paired"
    OFFLINE = "offline"


@dataclass
class Device:
    """一台攝影機硬體。

    注意:這裡的「裝置」是鏡頭硬體,與 push 服務的用戶端 token 是不同概念
    (01_資料模型 第 2.6 節)。

    hardware_id 與 secret_hash 是規格審查 #3、#2 新增的欄位:
    前者讓鏡頭重開機呼叫 register 時能沿用同一列,後者讓鏡頭能證明自己是自己。
    """

    id: uuid.UUID
    hardware_id: str
    name: str
    secret_hash: str
    status: DeviceStatus
    created_at: datetime
    user_id: uuid.UUID | None = None
    pairing_code: PairingCode | None = None
    last_seen_at: datetime | None = None

    # --- 建立 ---------------------------------------------------------------

    @classmethod
    def register(
        cls,
        *,
        id: uuid.UUID,
        hardware_id: str,
        secret_hash: str,
        pairing_code: PairingCode,
        name: str,
        now: datetime,
    ) -> "Device":
        """鏡頭首次註冊(03_spec 第 2.1 節)。

        建立出來一定是「未配對、無擁有者、帶一組有效配對碼」的狀態——
        01_資料模型 第 2.2 節要求 status = 'pending' 與 user_id is null 同時成立。
        name 由呼叫端給預設值(審查 #11),因為命名畫面在配對**之後**才出現。
        """
        return cls(
            id=id,
            hardware_id=hardware_id,
            name=name,
            secret_hash=secret_hash,
            status=DeviceStatus.PENDING,
            created_at=now,
            user_id=None,
            pairing_code=pairing_code,
            last_seen_at=None,
        )

    # --- 配對生命週期 -------------------------------------------------------

    def reissue_pairing_code(self, pairing_code: PairingCode) -> None:
        """重新產生配對碼(審查 #3:鏡頭重開機或配對碼過期時沿用同一列)。"""
        if self.status is not DeviceStatus.PENDING:
            raise DeviceAlreadyPaired()
        self.pairing_code = pairing_code

    def pair(self, *, user_id: uuid.UUID, typed_code: str, now: datetime) -> None:
        """使用者輸入配對碼完成綁定(03_spec 第 2.2 節)。

        先比對碼本身、再看有效期:碼根本不對時回 DEVICE_002,不該透漏
        「這組碼存在但過期了」。已配對的裝置沒有配對碼,一律落到 DEVICE_002(審查 #5)。
        """
        if self.pairing_code is None or not self.pairing_code.equals(typed_code):
            raise PairingCodeInvalid()
        if self.pairing_code.is_expired(now):
            raise PairingCodeExpired()

        self.user_id = user_id
        self.status = DeviceStatus.PAIRED
        self.pairing_code = None

    def unpair(self, pairing_code: PairingCode) -> None:
        """移除裝置(04_spec 第 2.3 節、01_資料模型 第 6 節)。

        devices 這一列不會被刪除,只重置成可被下一個人配對的狀態:清空 user_id、
        狀態回 pending、重新產生配對碼。last_seen_at 一併清空,否則新的擁有者在
        鏡頭還沒回報第一次心跳前,就會看到上一位使用者留下的「在線」狀態。

        呼叫端必須**先**請 Event 服務清掉該裝置的事件與 R2 影片才能呼叫這裡
        (審查 #9 的 fail-closed 順序),否則下一位配對者會看到前一位的寵物影片。
        """
        self.user_id = None
        self.status = DeviceStatus.PENDING
        self.pairing_code = pairing_code
        self.last_seen_at = None

    # --- 使用者操作 ---------------------------------------------------------

    def rename(self, name: str, *, max_length: int) -> None:
        """重新命名(04_spec 第 2.2 節、審查 #11:trim 後 1~max_length 字)。"""
        trimmed = name.strip()
        if not trimmed or len(trimmed) > max_length:
            raise InvalidDeviceName(f"裝置名稱須為 1~{max_length} 個字")
        self.name = trimmed

    # --- 連線狀態 -----------------------------------------------------------

    def record_heartbeat(self, now: datetime) -> None:
        """鏡頭心跳回報(03_spec 第 2.3 節)。未配對的裝置不該有心跳(審查 #14)。"""
        if self.status is not DeviceStatus.PAIRED:
            raise DeviceNotPaired()
        self.last_seen_at = now

    def display_status(self, now: datetime, *, offline_after_seconds: int) -> DeviceStatus:
        """對外顯示的狀態,不改變實體(審查 #6)。

        「超過 N 秒未回報」才算離線,所以剛好等於 N 秒時仍視為在線。
        已配對但從未回報過心跳的裝置直接算離線。
        """
        if self.status is not DeviceStatus.PAIRED:
            return self.status
        if self.last_seen_at is None:
            return DeviceStatus.OFFLINE
        if now - self.last_seen_at > timedelta(seconds=offline_after_seconds):
            return DeviceStatus.OFFLINE
        return DeviceStatus.PAIRED

    # --- 權限 ---------------------------------------------------------------

    def is_owned_by(self, user_id: uuid.UUID) -> bool:
        """審查 #1:PATCH / DELETE / heartbeat 之前都要問這一句。"""
        return self.user_id is not None and self.user_id == user_id
