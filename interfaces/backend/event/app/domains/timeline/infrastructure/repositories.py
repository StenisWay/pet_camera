"""TimelineEventRepository 的 SQLAlchemy 實作。"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.orm import EventRow
from app.domains.timeline.domain.entities import TimelineEvent
from app.domains.timeline.domain.repositories import TimelineEventRepository
from app.domains.timeline.infrastructure.mappers import to_timeline_event


class SqlAlchemyTimelineEventRepository(TimelineEventRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, event_id: UUID) -> TimelineEvent | None:
        row = await self.session.get(EventRow, event_id)
        return to_timeline_event(row) if row is not None else None

    async def save_read_state(self, event: TimelineEvent) -> None:
        """只寫 is_read。

        用 UPDATE 而不是把整個實體寫回去:events 的其他欄位屬於 detection,
        timeline 如果整列覆寫,就可能用讀取當下的舊值蓋掉 worker 剛寫進去的狀態。
        commit 由 UnitOfWork 負責,這裡只 flush。
        """
        row = await self.session.get(EventRow, event.id)
        if row is None:
            return
        row.is_read = event.is_read
        await self.session.flush()


async def _exists(session: AsyncSession, event_id: UUID) -> bool:
    return (
        await session.scalar(select(EventRow.id).where(EventRow.id == event_id))
    ) is not None
