"""shared_kernel.ports 的正式實作。"""

import uuid
from datetime import UTC, datetime

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
