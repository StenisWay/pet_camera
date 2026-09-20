"""組裝點(composition root):把 port 接上實作。

每個 port 一個 provider,測試因此可以用 dependency_overrides 換掉任何一個,
在完全不碰資料庫與 R2 的情況下驗證 HTTP 契約。
"""

from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.core.database import get_session_factory
from app.core.system import get_clock
from app.domains.timeline.application.ports import (
    DeviceOwnership,
    MediaUrlIssuer,
    TimelineQueries,
    TimelineUnitOfWork,
)
from app.domains.timeline.application.use_cases.get_playback_url import GetPlaybackUrl
from app.domains.timeline.application.use_cases.list_timeline import ListTimeline
from app.domains.timeline.application.use_cases.mark_event_read import MarkEventRead
from app.domains.timeline.infrastructure.device_adapter import HttpDeviceOwnership
from app.domains.timeline.infrastructure.queries import SqlAlchemyTimelineQueries
from app.domains.timeline.infrastructure.storage_adapter import R2MediaUrlIssuer
from app.domains.timeline.infrastructure.unit_of_work import SqlAlchemyTimelineUnitOfWork
from app.shared_kernel.ports import Clock

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_timeline_uow(settings: SettingsDep) -> TimelineUnitOfWork:
    return SqlAlchemyTimelineUnitOfWork(get_session_factory())


def get_timeline_queries(settings: SettingsDep) -> TimelineQueries:
    return SqlAlchemyTimelineQueries(get_session_factory())


def get_device_ownership(settings: SettingsDep) -> DeviceOwnership:
    return HttpDeviceOwnership(
        base_url=settings.device_service_url, api_key=settings.internal_api_key
    )


def get_media_urls(settings: SettingsDep) -> MediaUrlIssuer:
    return R2MediaUrlIssuer(settings)


def get_list_timeline(
    queries: Annotated[TimelineQueries, Depends(get_timeline_queries)],
    ownership: Annotated[DeviceOwnership, Depends(get_device_ownership)],
    urls: Annotated[MediaUrlIssuer, Depends(get_media_urls)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> ListTimeline:
    return ListTimeline(queries=queries, ownership=ownership, urls=urls, clock=clock)


def get_playback_url_use_case(
    uow: Annotated[TimelineUnitOfWork, Depends(get_timeline_uow)],
    ownership: Annotated[DeviceOwnership, Depends(get_device_ownership)],
    urls: Annotated[MediaUrlIssuer, Depends(get_media_urls)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> GetPlaybackUrl:
    return GetPlaybackUrl(uow=uow, ownership=ownership, urls=urls, clock=clock)


def get_mark_event_read(
    uow: Annotated[TimelineUnitOfWork, Depends(get_timeline_uow)],
    ownership: Annotated[DeviceOwnership, Depends(get_device_ownership)],
) -> MarkEventRead:
    return MarkEventRead(uow=uow, ownership=ownership)
