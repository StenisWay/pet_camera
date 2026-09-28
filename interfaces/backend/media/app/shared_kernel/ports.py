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
