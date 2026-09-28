"""notifications 的測試替身:有真實行為的 fake,不是 mock。"""

import uuid

from app.domains.notifications.application.ports import (
    DeliveryResult,
    DeviceDirectory,
    DeviceInfo,
    NotificationWindow,
    PushGateway,
    Recipient,
    RecipientDirectory,
    ThumbnailLinks,
)
from app.domains.notifications.domain.model import Notification


class FakeDeviceDirectory(DeviceDirectory):
    def __init__(self) -> None:
        self.devices: dict[uuid.UUID, DeviceInfo] = {}
        self.failures_before_success = 0
        self.calls = 0

    def given(self, device: DeviceInfo) -> DeviceInfo:
        self.devices[device.id] = device
        return device

    async def find(self, device_id: uuid.UUID) -> DeviceInfo | None:
        self.calls += 1
        if self.failures_before_success > 0:
            self.failures_before_success -= 1
            raise ConnectionError("device service unreachable")
        return self.devices.get(device_id)


class InMemoryNotificationWindow(NotificationWindow):
    def __init__(self) -> None:
        self.counts: dict[uuid.UUID, int] = {}
        self.available = True

    async def register(self, device_id: uuid.UUID) -> int:
        if not self.available:
            raise ConnectionError("redis unreachable")
        self.counts[device_id] = self.counts.get(device_id, 0) + 1
        return self.counts[device_id]

    def expire(self, device_id: uuid.UUID) -> None:
        """模擬 5 分鐘 TTL 到期。"""
        self.counts.pop(device_id, None)


class FakeRecipientDirectory(RecipientDirectory):
    def __init__(self) -> None:
        self.by_user: dict[uuid.UUID, list[Recipient]] = {}
        self.removed: list[uuid.UUID] = []
        self.failures_before_success = 0
        self.fail_remove = False

    def given(self, user_id: uuid.UUID, *recipients: Recipient) -> None:
        self.by_user.setdefault(user_id, []).extend(recipients)

    async def list_for_user(self, user_id: uuid.UUID) -> list[Recipient]:
        if self.failures_before_success > 0:
            self.failures_before_success -= 1
            raise ConnectionError("postgres unreachable")
        return list(self.by_user.get(user_id, []))

    async def remove(self, recipient_id: uuid.UUID) -> None:
        if self.fail_remove:
            raise ConnectionError("postgres unreachable")
        self.removed.append(recipient_id)
        for recipients in self.by_user.values():
            recipients[:] = [r for r in recipients if r.id != recipient_id]


class FakeThumbnailLinks(ThumbnailLinks):
    def __init__(self) -> None:
        self.signed: list[str] = []
        self.available = True

    async def presign(self, object_key: str) -> str:
        if not self.available:
            raise ConnectionError("r2 unreachable")
        self.signed.append(object_key)
        return f"https://r2.example.test/{object_key}?signed=30m"


class RecordingPushGateway(PushGateway):
    def __init__(self) -> None:
        self.sent: list[tuple[Recipient, Notification]] = []
        self.results: dict[uuid.UUID, DeliveryResult] = {}
        self.raising: set[uuid.UUID] = set()

    async def send(self, recipient: Recipient, notification: Notification) -> DeliveryResult:
        if recipient.id in self.raising:
            raise TimeoutError("push provider timed out")
        result = self.results.get(recipient.id, DeliveryResult.DELIVERED)
        if result is DeliveryResult.DELIVERED:
            self.sent.append((recipient, notification))
        return result


async def no_sleep(_: float) -> None:
    return None
