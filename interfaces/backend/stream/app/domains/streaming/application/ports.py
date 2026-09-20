"""application 層對外界提出的合約。以本領域的語言命名,不是對方介面的複製。

實作在 infrastructure(正式)與 tests/domains/streaming/fakes.py(測試替身)。
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from app.domains.streaming.domain.value_objects import DeviceSnapshot, TurnCredentials


class DeviceDirectory(ABC):
    """向 Device 服務查詢鏡頭狀態。跨服務邊界,不直接讀 devices 表
    (13_ADR_微服務與三節點部署.md 第 1 節)。"""

    @abstractmethod
    async def find(self, device_id: uuid.UUID) -> DeviceSnapshot | None:
        """查不到裝置時回傳 None,不拋例外——要不要當成錯誤由 use case 決定。

        Device 服務不可用時拋 ServiceUnavailable(ADR 第 4 節:Stream 選一致性,
        連線失敗比連到錯誤的裝置狀態安全)。
        """


class TurnCredentialIssuer(ABC):
    """簽發 TURN 短效憑證(06_spec 第 2.5 節)。"""

    @abstractmethod
    async def issue(self, session_id: uuid.UUID, now: datetime) -> TurnCredentials:
        """回傳有效期自 now 起算的憑證。效期必須長於 session TTL,
        否則會出現 session 還在但憑證先過期的狀態。"""


class SignalingEvents(ABC):
    """跨複本的等待與喚醒。

    為什麼需要:VM-1 與 VM-2 各跑一份 Stream 複本,LB 以請求為單位分流
    (ADR 第 1.1 節)。觀看端的 offer 與鏡頭端的 answer 很可能落在不同複本,
    單純在本機 await 一個 asyncio.Event 永遠等不到對方。
    """

    @abstractmethod
    async def wait_for_answer(self, session_id: uuid.UUID, timeout: timedelta) -> bool:
        """等待鏡頭端回覆 answer。收到回 True,逾時回 False(由 use case 轉成 STREAM_005)。"""

    @abstractmethod
    async def announce_answer(self, session_id: uuid.UUID) -> None:
        """通知正在等待這個 session 的 answer 的複本。"""

    @abstractmethod
    async def wait_for_offer(self, device_id: uuid.UUID, timeout: timedelta) -> bool:
        """鏡頭端長輪詢:等待該裝置出現待處理的 offer。逾時回 False(第 3.2 節回 204)。"""

    @abstractmethod
    async def announce_offer(self, device_id: uuid.UUID) -> None:
        """通知正在等待這個裝置的 offer 的複本。"""
