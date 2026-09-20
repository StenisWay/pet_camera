"""HTTP 層測試的裝配。

adapter 全部換成 fake,直接覆寫 app.state——presentation 的 provider 本來就只從
app.state 取東西,所以不需要 dependency_overrides,也不需要 Redis / TURN / Device 服務。

用 httpx.AsyncClient + ASGITransport,不用 TestClient:TestClient 會另外起一個
event loop,而本服務的核心行為(長輪詢、等待 answer)就是 async 的時序。
"""

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.security import SharedSecretCameraAuthenticator
from app.main import create_app
from tests.domains.streaming.builders import ALICE, NOW, SESSION_A, a_device
from tests.domains.streaming.fakes import (
    FakeClock,
    FakeDeviceDirectory,
    FakeRateLimitCounter,
    FakeSignalingEvents,
    FakeTurnCredentialIssuer,
    FixedIdGenerator,
    InMemoryStreamSessionRepository,
)

CAMERA_SECRET = "camera-shared-secret"
SECOND_SESSION = uuid.UUID("00000000-0000-0000-0000-000000005e52")


@pytest.fixture(scope="session", autouse=True)
def _fast_timeouts() -> AsyncIterator[None]:  # type: ignore[misc]
    """把 signaling 的等待時間壓到毫秒級。

    行為與 5 秒 / 30 秒完全相同,只是不讓測試真的坐等——逾時門檻本身在
    application 層用注入的值測過了。
    """
    # HS256 的金鑰長度至少 32 bytes(RFC 7518 3.2);預設值只是佔位字串
    os.environ["STREAM_JWT_SECRET"] = "test-secret-at-least-32-bytes-long!!"
    os.environ["STREAM_ANSWER_WAIT_TIMEOUT_SECONDS"] = "0.05"
    os.environ["STREAM_PENDING_OFFER_POLL_TIMEOUT_SECONDS"] = "0.05"
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def sessions(clock: FakeClock) -> InMemoryStreamSessionRepository:
    return InMemoryStreamSessionRepository(clock)


@pytest.fixture
def events() -> FakeSignalingEvents:
    return FakeSignalingEvents()


@pytest.fixture
def devices() -> FakeDeviceDirectory:
    return FakeDeviceDirectory(a_device())


@pytest.fixture
def rate_counter() -> FakeRateLimitCounter:
    return FakeRateLimitCounter()


@pytest.fixture
def app(
    clock: FakeClock,
    sessions: InMemoryStreamSessionRepository,
    events: FakeSignalingEvents,
    devices: FakeDeviceDirectory,
    rate_counter: FakeRateLimitCounter,
) -> FastAPI:
    application = create_app(lifespan_enabled=False)
    application.state.clock = clock
    application.state.id_generator = FixedIdGenerator(SESSION_A, SECOND_SESSION)
    application.state.session_repository = sessions
    application.state.signaling_events = events
    application.state.device_directory = devices
    application.state.turn_issuer = FakeTurnCredentialIssuer()
    application.state.rate_limit_counter = rate_counter
    application.state.camera_authenticator = SharedSecretCameraAuthenticator(CAMERA_SECRET)
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


def auth_header(user_id: uuid.UUID = ALICE) -> dict[str, str]:
    """Auth 服務簽發的 access token。exp 用真實時間,JWT 的驗證不看 FakeClock。"""
    settings = get_settings()
    token = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(UTC) + timedelta(hours=1)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


def camera_header(secret: str = CAMERA_SECRET) -> dict[str, str]:
    return {"X-Device-Credential": secret}
