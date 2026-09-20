"""EventRepository 的 SQLAlchemy 實作。"""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.orm import EventRow
from app.domains.detection.domain.entities import Event
from app.domains.detection.domain.repositories import EventRepository, PurgedEvents
from app.domains.detection.infrastructure.mappers import apply_to_row, to_entity, to_new_row


class SqlAlchemyEventRepository(EventRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, event_id: UUID) -> Event | None:
        row = await self.session.get(EventRow, event_id)
        return to_entity(row) if row is not None else None

    async def save(self, event: Event) -> None:
        """新增或更新;只 flush,commit 由 UnitOfWork 負責。"""
        row = await self.session.get(EventRow, event.id)
        if row is None:
            self.session.add(to_new_row(event))
        else:
            apply_to_row(event, row)
        await self.session.flush()

    async def delete_all_by_device(self, device_id: UUID) -> PurgedEvents:
        """先把 key 撈出來再刪——刪掉之後就再也問不到有哪些物件要清。"""
        rows = list(
            (
                await self.session.scalars(
                    select(EventRow).where(EventRow.device_id == device_id)
                )
            ).all()
        )
        keys = [
            key
            for row in rows
            for key in (row.video_object_key, row.thumbnail_object_key)
            if key
        ]
        if rows:
            await self.session.execute(
                delete(EventRow).where(EventRow.device_id == device_id)
            )
            await self.session.flush()
        return PurgedEvents(deleted_count=len(rows), object_keys=keys)
