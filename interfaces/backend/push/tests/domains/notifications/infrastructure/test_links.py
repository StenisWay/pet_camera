import uuid

from app.core.config import Settings
from app.domains.notifications.application.ports import Channel
from app.domains.notifications.domain.model import DeepLinkTarget
from app.domains.notifications.infrastructure.links import deep_link
from tests.domains.notifications.builders import DEVICE_ID, EVENT_ID

SETTINGS = Settings(deep_link_base="petcamera://devices", web_base_url="https://pc.test/")


def test_app_link_opens_the_camera_screen_at_the_event():
    target = DeepLinkTarget(device_id=DEVICE_ID, event_id=EVENT_ID)

    assert deep_link(Channel.APP, target, SETTINGS) == (
        f"petcamera://devices/{DEVICE_ID}?event_id={EVENT_ID}"
    )


def test_web_link_uses_the_dashboard_route():
    """screens/web/02:推播 deep link 導向 /dashboard/devices/{id}。"""
    target = DeepLinkTarget(device_id=DEVICE_ID, event_id=EVENT_ID)

    assert deep_link(Channel.WEB, target, SETTINGS) == (
        f"https://pc.test/dashboard/devices/{DEVICE_ID}?event_id={EVENT_ID}"
    )


def test_digest_link_has_no_event():
    """審查 #14:合併通知導向該裝置的攝影機畫面。"""
    target = DeepLinkTarget(device_id=DEVICE_ID, event_id=None)

    assert deep_link(Channel.APP, target, SETTINGS) == f"petcamera://devices/{DEVICE_ID}"
    assert uuid.UUID(deep_link(Channel.WEB, target, SETTINGS).rsplit("/", 1)[1]) == DEVICE_ID
