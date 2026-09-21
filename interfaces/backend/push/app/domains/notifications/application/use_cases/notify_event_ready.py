"""事件轉 ready 後推播給裝置擁有者(09_spec_推播通知.md 第 2 節)。

在背景執行(Event worker 拿到 202 就走了,審查 #1),所以這裡**不往外丟例外**:
結果以 DispatchReport 回報並寫 log。降級方式依 13_ADR 第 4 節——發送路徑選可用性:
查詢失敗延後重試,計數窗故障就當作首發,縮圖簽不出來就不附圖。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from app.domains.notifications.application.ports import (
    DeliveryResult,
    DeviceDirectory,
    NotificationWindow,
    PushGateway,
    Recipient,
    RecipientDirectory,
    ThumbnailLinks,
)
from app.domains.notifications.domain.model import Notification, Occurrence, ReadyEvent

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_RETRY_DELAYS: tuple[float, ...] = (1, 3, 5)


class DispatchStatus(StrEnum):
    SENT = "sent"
    DEVICE_UNOWNED = "device_unowned"  # 裝置不存在或已解除配對(審查 #13)
    SILENCED = "silenced"  # 計數窗第 3 個以後的事件(審查 #3)
    NO_RECIPIENTS = "no_recipients"
    GAVE_UP = "gave_up"  # 重試用盡


@dataclass(frozen=True)
class DispatchReport:
    status: DispatchStatus
    delivered: int = 0
    removed_endpoints: int = 0


class _GaveUp(Exception):
    pass


class NotifyEventReady:
    def __init__(
        self,
        *,
        devices: DeviceDirectory,
        window: NotificationWindow,
        recipients: RecipientDirectory,
        thumbnails: ThumbnailLinks,
        gateway: PushGateway,
        retry_delays: Sequence[float] = DEFAULT_RETRY_DELAYS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.devices = devices
        self.window = window
        self.recipients = recipients
        self.thumbnails = thumbnails
        self.gateway = gateway
        self.retry_delays = tuple(retry_delays)
        self.sleep = sleep

    async def execute(self, event: ReadyEvent) -> DispatchReport:
        try:
            return await self._dispatch(event)
        except _GaveUp:
            logger.error("gave up pushing event %s of device %s", event.event_id, event.device_id)
            return DispatchReport(DispatchStatus.GAVE_UP)

    async def _dispatch(self, event: ReadyEvent) -> DispatchReport:
        device = await self._with_retry(lambda: self.devices.find(event.device_id), "device")
        if device is None or device.owner_id is None:
            return DispatchReport(DispatchStatus.DEVICE_UNOWNED)

        occurrence = Occurrence.from_window_count(await self._register_in_window(event))
        if occurrence is Occurrence.LATER:
            return DispatchReport(DispatchStatus.SILENCED)

        owner_id = device.owner_id
        recipients = await self._with_retry(
            lambda: self.recipients.list_for_user(owner_id), "recipients"
        )
        if not recipients:
            return DispatchReport(DispatchStatus.NO_RECIPIENTS)

        image_url = await self._image_url(event) if occurrence is Occurrence.FIRST else None
        notification = event.notification_for(occurrence, device.name, image_url)
        assert notification is not None  # LATER 已在上面處理
        return await self._send_to_all(recipients, notification)

    async def _register_in_window(self, event: ReadyEvent) -> int | None:
        try:
            return await self.window.register(event.device_id)
        except Exception:
            logger.warning("notification window unavailable, pushing %s anyway", event.event_id)
            return None

    async def _image_url(self, event: ReadyEvent) -> str | None:
        key = event.signable_thumbnail_key
        if key is None:
            if event.thumbnail_object_key:
                logger.warning(
                    "refusing to sign thumbnail %r for device %s",
                    event.thumbnail_object_key,
                    event.device_id,
                )
            return None
        try:
            return await self.thumbnails.presign(key)
        except Exception:
            logger.warning("could not sign thumbnail for event %s", event.event_id, exc_info=True)
            return None

    async def _send_to_all(
        self, recipients: list[Recipient], notification: Notification
    ) -> DispatchReport:
        delivered = removed = 0
        for recipient in recipients:
            try:
                result = await self.gateway.send(recipient, notification)
            except Exception:
                logger.warning("push to endpoint %s failed", recipient.id, exc_info=True)
                continue
            if result is DeliveryResult.DELIVERED:
                delivered += 1
            elif result is DeliveryResult.ENDPOINT_GONE:
                # PUSH_003:刪除並停止對它發送(第 2.5 節)
                try:
                    await self.recipients.remove(recipient.id)
                    removed += 1
                except Exception:
                    logger.warning("could not remove gone endpoint %s", recipient.id, exc_info=True)
        return DispatchReport(DispatchStatus.SENT, delivered=delivered, removed_endpoints=removed)

    async def _with_retry(self, call: Callable[[], Awaitable[T]], what: str) -> T:
        for attempt, delay in enumerate((*self.retry_delays, None)):
            try:
                return await call()
            except Exception:
                if delay is None:
                    logger.warning("%s lookup failed, no retries left", what, exc_info=True)
                    raise _GaveUp() from None
                logger.warning("%s lookup failed (attempt %s), retrying", what, attempt + 1)
                await self.sleep(delay)
        raise AssertionError("unreachable")
