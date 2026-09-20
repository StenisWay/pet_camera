"""use case 的輸入與輸出。不是 HTTP schema,也不是 ORM。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.domains.streaming.domain.value_objects import IceCandidate


@dataclass(frozen=True)
class PendingOffer:
    """鏡頭端長輪詢拿到的待處理 offer(第 3.2 節)。"""

    session_id: uuid.UUID
    sdp: str


@dataclass(frozen=True)
class CandidateBatch:
    """增量輪詢的結果。

    next_since 由後端算,前端只要原樣回傳——把游標的算法留在前端,兩個平台
    (App / Web)就會各自算錯一次。
    """

    candidates: list[IceCandidate]
    next_since: int
