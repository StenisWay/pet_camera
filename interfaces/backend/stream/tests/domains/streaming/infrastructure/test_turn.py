"""coturn REST API 認證憑證(06_spec_即時串流.md 第 2.5 節)。

演算法是與 TURN server 的契約,不是實作細節:算錯了 coturn 會拒絕,
而錯誤只會在真的建立媒體連線時才浮現——正是單元測試最該守住的地方。
"""

import base64
import hashlib
import hmac
from datetime import timedelta

from app.domains.streaming.infrastructure.turn import CoturnCredentialIssuer
from tests.domains.streaming.builders import NOW, SESSION_A

SECRET = "turn-static-secret"
TTL = timedelta(seconds=600)
URLS = ("turn:vm3.internal:3478?transport=udp",)


def issuer() -> CoturnCredentialIssuer:
    return CoturnCredentialIssuer(urls=URLS, secret=SECRET, ttl=TTL)


async def test_username_is_expiry_and_session_id() -> None:
    credentials = await issuer().issue(SESSION_A, NOW)

    expiry = int((NOW + TTL).timestamp())
    assert credentials.username == f"{expiry}:{SESSION_A}"


async def test_credential_is_base64_of_hmac_sha1() -> None:
    credentials = await issuer().issue(SESSION_A, NOW)

    expected = base64.b64encode(
        hmac.new(SECRET.encode(), credentials.username.encode(), hashlib.sha1).digest()
    ).decode()
    assert credentials.credential == expected


async def test_expiry_is_reported_and_matches_the_username() -> None:
    """username 裡的 expiry 是 TURN server 看的,expires_at 是本服務看的,
    兩個對不上就會出現「憑證看起來還沒過期但 TURN 拒收」。"""
    credentials = await issuer().issue(SESSION_A, NOW)

    assert credentials.expires_at == NOW + TTL
    assert int(credentials.expires_at.timestamp()) == int(credentials.username.split(":")[0])


async def test_urls_come_from_configuration() -> None:
    credentials = await issuer().issue(SESSION_A, NOW)

    assert credentials.urls == URLS


async def test_credentials_differ_per_session() -> None:
    """憑證綁 session_id:一條連線的憑證外洩不該能拿去中繼別人的流量。"""
    import uuid

    first = await issuer().issue(SESSION_A, NOW)
    second = await issuer().issue(uuid.uuid4(), NOW)

    assert first.credential != second.credential
