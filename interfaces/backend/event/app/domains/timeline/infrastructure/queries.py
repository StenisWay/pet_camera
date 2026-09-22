"""TimelineQueries 的 SQLAlchemy 實作:列表分頁。"""

from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.orm import EventRow
from app.domains.timeline.application.ports import TimelinePage, TimelineQueries
from app.domains.timeline.domain.value_objects import DateRange, PageSize, TimelineCursor
from app.domains.timeline.infrastructure.mappers import to_timeline_event
from app.shared_kernel.errors import ServiceUnavailable


class SqlAlchemyTimelineQueries(TimelineQueries):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_by_device(
        self,
        device_id: UUID,
        *,
        cursor: TimelineCursor | None,
        page_size: PageSize,
        date_range: DateRange,
    ) -> TimelinePage:
        stmt = (
            select(EventRow)
            .where(EventRow.device_id == device_id)
            # 排序鍵與游標的比較鍵必須完全一致,否則分頁會重複或遺漏
            .order_by(EventRow.started_at.desc(), EventRow.id.desc())
            # 多取一筆來判斷還有沒有下一頁,省掉一次 count
            .limit(page_size.value + 1)
        )
        if date_range.started_from is not None:
            stmt = stmt.where(EventRow.started_at >= date_range.started_from)
        if date_range.started_to is not None:
            stmt = stmt.where(EventRow.started_at < date_range.started_to)
        if cursor is not None:
            # 列組比較讓 Postgres 用得上 (device_id, started_at desc) 索引
            stmt = stmt.where(
                tuple_(EventRow.started_at, EventRow.id)
                < (cursor.started_at, cursor.event_id)
            )

        try:
            async with self._session_factory() as session:
                rows = list((await session.scalars(stmt)).all())
        except (SQLAlchemyError, DBAPIError, OSError) as exc:
            # 13_ADR 第 4 節:Event 的讀取選一致性——回錯誤,不可回空列表讓使用者
            # 誤以為那段時間寵物沒有動靜
            raise ServiceUnavailable() from exc

        items = [to_timeline_event(row) for row in rows[: page_size.value]]
        next_cursor = (
            TimelineCursor(started_at=items[-1].started_at, event_id=items[-1].id)
            if len(rows) > page_size.value
            else None
        )
        return TimelinePage(items=items, next_cursor=next_cursor)
