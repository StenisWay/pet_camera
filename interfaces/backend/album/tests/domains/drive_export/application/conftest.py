import pytest

from tests.domains.album.fakes import FixedClock, SequentialIds
from tests.domains.drive_export.fakes import (
    CollectingExportScheduler,
    FakeAlbumContent,
    FakeDriveExportUnitOfWork,
    FakeGoogleDrive,
    FakeGoogleOAuth,
    InMemoryOAuthStateStore,
)


@pytest.fixture
def uow() -> FakeDriveExportUnitOfWork:
    return FakeDriveExportUnitOfWork()


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
def album() -> FakeAlbumContent:
    return FakeAlbumContent()


@pytest.fixture
def scheduler() -> CollectingExportScheduler:
    return CollectingExportScheduler()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def ids() -> SequentialIds:
    return SequentialIds()
