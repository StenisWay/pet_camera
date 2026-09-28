"""相簿列表的讀取端實作(CQRS 的讀取側)。

只回傳 DTO,不組實體:列表一次 30 筆,只是為了顯示縮圖網格,沒有業務規則要執行。
"""

import uuid

from sqlalchemy import Select, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.album.application.dtos import AlbumItemResult, AlbumPageResult
from app.domains.album.application.ports import AlbumQueries
from app.domains.album.domain.value_objects import DateRange, PageSize
from app.domains.album.infrastructure.orm import MediaItemRow
from app.shared_kernel.paging import Cursor


class SqlAlchemyAlbumQueries(AlbumQueries):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_page(
        self,
        owner_id: uuid.UUID,
        *,
        cursor: str | None,
        page_size: PageSize,
        date_range: DateRange,
    ) -> AlbumPageResult:
        stmt: Select = select(MediaItemRow).where(MediaItemRow.user_id == owner_id)
        if date_range.start is not None:
            stmt = stmt.where(MediaItemRow.captured_at >= date_range.start)
        if date_range.end is not None:
            stmt = stmt.where(MediaItemRow.captured_at < date_range.end)
        if cursor:
            decoded = Cursor.decode(cursor)
            stmt = stmt.where(
                tuple_(MediaItemRow.captured_at, MediaItemRow.id)
                < (decoded.captured_at, decoded.item_id)
            )

        stmt = stmt.order_by(MediaItemRow.captured_at.desc(), MediaItemRow.id.desc())
        # 多撈一筆來判斷還有沒有下一頁,不必另外 count
        rows = list(await self.session.scalars(stmt.limit(page_size.value + 1)))
        has_more = len(rows) > page_size.value
        rows = rows[: page_size.value]
        next_cursor = Cursor(rows[-1].captured_at, rows[-1].id).encode() if has_more else None
        return AlbumPageResult(
            items=[_to_result(row) for row in rows], next_cursor=next_cursor
        )


def _to_result(row: MediaItemRow) -> AlbumItemResult:
    return AlbumItemResult(
        id=row.id,
        type=row.type,
        status=row.status,
        captured_at=row.captured_at,
        duration_sec=row.duration_sec,
        drive_export_status=row.drive_export_status,
        drive_file_id=row.drive_file_id,
        object_key=row.object_key,
        thumbnail_object_key=row.thumbnail_object_key,
    )
