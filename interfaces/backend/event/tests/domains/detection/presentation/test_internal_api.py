"""內部端點的 HTTP 契約:08_spec 第 3.3 節。"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.domains.detection.presentation.dependencies import (
    get_detection_uow,
    get_media_uploader,
)
from app.main import create_app
from tests.domains.detection.application.test_purge_device_events import a_ready_event
from tests.domains.detection.builders import DEVICE
from tests.domains.detection.fakes import FakeDetectionUnitOfWork, FakeMediaUploader

KEY = get_settings().internal_api_key


@pytest.fixture
def uow() -> FakeDetectionUnitOfWork:
    return FakeDetectionUnitOfWork()


@pytest.fixture
def uploader() -> FakeMediaUploader:
    return FakeMediaUploader()


@pytest.fixture
async def client(uow, uploader):
    app = create_app()
    app.dependency_overrides.update(
        {get_detection_uow: lambda: uow, get_media_uploader: lambda: uploader}
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_purging_returns_the_deleted_count(client, uow):
    uow.given(a_ready_event())

    resp = await client.delete(
        f"/internal/devices/{DEVICE}/events", headers={"X-Internal-Api-Key": KEY}
    )

    assert resp.status_code == 200
    assert resp.json() == {"deleted_count": 1}


async def test_purging_an_empty_device_is_still_ok(client):
    """Device 服務可能重試,冪等不該變成錯誤。"""
    resp = await client.delete(
        f"/internal/devices/{DEVICE}/events", headers={"X-Internal-Api-Key": KEY}
    )

    assert resp.status_code == 200
    assert resp.json() == {"deleted_count": 0}


@pytest.mark.parametrize("headers", [{}, {"X-Internal-Api-Key": "wrong"}])
async def test_the_internal_endpoint_is_not_open_to_the_world(client, uow, headers):
    """只走 VCN 私有網路,共享金鑰是第二道防線——沒有它任何人都能清空別人的事件。"""
    uow.given(a_ready_event())

    resp = await client.delete(f"/internal/devices/{DEVICE}/events", headers=headers)

    assert resp.status_code == 403
    assert uow.commit_count == 0


async def test_the_internal_endpoint_does_not_use_the_user_token(client):
    """這支不是給登入使用者用的,所以不吃 Authorization,只認 X-Internal-Api-Key。"""
    resp = await client.delete(
        f"/internal/devices/{DEVICE}/events", headers={"Authorization": "Bearer whatever"}
    )

    assert resp.status_code == 403
