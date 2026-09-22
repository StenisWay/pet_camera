"""時間軸的 HTTP 端點(08_spec 第 3 節)。

router 裡沒有業務判斷:輸入 schema → Command/Query → use case → Result → 輸出 schema。
例外由 core/http_errors.py 統一轉成 HTTP,這裡不寫 try/except。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.config import Settings, get_settings
from app.core.security import CurrentUserId
from app.domains.timeline.application.dtos import ListTimelineQuery
from app.domains.timeline.application.use_cases.get_playback_url import GetPlaybackUrl
from app.domains.timeline.application.use_cases.list_timeline import ListTimeline
from app.domains.timeline.application.use_cases.mark_event_read import MarkEventRead
from app.domains.timeline.presentation.dependencies import (
    get_list_timeline,
    get_mark_event_read,
    get_playback_url_use_case,
)
from app.domains.timeline.presentation.schemas import (
    MarkReadIn,
    PlaybackUrlOut,
    ReadStateOut,
    TimelinePageOut,
)

# /devices 前綴屬於 Device 服務,只有 /devices/{id}/events 這個形狀導向本服務,
# Load Balancer 的分流規則見 08_spec 第 3.1 節。
devices_router = APIRouter(prefix="/devices", tags=["timeline"])
events_router = APIRouter(prefix="/events", tags=["timeline"])


@devices_router.get("/{device_id}/events", response_model=TimelinePageOut)
async def list_events(
    device_id: UUID,
    user_id: CurrentUserId,
    use_case: Annotated[ListTimeline, Depends(get_list_timeline)],
    cursor: str | None = None,
    limit: int | None = None,
    date: str | None = None,
    tz: str | None = None,
    started_from: Annotated[int | None, Query(alias="from")] = None,
    started_to: Annotated[int | None, Query(alias="to")] = None,
) -> TimelinePageOut:
    result = await use_case.execute(
        ListTimelineQuery(
            device_id=device_id,
            requester_id=user_id,
            cursor=cursor,
            limit=limit,
            date=date,
            tz=tz,
            started_from=started_from,
            started_to=started_to,
        )
    )
    return TimelinePageOut.of(result)


@events_router.get("/{event_id}/playback-url", response_model=PlaybackUrlOut)
async def get_playback_url(
    event_id: UUID,
    user_id: CurrentUserId,
    use_case: Annotated[GetPlaybackUrl, Depends(get_playback_url_use_case)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PlaybackUrlOut:
    result = await use_case.execute(event_id, user_id)
    return PlaybackUrlOut(url=result.url, expires_in=settings.presigned_url_ttl_seconds)


@events_router.patch("/{event_id}", response_model=ReadStateOut)
async def mark_event_read(
    event_id: UUID,
    body: MarkReadIn,
    user_id: CurrentUserId,
    use_case: Annotated[MarkEventRead, Depends(get_mark_event_read)],
) -> ReadStateOut:
    result = await use_case.execute(event_id, user_id, is_read=body.is_read)
    return ReadStateOut(id=result.id, is_read=result.is_read)
