"""application 層需要、但由外層實作的介面。

本領域不持有任何資料表:裝置資料屬於 Device 服務,收件端點屬於 push_tokens 領域,
計數窗在 Redis,縮圖在 R2——全部以 port 表達,由 infrastructure 的 adapter 接上。
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from app.domains.notifications.domain.model import Notification


@dataclass(frozen=True)
class DeviceInfo:
    """Device 服務 GET /internal/devices/{device_id} 的回應中本服務需要的部分。"""

    id: uuid.UUID
    name: str
    owner_id: uuid.UUID | None  # None:未配對或已解除配對(審查 #13)


class Channel(StrEnum):
    """收件端點的推播管道。值與 push_tokens.platform 一致(app / web)。"""

    APP = "app"
    WEB = "web"


@dataclass(frozen=True)
class Recipient:
    id: uuid.UUID
    channel: Channel
    token: str


class DeliveryResult(StrEnum):
    DELIVERED = "delivered"
    # 推播服務回報端點已失效(FCM UNREGISTERED、APNs 410、Web Push 404/410),PUSH_003
    ENDPOINT_GONE = "endpoint_gone"
    # 其他失敗(逾時、5xx、配額):端點本身可能沒問題,不刪
    FAILED = "failed"


class DeviceDirectory(ABC):
    @abstractmethod
    async def find(self, device_id: uuid.UUID) -> DeviceInfo | None:
        """取裝置的即時名稱與擁有者(審查 #2);裝置不存在時回傳 None。

        暫時性故障(Device 服務連不到、5xx)丟例外,由呼叫端決定是否重試。
        """


class NotificationWindow(ABC):
    @abstractmethod
    async def register(self, device_id: uuid.UUID) -> int:
        """在該裝置的 5 分鐘計數窗登記一次事件,回傳登記後的次數(第一次為 1)。

        計數窗從第一次登記起算,後續登記不延長它(09_spec 第 2.3 節)。
        """


class RecipientDirectory(ABC):
    @abstractmethod
    async def list_for_user(self, user_id: uuid.UUID) -> list[Recipient]:
        """該使用者名下所有已登記的端點;沒有時回傳空串列。"""

    @abstractmethod
    async def remove(self, recipient_id: uuid.UUID) -> None:
        """刪除已失效的端點(PUSH_003);不存在時不視為錯誤。"""


class ThumbnailLinks(ABC):
    @abstractmethod
    async def presign(self, object_key: str) -> str:
        """產生縮圖的 presigned URL,效期 30 分鐘(審查 #6)。"""


class PushGateway(ABC):
    @abstractmethod
    async def send(self, recipient: Recipient, notification: Notification) -> DeliveryResult:
        """對單一端點發送。端點失效回 ENDPOINT_GONE,其餘失敗回 FAILED 或丟例外。"""
