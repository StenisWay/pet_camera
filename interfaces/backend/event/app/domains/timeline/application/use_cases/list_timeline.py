"""時間軸列表:08_spec_時間軸與事件歷史.md 第 2.1 節。"""

from datetime import datetime

from app.domains.timeline.application.dtos import (
    ListTimelineQuery,
    TimelineItemResult,
    TimelinePageResult,
)
from app.domains.timeline.application.ports import (
    DeviceOwnership,
    MediaUrlIssuer,
    TimelineQueries,
)
from app.domains.timeline.domain.entities import TimelineEvent
from app.domains.timeline.domain.exceptions import DeviceNotFound
from app.domains.timeline.domain.value_objects import DateRange, PageSize, TimelineCursor
from app.shared_kernel.ports import Clock


class ListTimeline:
    """時間軸的讀取端。

    沒有業務規則需要聚合參與,所以直接走 TimelineQueries 回 DTO(CQRS 的讀取側);
    唯一的「規則」是縮圖還在不在保留期內,那由 TimelineEvent 自己回答。
    """

    def __init__(
        self,
        *,
        queries: TimelineQueries,
        ownership: DeviceOwnership,
        urls: MediaUrlIssuer,
        clock: Clock,
    ) -> None:
        self.queries = queries
        self.ownership = ownership
        self.urls = urls
        self.clock = clock

    async def execute(self, query: ListTimelineQuery) -> TimelinePageResult:
        # 先把輸入收斂成合法的形狀,再去問 Device——壞掉的 limit 不值得花一次跨服務往返
        page_size = PageSize.of(query.limit)
        date_range = DateRange.resolve(
            date=query.date,
            tz=query.tz,
            started_from=query.started_from,
            started_to=query.started_to,
        )
        cursor = TimelineCursor.decode(query.cursor) if query.cursor else None

        if not await self.ownership.is_owned_by(query.device_id, query.requester_id):
            # 不存在與非本人回同一個 404,不洩漏資源存在性(第 3.2 節)
            raise DeviceNotFound()

        page = await self.queries.list_by_device(
            query.device_id, cursor=cursor, page_size=page_size, date_range=date_range
        )

        now = self.clock.now()
        return TimelinePageResult(
            items=[await self._to_result(event, now) for event in page.items],
            next_cursor=page.next_cursor.encode() if page.next_cursor else None,
        )

    async def _to_result(self, event: TimelineEvent, now: datetime) -> TimelineItemResult:
        """縮圖的 presigned URL 直接夾在列表裡(規格審查 #3)。

        R2 不是公開 bucket,不夾帶前端就拿不到圖;一頁 20 筆再逐一去換發也不合理。
        已過保留期或尚未產生的縮圖回 None,不對不存在的物件浪費一次換發。
        """
        thumbnail_url = None
        if key := event.thumbnail_key_if_available(now):
            thumbnail_url = await self.urls.presigned_url(key)

        return TimelineItemResult(
            id=event.id,
            device_id=event.device_id,
            status=event.status,
            confidence_score=event.confidence_score,
            started_at=event.started_at,
            ended_at=event.ended_at,
            duration_sec=event.duration_sec,
            is_read=event.is_read,
            is_partial=event.is_partial,
            thumbnail_url=thumbnail_url,
        )
