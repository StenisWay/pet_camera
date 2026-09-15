"""Stream 訊令服務——涵蓋 F1(即時串流)。

不擁有任何 Postgres 資料表。Session 狀態是短效的(直播期間才存在,結束即可捨棄),
建議用 Redis 或記憶體內儲存(附 TTL),不需要 Postgres 的持久性保證。
此處仍定義 Repository 介面的形狀,實作可以是 Redis-backed,只是不叫「資料表」。

需要查詢裝置線上狀態(見 STREAM_001)時,呼叫 Device 服務的 API,
不直接讀取 Device 服務的資料——這是跨服務邊界,見
rule_doc/功能需求/13_ADR_微服務與雙節點部署.md 第 4 節 CAP 判斷。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol
from uuid import UUID

from pydantic import BaseModel


class TurnCredentials(BaseModel):
    urls: list[str]
    username: str
    credential: str


class StreamSession(BaseModel):
    session_id: UUID
    device_id: UUID
    turn_credentials: TurnCredentials
    created_at: datetime


class StreamSessionRepository(Protocol):
    """建議以 Redis 實作,key 可設定與 session 效期相同的 TTL。"""

    async def get_by_id(self, session_id: UUID) -> Optional[StreamSession]: ...

    async def create(self, device_id: UUID, turn_credentials: TurnCredentials) -> StreamSession: ...

    async def delete(self, session_id: UUID) -> None:
        """使用者離開直播頁,或 TTL 到期時清除。"""
        ...
