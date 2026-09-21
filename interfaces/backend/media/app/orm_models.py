"""匯入所有 ORM model,確保資料表都註冊到 Base.metadata。

給未來的 Alembic env.py 與整合測試用。目前不連真實資料庫,建表/migration 等所有
服務的規格確認後再一次產出(見 README「待辦:建立資料庫」)。
"""

from app.domains.media.infrastructure.orm import MediaItemRow

__all__ = ["MediaItemRow"]
