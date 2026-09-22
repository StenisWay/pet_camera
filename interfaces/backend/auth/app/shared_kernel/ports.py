"""跨領域共用的 port 介面。正式實作在 app/core/system.py,測試替身在 tests。"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime:
        """回傳帶時區(UTC)的目前時間。"""


class IdGenerator(ABC):
    @abstractmethod
    def new_id(self) -> uuid.UUID:
        """產生新的實體 ID(正式環境為 UUIDv7)。"""


class OpaqueTokenFactory(ABC):
    """不透明憑證(密碼重設 token、refresh token)的產生與指紋計算。

    兩個領域都要:明碼只回給使用者一次,資料庫只存指紋,因此查詢一律以指紋進行。
    「不透明」是相對於 JWT——這種 token 本身不帶資訊,必須查資料庫才知道它是誰的。
    """

    @abstractmethod
    def generate(self) -> str:
        """產生密碼學亂數明碼(至少 256 bits 的熵)。"""

    @abstractmethod
    def fingerprint(self, secret: str) -> str:
        """回傳可用於查詢的確定性雜湊;同一個明碼每次結果相同。"""
