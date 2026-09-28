"""值物件:不可變,建立時自我驗證。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


@dataclass(frozen=True)
class TurnCredentials:
    """coturn REST API 認證憑證(06_spec_即時串流.md 第 2.5 節)。

    credential 是 HMAC 簽章,不是密碼;簽發方式屬 infrastructure,本層只描述形狀。
    """

    urls: tuple[str, ...]
    username: str
    credential: str
    expires_at: datetime


@dataclass(frozen=True)
class IceCandidate:
    sdp_mid: str | None
    sdp_m_line_index: int | None
    candidate: str


HEARTBEAT_TIMEOUT = timedelta(seconds=90)


class DeviceStatus(StrEnum):
    """鏡頭狀態。值域與 devices.status 相同(01_資料模型與儲存規格.md 第 2.2 節),
    但這是 Stream 服務讀到的快照,不是它擁有的資料。"""

    PENDING = "pending"
    PAIRED = "paired"
    OFFLINE = "offline"


@dataclass(frozen=True)
class DeviceSnapshot:
    """向 Device 服務查到的鏡頭狀態快照。

    是否可串流由本服務判斷(見 is_online),Device 服務只提供原始資料。
    """

    device_id: uuid.UUID
    owner_id: uuid.UUID | None
    status: DeviceStatus
    last_seen_at: datetime | None

    def is_online(self, now: datetime) -> bool:
        """心跳每 30 秒一次,超過 90 秒未回報即視為離線
        (03_spec_裝置配對.md 第 2.3 節)。status 已標記 offline 時直接採信。
        """
        if self.status is not DeviceStatus.PAIRED:
            return False
        if self.last_seen_at is None:
            return False
        return now - self.last_seen_at < HEARTBEAT_TIMEOUT

    def is_owned_by(self, user_id: uuid.UUID) -> bool:
        return self.owner_id is not None and self.owner_id == user_id
