"""application 層對外界提出的合約。

這一層描述「系統做什麼」,不知道 FastAPI、SQLAlchemy、httpx 的存在。所有外部依賴
都在這裡宣告成 ABC,由 infrastructure 實作、presentation 在組裝點注入,
依賴箭頭因此永遠指向內層。
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Self

from app.domains.devices.domain.pairing_code import PairingCode
from app.domains.devices.domain.repositories import DeviceRepository


class DevicesUnitOfWork(ABC):
    """交易邊界。

    由 use case 以 `async with uow:` 決定範圍,且**必須明確 commit**——
    未 commit 就離開一律回滾,忘記 commit 會在測試中立刻被抓到,
    而不是默默寫入一半。
    """

    devices: DeviceRepository

    @abstractmethod
    async def __aenter__(self) -> Self: ...

    @abstractmethod
    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        """未 commit 的變更一律回滾。"""

    @abstractmethod
    async def commit(self) -> None: ...


class PairingCodeFactory(ABC):
    @abstractmethod
    def new_code(self, now: datetime) -> PairingCode:
        """產生一組新的配對碼與到期時間(03_spec 第 2.1 節:有效期 10 分鐘)。

        每次呼叫都必須回傳密碼學等級亂數產生的新碼——配對碼是「把別人的鏡頭綁到
        我帳號」的唯一憑證,可預測的碼等同於沒有防護(審查 #4)。
        """


class DeviceSecrets(ABC):
    """鏡頭端憑證(規格審查 #2)。

    規格書原本沒有定義鏡頭如何驗證身分,等於任何人知道 device_id 就能偽造心跳,
    讓一台實際已斷線的鏡頭永遠顯示在線。register 時簽發一組長效 secret,
    之後 heartbeat 都要帶上它。
    """

    @abstractmethod
    def issue(self) -> tuple[str, str]:
        """產生 (明碼, 雜湊)。明碼只在 register 的回應裡出現這一次,不落盤。"""

    @abstractmethod
    def verify(self, plaintext: str, secret_hash: str) -> bool:
        """驗證明碼是否對應該雜湊。比對必須是常數時間,避免計時攻擊。"""


class EventCleanup(ABC):
    """Event 服務的內部端點(規格審查 #7)。

    events 表由 Event 服務擁有(13_ADR 第 1 節),Device 不可直接寫入;
    而 01_資料模型 第 6 節要求移除裝置時一併刪掉該裝置的事件與 R2 影片縮圖。
    注意 events.device_id 雖然是 ON DELETE CASCADE,但移除裝置**不刪** devices 這一列
    (只重置為 pending),cascade 不會觸發,必須顯式呼叫。
    """

    @abstractmethod
    async def delete_device_events(self, device_id: uuid.UUID) -> None:
        """刪除該裝置的所有事件紀錄與對應的 R2 物件。

        必須是冪等的:審查 #9 的 fail-closed 流程在失敗後會讓使用者重試,
        重複呼叫不可以報錯。
        失敗時拋 EventCleanupFailed,呼叫端據此中止整個移除流程。
        """
