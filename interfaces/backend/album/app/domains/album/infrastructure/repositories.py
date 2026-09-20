import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.album.domain.entities import AlbumItem, DriveExportStatus
from app.domains.album.domain.repositories import AlbumItemRepository
from app.domains.album.infrastructure.mappers import apply_to_row, to_entity
from app.domains.album.infrastructure.orm import MediaItemRow


class SqlAlchemyAlbumItemRepository(AlbumItemRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, item_id: uuid.UUID) -> AlbumItem | None:
        row = await self.session.get(MediaItemRow, item_id)
        return to_entity(row) if row else None

    async def get_many(self, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, AlbumItem]:
        if not item_ids:
            return {}
        rows = await self.session.scalars(
            select(MediaItemRow).where(MediaItemRow.id.in_(item_ids))
        )
        return {row.id: to_entity(row) for row in rows}

    async def save(self, item: AlbumItem) -> None:
        row = await self.session.get(MediaItemRow, item.id)
        if row is None:
            # Album 不建立 media_items(那是 Media 服務的職責),所以這是呼叫端的錯
            raise LookupError(f"media item {item.id} does not exist")
        apply_to_row(item, row)
        await self.session.flush()

    async def delete(self, item_id: uuid.UUID) -> None:
        await self.session.execute(delete(MediaItemRow).where(MediaItemRow.id == item_id))

    async def delete_all_owned_by(self, owner_id: uuid.UUID) -> list[str]:
        # 一次 DELETE ... RETURNING 就拿得到 key,不必先把整個相簿分頁讀出來
        result = await self.session.execute(
            delete(MediaItemRow)
            .where(MediaItemRow.user_id == owner_id)
            .returning(MediaItemRow.object_key, MediaItemRow.thumbnail_object_key)
        )
        keys: list[str] = []
        for object_key, thumbnail_object_key in result.all():
            keys.extend(k for k in (object_key, thumbnail_object_key) if k)
        return keys

    async def list_stale_exports(self, *, changed_before: datetime) -> list[AlbumItem]:
        rows = await self.session.scalars(
            select(MediaItemRow).where(
                MediaItemRow.drive_export_status == DriveExportStatus.EXPORTING.value,
                MediaItemRow.updated_at < changed_before,
            )
        )
        return [to_entity(row) for row in rows]
