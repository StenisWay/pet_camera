from datetime import tzinfo

from app.domains.album.application.dtos import AlbumPageResult, ListAlbumQuery
from app.domains.album.application.ports import AlbumQueries
from app.domains.album.domain.value_objects import DateRange, PageSize


class ListAlbum:
    """12_spec 第 2.1 節:相簿項目依 captured_at 由新到舊分頁。"""

    def __init__(
        self,
        queries: AlbumQueries,
        *,
        default_page_size: int,
        max_page_size: int,
        timezone: tzinfo,
    ) -> None:
        self.queries = queries
        self.default_page_size = default_page_size
        self.max_page_size = max_page_size
        # 日期篩選與分組的時區,見 DateRange
        self.timezone = timezone

    async def execute(self, query: ListAlbumQuery) -> AlbumPageResult:
        date_range = DateRange.build(
            tz=self.timezone,
            day=query.date,
            date_from=query.date_from,
            date_to=query.date_to,
        )
        page_size = PageSize.build(
            query.limit, default=self.default_page_size, maximum=self.max_page_size
        )
        return await self.queries.list_page(
            query.owner_id,
            cursor=query.cursor,
            page_size=page_size,
            date_range=date_range,
        )
