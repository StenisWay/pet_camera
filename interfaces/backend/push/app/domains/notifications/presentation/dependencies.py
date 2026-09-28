"""notifications 的組裝點。

每個 port 的正式 adapter 在 lifespan 時掛上 app.state(見 app/main.py),這裡只負責取出——
測試以 dependency_overrides 換成 fake,不需要 Device 服務、Redis、R2 或 FCM。
"""

from typing import Annotated

from fastapi import Depends, Request

from app.core.dependencies import SettingsDep
from app.domains.notifications.application.ports import (
    DeviceDirectory,
    NotificationWindow,
    PushGateway,
    RecipientDirectory,
    ThumbnailLinks,
)
from app.domains.notifications.application.use_cases.notify_event_ready import NotifyEventReady


def get_device_directory(request: Request) -> DeviceDirectory:
    return request.app.state.device_directory


def get_notification_window(request: Request) -> NotificationWindow:
    return request.app.state.notification_window


def get_recipient_directory(request: Request) -> RecipientDirectory:
    return request.app.state.recipient_directory


def get_thumbnail_links(request: Request) -> ThumbnailLinks:
    return request.app.state.thumbnail_links


def get_push_gateway(request: Request) -> PushGateway:
    return request.app.state.push_gateway


def get_notify_event_ready(
    devices: Annotated[DeviceDirectory, Depends(get_device_directory)],
    window: Annotated[NotificationWindow, Depends(get_notification_window)],
    recipients: Annotated[RecipientDirectory, Depends(get_recipient_directory)],
    thumbnails: Annotated[ThumbnailLinks, Depends(get_thumbnail_links)],
    gateway: Annotated[PushGateway, Depends(get_push_gateway)],
    settings: SettingsDep,
) -> NotifyEventReady:
    return NotifyEventReady(
        devices=devices,
        window=window,
        recipients=recipients,
        thumbnails=thumbnails,
        gateway=gateway,
        retry_delays=settings.lookup_retry_delays_seconds,
    )


NotifyEventReadyDep = Annotated[NotifyEventReady, Depends(get_notify_event_ready)]
