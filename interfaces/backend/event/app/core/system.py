"""shared_kernel.ports 的正式實作。"""

import uuid
from datetime import UTC, datetime
from functools import lru_cache

from uuid6 import uuid7

from app.shared_kernel.ports import Clock, IdGenerator


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)


class Uuid7Generator(IdGenerator):
    def new_id(self) -> uuid.UUID:
        # 01_資料模型與儲存規格.md 第 2.0 節:id 會出現在 R2 key 與 API 路徑上,
        # 用 UUIDv7 取得時間排序與 B-tree 友善的特性
        return uuid.UUID(str(uuid7()))


@lru_cache
def get_clock() -> Clock:
    """FastAPI 的 provider。測試以 dependency_overrides 換成 FixedClock——
    「這筆事件過期了沒」的斷言不能建立在真實時鐘上。"""
    return SystemClock()


@lru_cache
def get_id_generator() -> IdGenerator:
    return Uuid7Generator()
