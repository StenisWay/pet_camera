"""HTTP 層測試:用真的 app,但每個 port 都 override 成 fake——不連資料庫。"""

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import get_clock, get_id_generator, get_rate_limit_counter
from app.core.security import get_current_user_id
from app.domains.album.presentation.dependencies import (
    get_album_queries,
    get_album_uow,
    get_object_storage,
)
from app.domains.drive_export.presentation.dependencies import (
    get_album_content,
    get_drive_uow,
    get_export_scheduler,
    get_google_drive,
    get_google_oauth,
    get_oauth_state_store,
)
from app.main import create_app
from tests.domains.album.builders import OWNER
from tests.domains.album.fakes import (
    FakeAlbumQueries,
    FakeAlbumUnitOfWork,
    FakeMediaObjectStorage,
    FixedClock,
    InMemoryRateLimitCounter,
    SequentialIds,
)
from tests.domains.drive_export.fakes import (
    CollectingExportScheduler,
    FakeAlbumContent,
    FakeDriveExportUnitOfWork,
    FakeGoogleDrive,
    FakeGoogleOAuth,
    InMemoryOAuthStateStore,
)


@pytest.fixture
def current_user_id() -> uuid.UUID:
    return OWNER


@pytest.fixture
def album_uow() -> FakeAlbumUnitOfWork:
    return FakeAlbumUnitOfWork()


@pytest.fixture
def drive_uow() -> FakeDriveExportUnitOfWork:
    return FakeDriveExportUnitOfWork()


@pytest.fixture
def storage() -> FakeMediaObjectStorage:
    return FakeMediaObjectStorage()


@pytest.fixture
def album_content() -> FakeAlbumContent:
    return FakeAlbumContent()


@pytest.fixture
def scheduler() -> CollectingExportScheduler:
    return CollectingExportScheduler()


@pytest.fixture
def oauth() -> FakeGoogleOAuth:
    return FakeGoogleOAuth()


@pytest.fixture
def drive() -> FakeGoogleDrive:
    return FakeGoogleDrive()


@pytest.fixture
def states() -> InMemoryOAuthStateStore:
    return InMemoryOAuthStateStore()


@pytest.fixture
def rate_limit_counter() -> InMemoryRateLimitCounter:
    return InMemoryRateLimitCounter()


@pytest.fixture
def app(
    album_uow,
    drive_uow,
    storage,
    album_content,
    scheduler,
    oauth,
    drive,
    states,
    rate_limit_counter,
    current_user_id,
):
    application = create_app(lifespan_enabled=False)
    overrides = {
        get_current_user_id: lambda: current_user_id,
        get_clock: lambda: FixedClock(),
        get_id_generator: lambda: SequentialIds(),
        get_rate_limit_counter: lambda: rate_limit_counter,
        get_album_uow: lambda: album_uow,
        get_album_queries: lambda: FakeAlbumQueries(album_uow),
        get_object_storage: lambda: storage,
        get_drive_uow: lambda: drive_uow,
        get_album_content: lambda: album_content,
        get_export_scheduler: lambda: scheduler,
        get_google_oauth: lambda: oauth,
        get_google_drive: lambda: drive,
        get_oauth_state_store: lambda: states,
    }
    application.dependency_overrides.update(overrides)
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://album.test"
    ) as http_client:
        yield http_client
