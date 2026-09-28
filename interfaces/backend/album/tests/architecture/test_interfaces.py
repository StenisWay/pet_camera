"""每個介面至少要有正式實作與測試替身,且都能被實例化(沒有漏實作的抽象方法)。"""

import inspect

import pytest

from app.core.rate_limit import RateLimitCounter
from app.core.redis_rate_limit import RedisRateLimitCounter
from app.core.system import SystemClock, Uuid7Generator
from app.domains.album.application.ports import (
    AlbumQueries,
    AlbumUnitOfWork,
    MediaObjectStorage,
)
from app.domains.album.domain.repositories import AlbumItemRepository
from app.domains.album.infrastructure.queries import SqlAlchemyAlbumQueries
from app.domains.album.infrastructure.r2_storage import R2ObjectStorage
from app.domains.album.infrastructure.repositories import SqlAlchemyAlbumItemRepository
from app.domains.album.infrastructure.unit_of_work import SqlAlchemyAlbumUnitOfWork
from app.domains.drive_export.application.ports import (
    AlbumContent,
    DriveExportUnitOfWork,
    ExportScheduler,
    GoogleDrive,
    GoogleOAuth,
    OAuthStateStore,
)
from app.domains.drive_export.domain.repositories import DriveConnectionRepository
from app.domains.drive_export.infrastructure.album_adapter import AlbumApiContent
from app.domains.drive_export.infrastructure.google import HttpGoogleDrive, HttpGoogleOAuth
from app.domains.drive_export.infrastructure.redis_state_store import RedisOAuthStateStore
from app.domains.drive_export.infrastructure.repositories import (
    SqlAlchemyDriveConnectionRepository,
)
from app.domains.drive_export.infrastructure.unit_of_work import SqlAlchemyDriveExportUnitOfWork
from app.domains.drive_export.presentation.scheduler import BackgroundTaskExportScheduler
from app.shared_kernel.ports import Clock, IdGenerator
from tests.domains.album.fakes import (
    FakeAlbumItemRepository,
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
    FakeDriveConnectionRepository,
    FakeDriveExportUnitOfWork,
    FakeGoogleDrive,
    FakeGoogleOAuth,
    InMemoryOAuthStateStore,
)

IMPLEMENTATIONS = [
    (AlbumItemRepository, SqlAlchemyAlbumItemRepository),
    (AlbumItemRepository, FakeAlbumItemRepository),
    (AlbumUnitOfWork, SqlAlchemyAlbumUnitOfWork),
    (AlbumUnitOfWork, FakeAlbumUnitOfWork),
    (AlbumQueries, SqlAlchemyAlbumQueries),
    (AlbumQueries, FakeAlbumQueries),
    (MediaObjectStorage, R2ObjectStorage),
    (MediaObjectStorage, FakeMediaObjectStorage),
    (DriveConnectionRepository, SqlAlchemyDriveConnectionRepository),
    (DriveConnectionRepository, FakeDriveConnectionRepository),
    (DriveExportUnitOfWork, SqlAlchemyDriveExportUnitOfWork),
    (DriveExportUnitOfWork, FakeDriveExportUnitOfWork),
    (AlbumContent, AlbumApiContent),
    (AlbumContent, FakeAlbumContent),
    (GoogleOAuth, HttpGoogleOAuth),
    (GoogleOAuth, FakeGoogleOAuth),
    (GoogleDrive, HttpGoogleDrive),
    (GoogleDrive, FakeGoogleDrive),
    (OAuthStateStore, RedisOAuthStateStore),
    (OAuthStateStore, InMemoryOAuthStateStore),
    (ExportScheduler, BackgroundTaskExportScheduler),
    (ExportScheduler, CollectingExportScheduler),
    (RateLimitCounter, RedisRateLimitCounter),
    (RateLimitCounter, InMemoryRateLimitCounter),
    (Clock, SystemClock),
    (Clock, FixedClock),
    (IdGenerator, Uuid7Generator),
    (IdGenerator, SequentialIds),
]


@pytest.mark.parametrize(("interface", "impl"), IMPLEMENTATIONS, ids=lambda x: x.__name__)
def test_implementation_explicitly_implements_interface(interface, impl):
    assert issubclass(impl, interface)
    assert not inspect.isabstract(impl), f"{impl.__name__} 尚未實作:{impl.__abstractmethods__}"
