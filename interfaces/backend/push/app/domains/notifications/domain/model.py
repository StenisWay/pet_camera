"""推播的業務規則(09_spec_推播通知.md 第 2.2、2.3 節)。純 Python,不依賴框架。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domains.notifications.domain.exceptions import InvalidConfidenceScore

# 審查 #7。偵測門檻本身是 0.6(07_spec 第 2.1 節),所以只會出現這兩種描述
HIGH_CONFIDENCE_THRESHOLD = 0.8
HIGH_CONFIDENCE = "高信心"
NORMAL_CONFIDENCE = "一般"
DIGEST_BODY = "偵測到多次活動"


class Occurrence(StrEnum):
    """事件在同一裝置 5 分鐘計數窗內的位置(審查 #3)。"""

    FIRST = "first"  # 立即推播
    SECOND = "second"  # 立即送一則合併通知
    LATER = "later"  # 靜默

    @classmethod
    def from_window_count(cls, count: int | None) -> Occurrence:
        """count 是計數窗 INCR 後的值;None 表示計數窗無法存取。

        計數窗無法存取時視為未開始、直接推播——寧可短暫多推播,不可漏推
        (13_ADR_微服務與三節點部署.md 第 4 節)。
        """
        if count is None or count <= 1:
            return cls.FIRST
        if count == 2:
            return cls.SECOND
        return cls.LATER


@dataclass(frozen=True)
class DeepLinkTarget:
    """點擊通知後要開的畫面。event_id 為 None 時導向該裝置的攝影機畫面(審查 #14)。

    這裡只決定「去哪裡」,各平台的網址長相(App scheme / Web 路由)由發送 adapter 決定。
    """

    device_id: uuid.UUID
    event_id: uuid.UUID | None


@dataclass(frozen=True)
class Notification:
    title: str
    body: str
    target: DeepLinkTarget
    image_url: str | None


@dataclass(frozen=True)
class ReadyEvent:
    """Event 服務通知的「事件已 ready」(POST /internal/notifications/event-ready)。"""

    event_id: uuid.UUID
    device_id: uuid.UUID
    confidence_score: float
    thumbnail_object_key: str | None
    started_at: datetime

    def __post_init__(self) -> None:
        if not 0 <= self.confidence_score <= 1:
            raise InvalidConfidenceScore()

    @property
    def confidence_description(self) -> str:
        if self.confidence_score >= HIGH_CONFIDENCE_THRESHOLD:
            return HIGH_CONFIDENCE
        return NORMAL_CONFIDENCE

    @property
    def signable_thumbnail_key(self) -> str | None:
        """只有這台裝置自己的縮圖才可以簽出 presigned URL。

        key 由內部呼叫端提供;不設限的話,一個被攻破的呼叫端就能讓本服務替任意 R2
        物件(例如別人的相簿)簽出公開連結。key 形狀見 01_資料模型與儲存規格.md 第 3.1 節。
        """
        key = self.thumbnail_object_key
        if not key or not key.startswith(f"thumbnails/{self.device_id}/"):
            return None
        if ".." in key.split("/"):
            return None
        return key

    def notification_for(
        self, occurrence: Occurrence, device_name: str, image_url: str | None
    ) -> Notification | None:
        """依計數窗位置組出通知;靜默時回傳 None。"""
        title = f"{device_name} 偵測到活動"
        if occurrence is Occurrence.FIRST:
            return Notification(
                title=title,
                body=self.confidence_description,
                target=DeepLinkTarget(device_id=self.device_id, event_id=self.event_id),
                image_url=image_url,
            )
        if occurrence is Occurrence.SECOND:
            # 合併通知不指向單一事件,也就沒有「該事件的縮圖」可附
            return Notification(
                title=title,
                body=DIGEST_BODY,
                target=DeepLinkTarget(device_id=self.device_id, event_id=None),
                image_url=None,
            )
        return None
