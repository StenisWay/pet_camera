import pytest

from tests.domains.album.fakes import (
    FakeAlbumQueries,
    FakeAlbumUnitOfWork,
    FakeMediaObjectStorage,
    FixedClock,
)


@pytest.fixture
def uow() -> FakeAlbumUnitOfWork:
    return FakeAlbumUnitOfWork()


@pytest.fixture
def storage() -> FakeMediaObjectStorage:
    return FakeMediaObjectStorage()


@pytest.fixture
def queries(uow: FakeAlbumUnitOfWork) -> FakeAlbumQueries:
    return FakeAlbumQueries(uow)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()
