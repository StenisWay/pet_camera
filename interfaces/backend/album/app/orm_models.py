"""匯入所有 ORM model,確保資料表都註冊到 Base.metadata。

給未來的 Alembic env.py 與測試用。目前不連真實資料庫,建表/migration 等所有服務的
規格確認後再一次產出(見 README「待辦:建立資料庫」)。
"""

from app.domains.album.infrastructure.orm import MediaItemRow
from app.domains.drive_export.infrastructure.orm import DriveCredentialRow

__all__ = ["DriveCredentialRow", "MediaItemRow"]
