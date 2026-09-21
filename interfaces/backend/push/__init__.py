"""Push 服務——涵蓋 F4(推播通知)。擁有 push_tokens 表。
注意:這是使用者「用戶端裝置」(手機/瀏覽器)的推播接收端點,
與 Device 服務的攝影機硬體是不同概念,不可混用。

規格:rule_doc/功能需求/09_spec_推播通知.md(第 8 節為 2026-09-20 的規格審查決議,
以下註解中的「審查 #N」對應該表)。

**本檔是對外契約**:給其他服務與規格書讀的。實作採 Clean Architecture,每個領域分為
domain / application / infrastructure / presentation 四層:

    app/domains/push_tokens/     推播端點登記(09_spec 第 2.4、2.5 節)
    app/domains/notifications/   事件 ready 後的推播與防洗版(第 2.1–2.3 節)

這裡的型別與介面對應實作的 domain 層與端點;tests/test_contract.py 驗證兩者不會走樣。

刪除帳號**沒有**本服務的端點:push_tokens 的外鍵 ON DELETE CASCADE 會在 Auth 刪除
users 時一併帶走(09_spec 第 3 節,審查 #8 的修訂決議)。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Optional
from uuid import UUID

# /internal/* 只走 VCN 私有網路、不經 Load Balancer,以 X-Internal-Api-Key 標頭把關
ENDPOINTS = [
    # (method, path)                                    呼叫者
    ("PUT", "/push-tokens"),  # App/Web;回 200 {id, platform, created_at},不含 token(審查 #10)
    ("GET", "/push-tokens"),  # App/Web;回 {items: [{id, platform, created_at}]}(審查 #11)
    ("DELETE", "/push-tokens/{push_token_id}"),  # App/Web;非本人與不存在一律 404(審查 #5)
    ("POST", "/internal/notifications/event-ready"),  # Event worker;回 202(審查 #1)
]


class ClientPlatform(StrEnum):
    APP = "app"
    WEB = "web"


@dataclass
class PushToken:
    id: UUID
    user_id: UUID
    platform: ClientPlatform
    token: str  # FCM registration token(Android/iOS),或 Web Push subscription(JSON 字串)
    created_at: datetime


@dataclass
class EventReadyNotification:
    """POST /internal/notifications/event-ready 的 body(審查 #1)。

    Event worker 把事件標記為 ready 後呼叫(07_spec 第 2.3 節第 6 步),Push 服務回 202
    並在背景完成查詢與發送,worker 不等待發送結果。

    不夾帶裝置名稱與擁有者:那是 Device 服務的資料,由 Push 以 device_id 向
    GET /internal/devices/{device_id} 取即時值(審查 #2)。
    thumbnail_object_key 必須位於 thumbnails/{device_id}/ 底下,否則通知不附圖。
    confidence_score 必須介於 0 與 1 之間,否則回 400 VAL_001。
    """

    event_id: UUID
    device_id: UUID
    confidence_score: float
    thumbnail_object_key: Optional[str]
    started_at: datetime


class PushTokenRepository(ABC):
    @abstractmethod
    async def get(self, push_token_id: UUID) -> Optional[PushToken]:
        """刪除前驗證擁有者用(審查 #5);不存在時回傳 None。"""

    @abstractmethod
    async def find_by_endpoint(self, platform: ClientPlatform, token: str) -> Optional[PushToken]:
        """以唯一鍵 (platform, token) 找既有登記,不含 user_id(審查 #4)。"""

    @abstractmethod
    async def list_by_user(self, user_id: UUID) -> list[PushToken]:
        """發送推播時取出收件端點;也供 GET /push-tokens(審查 #11)。"""

    @abstractmethod
    async def save(self, push_token: PushToken) -> PushToken:
        """新增或更新。同一 (platform, token) 已存在時改綁到新的 user_id、id 不變(審查 #4)。"""

    @abstractmethod
    async def delete(self, push_token_id: UUID) -> None:
        """解除登記(審查 #5),或推播服務回報端點失效時(PUSH_003,審查 #9)。冪等。"""
