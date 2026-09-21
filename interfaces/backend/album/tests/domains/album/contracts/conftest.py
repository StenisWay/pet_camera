"""合約測試的共用裝置:同一份測試跑在所有 AlbumItemRepository / AlbumUnitOfWork 實作上。

- fake 通過 → application 測試使用的替身行為與正式實作一致,那些測試才可信
- SQLAlchemy 通過 → 正式實作確實遵守介面的 docstring 承諾

Album 不建立 media_items(那是 Media 服務的職責),所以每個實作都要提供 seed:
把一筆既有資料放進去,合約測試才有東西可讀可改。
"""

from dataclasses import dataclass
from typing import Protocol

import pytest

from app.domains.album.application.ports import AlbumUnitOfWork
from app.domains.album.domain.entities import AlbumItem
from app.domains.album.infrastructure.orm import MediaItemRow
from app.domains.album.infrastructure.unit_of_work import SqlAlchemyAlbumUnitOfWork
from tests.domains.album.fakes import FakeAlbumUnitOfWork


class Store(Protocol):
    def uow(self) -> AlbumUnitOfWork: ...
    async def seed(self, item: AlbumItem) -> AlbumItem: ...


@dataclass
class FakeStore:
    shared: FakeAlbumUnitOfWork

    def uow(self) -> AlbumUnitOfWork:
        return self.shared  # 同一個實例 = 同一個「資料庫」

    async def seed(self, item: AlbumItem) -> AlbumItem:
        return self.shared.given(item)


@dataclass
class SqlStore:
    session_factory: object

    def uow(self) -> AlbumUnitOfWork:
        return SqlAlchemyAlbumUnitOfWork(self.session_factory)

    async def seed(self, item: AlbumItem) -> AlbumItem:
        async with self.session_factory() as session:
            session.add(
                MediaItemRow(
                    id=item.id,
                    user_id=item.owner_id,
                    device_id=item.device_id,
                    type=item.type.value,
                    object_key=item.object_key,
                    thumbnail_object_key=item.thumbnail_object_key,
                    duration_sec=item.duration_sec,
                    status=item.status.value,
                    captured_at=item.captured_at,
                    drive_export_status=item.drive_export_status.value,
                    drive_file_id=item.drive_file_id,
                )
            )
            await session.commit()
        return item


@pytest.fixture(params=["fake", pytest.param("sqlalchemy", marks=pytest.mark.integration)])
def store(request) -> Store:
    if request.param == "fake":
        return FakeStore(FakeAlbumUnitOfWork())
    return SqlStore(request.getfixturevalue("session_factory"))
