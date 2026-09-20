"""建立測試資料的輔助函式與固定 ID。

時間與 ID 都是固定值,domain 測試因此完全確定(不呼叫 datetime.now / uuid7)。
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

DEVICE = uuid.UUID("00000000-0000-0000-0000-0000000000d1")
OTHER_DEVICE = uuid.UUID("00000000-0000-0000-0000-0000000000d2")
EVENT = uuid.UUID("00000000-0000-0000-0000-0000000000e1")

# 錄影開始的基準時間,所有相對時間都從這裡算起
T0 = datetime(2026, 9, 20, 3, 0, 0, tzinfo=UTC)

HIGH = Decimal("0.90")  # 明顯超過門檻
LOW = Decimal("0.10")  # 明顯低於門檻


def at(seconds: float) -> datetime:
    """T0 之後 N 秒。"""
    return T0 + timedelta(seconds=seconds)
