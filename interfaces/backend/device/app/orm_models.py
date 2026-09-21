"""匯入所有 ORM model,確保資料表都註冊到 Base.metadata。

Alembic 的 env.py 與測試的 create_all 都依賴這個模組。
Device 服務只擁有 devices 一張表(13_ADR 第 1 節)。
"""

from app.core.database import Base
from app.domains.devices.infrastructure.orm import DeviceRow

__all__ = ["Base", "DeviceRow"]
