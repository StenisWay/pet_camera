"""album 的組裝點。共用的基礎設施 provider 在 app/core/dependencies.py。"""

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, Request

from app.core.dependencies import ClockDep, SessionFactoryDep, SettingsDep
from app.domains.album.application.ports import (
    AlbumQueries,
    AlbumUnitOfWork,
    MediaObjectStorage,
)
from app.domains.album.application.use_cases.delete_album_item import DeleteAlbumItem
from app.domains.album.application.use_cases.expire_stale_exports import ExpireStaleExports
from app.domains.album.application.use_cases.list_album import ListAlbum
from app.domains.album.application.use_cases.purge_user_album import PurgeUserAlbum
from app.domains.album.infrastructure.queries import SqlAlchemyAlbumQueries
from app.domains.album.infrastructure.unit_of_work import SqlAlchemyAlbumUnitOfWork


def get_object_storage(request: Request) -> MediaObjectStorage:
    return request.app.state.object_storage


def get_album_uow(session_factory: SessionFactoryDep) -> AlbumUnitOfWork:
    return SqlAlchemyAlbumUnitOfWork(session_factory)


async def get_album_queries(session_factory: SessionFactoryDep) -> AsyncIterator[AlbumQueries]:
    async with session_factory() as session:
        yield SqlAlchemyAlbumQueries(session)


AlbumUowDep = Annotated[AlbumUnitOfWork, Depends(get_album_uow)]
ObjectStorageDep = Annotated[MediaObjectStorage, Depends(get_object_storage)]
AlbumQueriesDep = Annotated[AlbumQueries, Depends(get_album_queries)]


def get_list_album(queries: AlbumQueriesDep, settings: SettingsDep) -> ListAlbum:
    return ListAlbum(
        queries,
        default_page_size=settings.page_size,
        max_page_size=settings.max_page_size,
        timezone=ZoneInfo(settings.timezone),
    )


def get_delete_album_item(uow: AlbumUowDep, storage: ObjectStorageDep) -> DeleteAlbumItem:
    return DeleteAlbumItem(uow, storage)


def get_purge_user_album(uow: AlbumUowDep, storage: ObjectStorageDep) -> PurgeUserAlbum:
    return PurgeUserAlbum(uow, storage)


def get_expire_stale_exports(
    uow: AlbumUowDep, clock: ClockDep, settings: SettingsDep
) -> ExpireStaleExports:
    return ExpireStaleExports(
        uow, clock, stale_after=timedelta(seconds=settings.export_stale_after_seconds)
    )


ListAlbumDep = Annotated[ListAlbum, Depends(get_list_album)]
DeleteAlbumItemDep = Annotated[DeleteAlbumItem, Depends(get_delete_album_item)]
PurgeUserAlbumDep = Annotated[PurgeUserAlbum, Depends(get_purge_user_album)]
