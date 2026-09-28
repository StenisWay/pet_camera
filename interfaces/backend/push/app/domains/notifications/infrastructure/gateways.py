"""PushGateway 的實作:FCM(App)與 Web Push(Web)。

platform 只有 app / web(01_資料模型第 2.6 節),App 端的 Android 與 iOS 都向 FCM 取
registration token,由 FCM 轉送 APNs——所以 App 只需要 FCM 一條管道,APNs 的差異
(附圖需要 mutable-content)以 FCM message 的 apns 區塊表達。

失效判定(09_spec 第 2.5 節,PUSH_003)刻意保守:只有推播服務明確說「這個端點不存在了」
才回 ENDPOINT_GONE。逾時、配額、5xx、payload 錯誤都回 FAILED,不刪端點——誤刪會讓
使用者從此靜默收不到通知,而且沒有任何錯誤訊息提醒他。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx
import jwt

from app.core.config import Settings
from app.domains.notifications.application.ports import (
    Channel,
    DeliveryResult,
    PushGateway,
    Recipient,
)
from app.domains.notifications.domain.model import Notification
from app.domains.notifications.infrastructure.links import deep_link

logger = logging.getLogger(__name__)

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
# 通知要在事件發生後盡快送達才有意義(驗收:10 秒內);1 小時後才送到的「寵物有動靜」沒有價值
NOTIFICATION_TTL_SECONDS = 3600


def _data(notification: Notification, link: str) -> dict[str, str]:
    data = {"link": link, "device_id": str(notification.target.device_id)}
    if notification.target.event_id is not None:
        data["event_id"] = str(notification.target.event_id)
    return data


class FcmGateway(PushGateway):
    """FCM HTTP v1。以 service account 自行簽 JWT 換 OAuth access token,快取到過期前。"""

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._account = json.loads(settings.fcm_credentials_json)
        self._send_url = FCM_SEND_URL.format(project_id=settings.fcm_project_id)
        self._client = client or httpx.AsyncClient(timeout=settings.push_provider_timeout_seconds)
        self._access_token: tuple[str, float] | None = None
        self._token_lock = asyncio.Lock()

    async def send(self, recipient: Recipient, notification: Notification) -> DeliveryResult:
        response = await self._client.post(
            self._send_url,
            headers={"Authorization": f"Bearer {await self._get_access_token()}"},
            json={"message": self._message(recipient, notification)},
        )
        if response.is_success:
            return DeliveryResult.DELIVERED
        if self._error_code(response) == "UNREGISTERED":
            return DeliveryResult.ENDPOINT_GONE
        logger.warning(
            "FCM rejected push to %s: %s %s",
            recipient.id,
            response.status_code,
            response.text[:500],
        )
        return DeliveryResult.FAILED

    def _message(self, recipient: Recipient, notification: Notification) -> dict[str, Any]:
        link = deep_link(Channel.APP, notification.target, self._settings)
        body: dict[str, Any] = {"title": notification.title, "body": notification.body}
        if notification.image_url:
            body["image"] = notification.image_url
        return {
            "token": recipient.token,
            "notification": body,
            "data": _data(notification, link),
            "android": {"priority": "high", "ttl": f"{NOTIFICATION_TTL_SECONDS}s"},
            "apns": {
                "headers": {"apns-priority": "10"},
                # iOS 要靠 Notification Service Extension 下載附圖,需要 mutable-content
                "payload": {"aps": {"mutable-content": 1}},
                "fcm_options": {"image": notification.image_url} if notification.image_url else {},
            },
        }

    @staticmethod
    def _error_code(response: httpx.Response) -> str | None:
        try:
            details = response.json()["error"].get("details", [])
        except (ValueError, KeyError, AttributeError):
            return None
        for detail in details:
            if code := detail.get("errorCode"):
                return str(code)
        return None

    def _cached_access_token(self) -> str | None:
        if self._access_token and self._access_token[1] > time.time():
            return self._access_token[0]
        return None

    async def _get_access_token(self) -> str:
        if token := self._cached_access_token():
            return token
        async with self._token_lock:
            if token := self._cached_access_token():
                return token
            now = int(time.time())
            token_uri = self._account.get("token_uri", GOOGLE_TOKEN_URI)
            assertion = jwt.encode(
                {
                    "iss": self._account["client_email"],
                    "scope": FCM_SCOPE,
                    "aud": token_uri,
                    "iat": now,
                    "exp": now + 3600,
                },
                self._account["private_key"],
                algorithm="RS256",
            )
            response = await self._client.post(
                token_uri,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
            response.raise_for_status()
            body = response.json()
            # 提早一分鐘換新,避免在途請求拿到剛好過期的 token
            self._access_token = (body["access_token"], now + int(body["expires_in"]) - 60)
            return body["access_token"]

    async def aclose(self) -> None:
        await self._client.aclose()


WebPushSender = Callable[..., int]


def _pywebpush_sender(**kwargs: Any) -> int:
    """pywebpush 是同步函式(requests),由呼叫端放到 thread 執行。回傳 HTTP 狀態碼。"""
    from pywebpush import WebPushException, webpush

    try:
        return webpush(**kwargs).status_code
    except WebPushException as exc:
        if exc.response is None:
            raise
        return exc.response.status_code


class WebPushGateway(PushGateway):
    """Web Push(VAPID + aes128gcm 加密)。token 是瀏覽器給的 subscription JSON 字串。"""

    def __init__(self, settings: Settings, *, sender: WebPushSender = _pywebpush_sender) -> None:
        self._settings = settings
        self._sender = sender

    async def send(self, recipient: Recipient, notification: Notification) -> DeliveryResult:
        try:
            subscription = json.loads(recipient.token)
            subscription["endpoint"]
        except (ValueError, TypeError, KeyError):
            # 解析不了的 subscription 永遠送不到,留著只會每次都失敗
            return DeliveryResult.ENDPOINT_GONE

        link = deep_link(Channel.WEB, notification.target, self._settings)
        payload = {
            "title": notification.title,
            "body": notification.body,
            "image": notification.image_url,
            **_data(notification, link),
        }
        status = await asyncio.to_thread(
            self._sender,
            subscription_info=subscription,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=self._settings.web_push_vapid_private_key,
            vapid_claims={"sub": self._settings.web_push_vapid_subject},
            ttl=NOTIFICATION_TTL_SECONDS,
            timeout=self._settings.push_provider_timeout_seconds,
        )
        if 200 <= status < 300:
            return DeliveryResult.DELIVERED
        if status in (404, 410):
            return DeliveryResult.ENDPOINT_GONE
        logger.warning("Web Push rejected push to %s: %s", recipient.id, status)
        return DeliveryResult.FAILED


class UnconfiguredGateway(PushGateway):
    """憑證尚未備妥時的管道:一律 FAILED(不是 ENDPOINT_GONE,否則會把所有登記刪光)。"""

    def __init__(self, channel_name: str) -> None:
        self._channel_name = channel_name

    async def send(self, recipient: Recipient, notification: Notification) -> DeliveryResult:
        logger.warning("%s push channel is not configured; dropping push", self._channel_name)
        return DeliveryResult.FAILED


class RoutingPushGateway(PushGateway):
    def __init__(self, gateways: Mapping[Channel, PushGateway]) -> None:
        self._gateways = dict(gateways)

    async def send(self, recipient: Recipient, notification: Notification) -> DeliveryResult:
        return await self._gateways[recipient.channel].send(recipient, notification)

    async def aclose(self) -> None:
        for gateway in self._gateways.values():
            closer = getattr(gateway, "aclose", None)
            if closer is not None:
                await closer()


def build_push_gateway(settings: Settings) -> RoutingPushGateway:
    app: PushGateway = (
        FcmGateway(settings)
        if settings.fcm_credentials_json and settings.fcm_project_id
        else UnconfiguredGateway("FCM")
    )
    web: PushGateway = (
        WebPushGateway(settings)
        if settings.web_push_vapid_private_key
        else UnconfiguredGateway("Web Push")
    )
    return RoutingPushGateway({Channel.APP: app, Channel.WEB: web})
