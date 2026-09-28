"""組裝點(composition root)。

adapter 一律從 app.state 取——它們在 lifespan 建立(見 app/main.py),這裡不 import
infrastructure,測試才能用 dependency_overrides 換掉任何一個 port,完全不碰
資料庫、Redis、R2 與 VM-3 的 worker。
"""

from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.rate_limit import RateLimitCounter, RateLimiter
from app.core.security import CurrentUserId
from app.domains.media.application.ports import (
    ClipWorker,
    DeviceDirectory,
    EventSource,
    FrameSource,
    MediaStorage,
    MediaUnitOfWork,
)
from app.domains.media.application.use_cases.expire_stale_processing import (
    ExpireStaleProcessing,
)
from app.domains.media.application.use_cases.finish_media_item import (
    CompleteMediaItem,
    FailMediaItem,
)
from app.domains.media.application.use_cases.get_media_item import GetMediaItem
from app.domains.media.application.use_cases.request_clip import RequestClip
from app.domains.media.application.use_cases.take_event_screenshot import TakeEventScreenshot
from app.domains.media.application.use_cases.take_live_screenshot import TakeLiveScreenshot
from app.shared_kernel.ports import Clock, IdGenerator

SettingsDep = Annotated[Settings, Depends(get_settings)]


# --- port 的 provider(測試逐一覆寫的就是這些) ---


def get_media_uow(request: Request) -> MediaUnitOfWork:
    return request.app.state.uow_factory()


def get_device_directory(request: Request) -> DeviceDirectory:
    return request.app.state.device_directory


def get_event_source(request: Request) -> EventSource:
    return request.app.state.event_source


def get_frame_source(request: Request) -> FrameSource:
    return request.app.state.frame_source


def get_clip_worker(request: Request) -> ClipWorker:
    return request.app.state.clip_worker


def get_media_storage(request: Request) -> MediaStorage:
    return request.app.state.media_storage


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_id_generator(request: Request) -> IdGenerator:
    return request.app.state.id_generator


def get_rate_limit_counter(request: Request) -> RateLimitCounter:
    return request.app.state.rate_limit_counter


UowDep = Annotated[MediaUnitOfWork, Depends(get_media_uow)]
ClockDep = Annotated[Clock, Depends(get_clock)]
IdsDep = Annotated[IdGenerator, Depends(get_id_generator)]
StorageDep = Annotated[MediaStorage, Depends(get_media_storage)]
CounterDep = Annotated[RateLimitCounter, Depends(get_rate_limit_counter)]


# --- 限流(審查 #15) ---


async def enforce_screenshot_rate_limit(
    user_id: CurrentUserId, counter: CounterDep, settings: SettingsDep
) -> None:
    limiter = RateLimiter(
        counter,
        limit=settings.screenshot_rate_limit,
        window_seconds=settings.rate_limit_window_seconds,
    )
    await limiter.check(str(user_id), endpoint="screenshot")


async def enforce_clip_rate_limit(
    user_id: CurrentUserId, counter: CounterDep, settings: SettingsDep
) -> None:
    """轉碼比擷幀貴得多,額度更緊。"""
    limiter = RateLimiter(
        counter,
        limit=settings.clip_rate_limit,
        window_seconds=settings.rate_limit_window_seconds,
    )
    await limiter.check(str(user_id), endpoint="clip")


# --- use case 的 provider ---


def get_take_live_screenshot(
    uow: UowDep,
    devices: Annotated[DeviceDirectory, Depends(get_device_directory)],
    frames: Annotated[FrameSource, Depends(get_frame_source)],
    storage: StorageDep,
    clock: ClockDep,
    ids: IdsDep,
) -> TakeLiveScreenshot:
    return TakeLiveScreenshot(uow, devices, frames, storage, clock, ids)


def get_take_event_screenshot(
    uow: UowDep,
    events: Annotated[EventSource, Depends(get_event_source)],
    frames: Annotated[FrameSource, Depends(get_frame_source)],
    storage: StorageDep,
    clock: ClockDep,
    ids: IdsDep,
    settings: SettingsDep,
) -> TakeEventScreenshot:
    return TakeEventScreenshot(
        uow,
        events,
        frames,
        storage,
        clock,
        ids,
        retention=timedelta(days=settings.video_retention_days),
    )


def get_request_clip(
    uow: UowDep,
    events: Annotated[EventSource, Depends(get_event_source)],
    worker: Annotated[ClipWorker, Depends(get_clip_worker)],
    clock: ClockDep,
    ids: IdsDep,
    settings: SettingsDep,
) -> RequestClip:
    return RequestClip(
        uow,
        events,
        worker,
        clock,
        ids,
        retention=timedelta(days=settings.video_retention_days),
    )


def get_get_media_item(uow: UowDep, storage: StorageDep) -> GetMediaItem:
    return GetMediaItem(uow, storage)


def get_complete_media_item(uow: UowDep, clock: ClockDep) -> CompleteMediaItem:
    return CompleteMediaItem(uow, clock)


def get_fail_media_item(uow: UowDep, clock: ClockDep) -> FailMediaItem:
    return FailMediaItem(uow, clock)


def get_expire_stale_processing(
    uow: UowDep, clock: ClockDep, settings: SettingsDep
) -> ExpireStaleProcessing:
    return ExpireStaleProcessing(
        uow, clock, stale_after=timedelta(seconds=settings.processing_stale_after_seconds)
    )
