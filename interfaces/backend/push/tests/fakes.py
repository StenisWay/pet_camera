"""跨領域共用的測試替身(shared_kernel 與 core 的 port)。"""

import uuid
from datetime import UTC, datetime

from app.core.rate_limit import RateLimitCounter
from app.shared_kernel.ports import Clock, IdGenerator


class InMemoryRateLimitCounter(RateLimitCounter):
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.available = True

    async def hit(self, key: str, *, window_seconds: int) -> int:
        if not self.available:
            raise ConnectionError("redis unreachable")
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]


class FixedClock(Clock):
    def __init__(self, now: datetime = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)) -> None:
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
