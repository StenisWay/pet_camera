import pytest

from app.domains.notifications.application.use_cases.notify_event_ready import NotifyEventReady
from tests.domains.notifications.fakes import (
    FakeDeviceDirectory,
    FakeRecipientDirectory,
    FakeThumbnailLinks,
    InMemoryNotificationWindow,
    RecordingPushGateway,
    no_sleep,
)


@pytest.fixture
def devices() -> FakeDeviceDirectory:
    return FakeDeviceDirectory()


@pytest.fixture
def window() -> InMemoryNotificationWindow:
    return InMemoryNotificationWindow()


@pytest.fixture
def recipients() -> FakeRecipientDirectory:
    return FakeRecipientDirectory()


@pytest.fixture
def thumbnails() -> FakeThumbnailLinks:
    return FakeThumbnailLinks()


@pytest.fixture
def gateway() -> RecordingPushGateway:
    return RecordingPushGateway()


@pytest.fixture
def use_case(devices, window, recipients, thumbnails, gateway) -> NotifyEventReady:
    return NotifyEventReady(
        devices=devices,
        window=window,
        recipients=recipients,
        thumbnails=thumbnails,
        gateway=gateway,
        retry_delays=(1, 2),
        sleep=no_sleep,
    )
