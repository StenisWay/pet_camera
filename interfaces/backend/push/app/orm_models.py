"""匯入所有 ORM model,確保資料表都註冊到 Base.metadata(給 Alembic 比對與整合測試建表)。"""

from app.domains.push_tokens.infrastructure.orm import PushTokenRow

__all__ = ["PushTokenRow"]
