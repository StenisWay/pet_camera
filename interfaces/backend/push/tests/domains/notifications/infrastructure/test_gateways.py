"""推播管道 adapter:只驗證「推播服務的回應怎麼對應成 DeliveryResult」與請求形狀。
不對外連線——FCM 用 httpx.MockTransport,Web Push 注入 sender。"""

import json
import uuid

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings
from app.domains.notifications.application.ports import Channel, DeliveryResult, Recipient
from app.domains.notifications.domain.model import DeepLinkTarget, Notification
from app.domains.notifications.infrastructure.gateways import (
    FcmGateway,
    RoutingPushGateway,
    UnconfiguredGateway,
    WebPushGateway,
    build_push_gateway,
)
from tests.domains.notifications.builders import DEVICE_ID, EVENT_ID

NOTIFICATION = Notification(
    title="客廳 偵測到活動",
    body="高信心",
    target=DeepLinkTarget(device_id=DEVICE_ID, event_id=EVENT_ID),
    image_url="https://r2.example.test/t.jpg",
)
PHONE = Recipient(id=uuid.uuid4(), channel=Channel.APP, token="fcm-token-1")
SUBSCRIPTION = {"endpoint": "https://push.example.test/abc", "keys": {"p256dh": "k", "auth": "a"}}
BROWSER = Recipient(id=uuid.uuid4(), channel=Channel.WEB, token=json.dumps(SUBSCRIPTION))


@pytest.fixture(scope="module")
def service_account() -> dict:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return {
        "client_email": "push@proj.iam.gserviceaccount.com",
        "private_key": pem,
        "token_uri": "https://oauth2.example.test/token",
    }


def _fcm(service_account, send_handler, log=None) -> FcmGateway:
    log = log if log is not None else []

    def handler(request: httpx.Request) -> httpx.Response:
        log.append(request)
        if request.url.host == "oauth2.example.test":
            return httpx.Response(200, json={"access_token": "at-1", "expires_in": 3600})
        return send_handler(request)

    settings = Settings(fcm_project_id="proj", fcm_credentials_json=json.dumps(service_account))
    return FcmGateway(settings, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_fcm_sends_title_body_image_and_link(service_account):
    log: list[httpx.Request] = []
    gateway = _fcm(service_account, lambda _: httpx.Response(200, json={"name": "m/1"}), log)

    assert await gateway.send(PHONE, NOTIFICATION) is DeliveryResult.DELIVERED

    token_request, send_request = log
    assertion = dict(httpx.QueryParams(token_request.content.decode()))["assertion"]
    claims = jwt.decode(assertion, options={"verify_signature": False})
    assert claims["iss"] == service_account["client_email"]
    assert claims["scope"] == "https://www.googleapis.com/auth/firebase.messaging"
    assert send_request.url == "https://fcm.googleapis.com/v1/projects/proj/messages:send"
    assert send_request.headers["Authorization"] == "Bearer at-1"
    message = json.loads(send_request.content)["message"]
    assert message["token"] == "fcm-token-1"
    assert message["notification"] == {
        "title": "客廳 偵測到活動",
        "body": "高信心",
        "image": "https://r2.example.test/t.jpg",
    }
    assert message["data"]["link"] == f"petcamera://devices/{DEVICE_ID}?event_id={EVENT_ID}"
    assert message["data"]["device_id"] == str(DEVICE_ID)
    assert message["data"]["event_id"] == str(EVENT_ID)
    # iOS 經 FCM 轉送 APNs:附圖需要 mutable-content 讓 Notification Service Extension 下載
    assert message["apns"]["payload"]["aps"]["mutable-content"] == 1


async def test_fcm_reuses_the_access_token_until_it_expires(service_account):
    log: list[httpx.Request] = []
    gateway = _fcm(service_account, lambda _: httpx.Response(200, json={}), log)

    await gateway.send(PHONE, NOTIFICATION)
    await gateway.send(PHONE, NOTIFICATION)

    assert [r.url.host for r in log].count("oauth2.example.test") == 1


async def test_fcm_unregistered_token_is_gone(service_account):
    """第 2.5 節:FCM NotRegistered / Unregistered → 刪除該筆(PUSH_003)。"""
    body = {"error": {"status": "NOT_FOUND", "details": [{"errorCode": "UNREGISTERED"}]}}
    gateway = _fcm(service_account, lambda _: httpx.Response(404, json=body))

    assert await gateway.send(PHONE, NOTIFICATION) is DeliveryResult.ENDPOINT_GONE


@pytest.mark.parametrize(
    ("status", "error_code"),
    [(400, "INVALID_ARGUMENT"), (429, "QUOTA_EXCEEDED"), (503, "UNAVAILABLE"), (500, "INTERNAL")],
)
async def test_fcm_other_errors_keep_the_token(service_account, status, error_code):
    """配額、暫時故障、payload 錯誤都不代表端點失效,刪掉會讓使用者從此收不到通知。"""
    body = {"error": {"details": [{"errorCode": error_code}]}}
    gateway = _fcm(service_account, lambda _: httpx.Response(status, json=body))

    assert await gateway.send(PHONE, NOTIFICATION) is DeliveryResult.FAILED


def _web_push(status: int | None = 201, calls: list | None = None) -> WebPushGateway:
    calls = calls if calls is not None else []

    def sender(**kwargs) -> int:
        calls.append(kwargs)
        return status

    settings = Settings(
        web_push_vapid_private_key="vapid-private",
        web_base_url="https://pc.test",
        web_push_vapid_subject="mailto:ops@pc.test",
    )
    return WebPushGateway(settings, sender=sender)


async def test_web_push_sends_an_encrypted_payload_to_the_subscription():
    calls: list[dict] = []

    assert await _web_push(201, calls).send(BROWSER, NOTIFICATION) is DeliveryResult.DELIVERED

    (call,) = calls
    assert call["subscription_info"] == SUBSCRIPTION
    assert call["vapid_private_key"] == "vapid-private"
    assert call["vapid_claims"] == {"sub": "mailto:ops@pc.test"}
    payload = json.loads(call["data"])
    assert payload["title"] == "客廳 偵測到活動"
    assert payload["image"] == "https://r2.example.test/t.jpg"
    assert payload["link"] == f"https://pc.test/dashboard/devices/{DEVICE_ID}?event_id={EVENT_ID}"


@pytest.mark.parametrize(("status", "expected"), [(404, "endpoint_gone"), (410, "endpoint_gone")])
async def test_web_push_expired_subscription_is_gone(status, expected):
    """第 2.5 節:Web Push 404 / 410 → 刪除該筆。"""
    assert (await _web_push(status).send(BROWSER, NOTIFICATION)).value == expected


@pytest.mark.parametrize("status", [400, 413, 429, 500])
async def test_web_push_other_errors_keep_the_subscription(status):
    assert await _web_push(status).send(BROWSER, NOTIFICATION) is DeliveryResult.FAILED


async def test_malformed_subscription_can_never_be_delivered_and_is_gone():
    broken = Recipient(id=uuid.uuid4(), channel=Channel.WEB, token="not json")

    assert await _web_push().send(broken, NOTIFICATION) is DeliveryResult.ENDPOINT_GONE


async def test_routing_picks_the_gateway_by_channel():
    class Recording(UnconfiguredGateway):
        def __init__(self) -> None:
            super().__init__("test")
            self.seen: list[Recipient] = []

        async def send(self, recipient, notification):
            self.seen.append(recipient)
            return DeliveryResult.DELIVERED

    app, web = Recording(), Recording()
    router = RoutingPushGateway({Channel.APP: app, Channel.WEB: web})

    await router.send(PHONE, NOTIFICATION)
    await router.send(BROWSER, NOTIFICATION)

    assert app.seen == [PHONE]
    assert web.seen == [BROWSER]


async def test_missing_credentials_fail_without_deleting_endpoints(caplog):
    """憑證還沒備妥時不可把端點當成失效——那會把所有使用者的登記刪光。"""
    gateway = build_push_gateway(Settings())

    with caplog.at_level("WARNING"):
        assert await gateway.send(PHONE, NOTIFICATION) is DeliveryResult.FAILED
        assert await gateway.send(BROWSER, NOTIFICATION) is DeliveryResult.FAILED
    assert "not configured" in caplog.text
