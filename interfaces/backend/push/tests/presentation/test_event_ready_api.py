"""POST /internal/notifications/event-ready 的 HTTP 契約(09_spec 第 3 節,審查 #1)。"""

import pytest

from app.domains.notifications.application.ports import Channel, DeviceInfo, Recipient
from tests.domains.notifications.builders import DEVICE_ID, EVENT_ID, OWNER, THUMBNAIL_KEY
from tests.presentation.conftest import INTERNAL_KEY

PHONE = Recipient(id=EVENT_ID, channel=Channel.APP, token="fcm-1")
BODY = {
    "event_id": str(EVENT_ID),
    "device_id": str(DEVICE_ID),
    "confidence_score": 0.92,
    "thumbnail_object_key": THUMBNAIL_KEY,
    "started_at": "2026-09-20T03:14:00Z",
}


def _post(client, body=BODY, key=INTERNAL_KEY):
    headers = {"X-Internal-Api-Key": key} if key else {}
    return client.post("/internal/notifications/event-ready", json=body, headers=headers)


async def test_accepts_with_202_and_pushes_in_the_background(client, devices, recipients, gateway):
    devices.given(DeviceInfo(id=DEVICE_ID, name="客廳", owner_id=OWNER))
    recipients.given(OWNER, PHONE)

    response = await _post(client)

    assert response.status_code == 202
    assert [n.title for _, n in gateway.sent] == ["客廳 偵測到活動"]


async def test_background_failure_does_not_turn_into_an_error_response(client, devices):
    """worker 不等待發送結果——推播失敗不應該影響事件本身的處理。"""
    devices.failures_before_success = 99

    response = await _post(client)

    assert response.status_code == 202


@pytest.mark.parametrize("key", [None, "wrong-key"])
async def test_requires_the_internal_api_key(client, gateway, key):
    response = await _post(client, key=key)

    assert response.status_code == 403
    assert gateway.sent == []


@pytest.mark.parametrize(
    "change",
    [
        {"confidence_score": 1.5},
        {"device_id": "not-a-uuid"},
        {"started_at": None},
    ],
)
async def test_malformed_body_returns_val_001(client, change):
    response = await _post(client, body={**BODY, **change})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VAL_001"


async def test_thumbnail_is_optional(client, devices, recipients, gateway):
    devices.given(DeviceInfo(id=DEVICE_ID, name="客廳", owner_id=OWNER))
    recipients.given(OWNER, PHONE)
    body = {k: v for k, v in BODY.items() if k != "thumbnail_object_key"}

    assert (await _post(client, body=body)).status_code == 202
    assert gateway.sent[0][1].image_url is None


async def test_health_does_not_touch_any_backend(client):
    assert (await client.get("/health")).json() == {"status": "ok"}
