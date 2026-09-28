"""MediaItemRepository 的 SQLAlchemy 實作。

明確繼承介面:漏實作任何抽象方法,建立實例當下就 TypeError。
只 flush 不 commit——交易邊界由 UnitOfWork(也就是 use case)決定。
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.media.domain.entities import MediaItem, MediaItemStatus
from app.domains.media.domain.repositories import MediaItemRepository
from app.domains.media.infrastructure.mappers import apply_to_row, to_entity, to_new_row
from app.domains.media.infrastructure.orm import MediaItemRow

ACTIVE_STATUSES = (MediaItemStatus.PROCESSING.value, MediaItemStatus.READY.value)


class SqlAlchemyMediaItemRepository(MediaItemRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _row(self, item_id: uuid.UUID) -> MediaItemRow | None:
        return await self.session.get(MediaItemRow, item_id)

    async def get(self, item_id: uuid.UUID, *, owner_id: uuid.UUID) -> MediaItem | None:
        row = await self._row(item_id)
        # 擁有者過濾放在查詢結果上而不是外層判斷,讓「查不到」與「不是你的」走同一條路
        if row is None or row.user_id != owner_id:
            return None
        return to_entity(row)

    async def get_internal(self, item_id: uuid.UUID) -> MediaItem | None:
        row = await self._row(item_id)
        return to_entity(row) if row is not None else None

    async def add(self, item: MediaItem) -> None:
        self.session.add(to_new_row(item))
        await self.session.flush()

    async def save(self, item: MediaItem) -> None:
        row = await self._row(item.id)
        if row is None:
            self.session.add(to_new_row(item))
        else:
            apply_to_row(item, row)
        await self.session.flush()

    async def find_active_clip(
        self,
        *,
        owner_id: uuid.UUID,
        source_event_id: uuid.UUID,
        captured_at: datetime,
        duration_sec: int,
    ) -> MediaItem | None:
        stmt = (
            select(MediaItemRow)
            .where(
                MediaItemRow.user_id == owner_id,
                MediaItemRow.source_event_id == source_event_id,
                MediaItemRow.captured_at == captured_at,
                MediaItemRow.duration_sec == duration_sec,
                MediaItemRow.status.in_(ACTIVE_STATUSES),
            )
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return to_entity(row) if row is not None else None

    async def list_stale_processing(self, *, changed_before: datetime) -> list[MediaItem]:
        stmt = select(MediaItemRow).where(
            MediaItemRow.status == MediaItemStatus.PROCESSING.value,
            MediaItemRow.updated_at < changed_before,
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [to_entity(row) for row in rows]
