"""跨領域共用的測試替身:時間與 ID。

時間與亂數一律可注入,否則測試會 flaky——「7 天前的事件是否過期」這種斷言
不能建立在真實時鐘上。
"""

import uuid
from datetime import datetime

from app.shared_kernel.ports import Clock, IdGenerator


class FixedClock(Clock):
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        self._now = now


class SequentialIds(IdGenerator):
    def __init__(self) -> None:
        self._n = 0

    def new_id(self) -> uuid.UUID:
        self._n += 1
        return uuid.UUID(int=self._n)
