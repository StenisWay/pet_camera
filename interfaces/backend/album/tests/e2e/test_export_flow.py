"""端到端:授權 → 選取項目匯出 → 背景上傳 → 相簿狀態變成 exported。

整支 app、真實資料庫、真實的兩個領域接線,只有 Google 與 R2 是 fake(不對外發網路)。
標記 integration,需要真實 PostgreSQL:uv run pytest -m integration
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import get_clock, get_id_generator, get_rate_limit_counter
from app.core.security import get_current_user_id
from app.core.system import SystemClock, Uuid7Generator
from app.domains.album.api import AlbumApi
from app.domains.album.infrastructure.orm import MediaItemRow
from app.domains.album.presentation.dependencies import get_object_storage
from app.domains.drive_export.application.ports import OAuthTokens
from app.domains.drive_export.infrastructure.album_adapter import AlbumApiContent
from app.domains.drive_export.presentation.dependencies import (
    get_album_content,
    get_google_drive,
    get_google_oauth,
    get_oauth_state_store,
)
from app.main import create_app
from tests.domains.album.fakes import FakeMediaObjectStorage, InMemoryRateLimitCounter
from tests.domains.drive_export.fakes import (
    FakeGoogleDrive,
    FakeGoogleOAuth,
    InMemoryOAuthStateStore,
)

pytestmark = pytest.mark.integration

OWNER = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
CAPTURED_AT = datetime(2026, 9, 20, 10, 30, 15, tzinfo=UTC)


@pytest.fixture
def storage() -> FakeMediaObjectStorage:
    return FakeMediaObjectStorage()


@pytest.fixture
def oauth() -> FakeGoogleOAuth:
    return FakeGoogleOAuth()


@pytest.fixture
def drive() -> FakeGoogleDrive:
    return FakeGoogleDrive()


@pytest.fixture
def app(session_factory, storage, oauth, drive):
    application = create_app(lifespan_enabled=False)
    clock = SystemClock()
    # 真實接線:drive_export 透過 album 的公開 API 取得相簿能力
    album_content = AlbumApiContent(AlbumApi(session_factory, storage, clock))
    application.dependency_overrides.update(
        {
            get_current_user_id: lambda: OWNER,
            get_clock: lambda: clock,
            get_id_generator: lambda: Uuid7Generator(),
            get_rate_limit_counter: lambda: InMemoryRateLimitCounter(),
            get_object_storage: lambda: storage,
            get_album_content: lambda: album_content,
            get_google_oauth: lambda: oauth,
            get_google_drive: lambda: drive,
            get_oauth_state_store: lambda: InMemoryOAuthStateStore(),
        }
    )
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://album.test"
    ) as http_client:
        yield http_client


async def given_ready_item(session_factory) -> uuid.UUID:
    item_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            MediaItemRow(
                id=item_id,
                user_id=OWNER,
                device_id=uuid.uuid4(),
                type="clip",
                object_key=f"media/{OWNER}/{item_id}.mp4",
                thumbnail_object_key=f"media-thumbnails/{OWNER}/{item_id}.jpg",
                duration_sec=30,
                status="ready",
                captured_at=CAPTURED_AT,
                drive_export_status="not_exported",
            )
        )
        await session.commit()
    return item_id


async def test_user_can_connect_drive_then_export_a_clip(client, session_factory, oauth, drive):
    item_id = await given_ready_item(session_factory)

    # 1. 取得授權連結並完成綁定
    url = (await client.get("/integrations/google-drive/oauth-url")).json()["authorization_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    oauth.codes["code-1"] = OAuthTokens(access_token="at", refresh_token="rt-1")
    assert (
        await client.post(
            "/integrations/google-drive/oauth-callback",
            json={"code": "code-1", "state": state},
        )
    ).status_code == 204

    # 2. 送出匯出(背景任務在回應送出後執行)
    accepted = await client.post(
        "/media/export/google-drive", json={"media_item_ids": [str(item_id)]}
    )
    assert accepted.status_code == 202

    # 3. 檔案進了「寵物攝影機」資料夾,相簿狀態變成 exported
    upload = drive.uploads[0]
    assert upload["folder_id"] == drive.folders["寵物攝影機"]
    assert upload["filename"] == "clip_20260920_103015.mp4"

    item = next(i for i in (await client.get("/media")).json()["items"] if i["id"] == str(item_id))
    assert item["drive_export_status"] == "exported"
    assert item["drive_file_id"] == upload["file_id"]


async def test_deleting_an_item_removes_it_from_the_album_and_r2(
    client, session_factory, storage
):
    item_id = await given_ready_item(session_factory)

    assert (await client.delete(f"/media/{item_id}")).status_code == 204

    assert (await client.get("/media")).json()["items"] == []
    assert len(storage.deleted) == 2  # 內容 + 縮圖
