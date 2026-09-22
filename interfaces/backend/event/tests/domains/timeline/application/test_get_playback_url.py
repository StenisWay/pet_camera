"""GetPlaybackUrl:08_spec 第 2.2 節的播放連結換發。"""

import uuid
from datetime import timedelta

import pytest

from app.domains.timeline.application.use_cases.get_playback_url import GetPlaybackUrl
from app.domains.timeline.domain.entities import EventStatus
from app.domains.timeline.domain.exceptions import (
    DeviceNotFound,
    EventNotFound,
    EventNotReady,
    EventProcessingFailed,
    VideoExpired,
)
from tests.domains.timeline.builders import (
    ALICE,
    BOB,
    DEVICE,
    EVENT,
    STARTED,
    a_timeline_event,
    days,
)
from tests.domains.timeline.fakes import (
    FakeDeviceOwnership,
    FakeMediaUrlIssuer,
    FakeTimelineUnitOfWork,
)
from tests.fakes import FixedClock

NOW = STARTED + timedelta(hours=1)


@pytest.fixture
def uow() -> FakeTimelineUnitOfWork:
    return FakeTimelineUnitOfWork()


@pytest.fixture
def ownership() -> FakeDeviceOwnership:
    return FakeDeviceOwnership({DEVICE: ALICE})


@pytest.fixture
def urls() -> FakeMediaUrlIssuer:
    return FakeMediaUrlIssuer()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def use_case(uow, ownership, urls, clock) -> GetPlaybackUrl:
    return GetPlaybackUrl(uow=uow, ownership=ownership, urls=urls, clock=clock)


async def test_ready_event_gets_a_short_lived_url(use_case, uow, urls):
    event = uow.given(a_timeline_event())

    result = await use_case.execute(EVENT, ALICE)

    assert result.url == f"https://r2.example.com/{event.video_object_key}?signed=1"
    assert urls.issued == [event.video_object_key]


async def test_unknown_event_is_not_found(use_case):
    with pytest.raises(EventNotFound):
        await use_case.execute(uuid.uuid4(), ALICE)


async def test_someone_elses_event_is_not_found_either(use_case, uow):
    """非本人回 404 而不是 403,否則等於確認這個事件存在(規格審查 #2)。"""
    uow.given(a_timeline_event())

    with pytest.raises(DeviceNotFound):
        await use_case.execute(EVENT, BOB)


async def test_processing_event_is_not_ready(use_case, uow):
    uow.given(a_timeline_event(status=EventStatus.PROCESSING))

    with pytest.raises(EventNotReady):
        await use_case.execute(EVENT, ALICE)


async def test_failed_event_has_nothing_to_play(use_case, uow):
    uow.given(a_timeline_event(status=EventStatus.FAILED))

    with pytest.raises(EventProcessingFailed):
        await use_case.execute(EVENT, ALICE)


async def test_expired_video_is_gone(use_case, uow, clock):
    """驗收標準:已過保留期的事件顯示 TIMELINE_002,而不是錯誤畫面。"""
    uow.given(a_timeline_event())
    clock.set(STARTED + days(8))

    with pytest.raises(VideoExpired):
        await use_case.execute(EVENT, ALICE)


async def test_no_url_is_issued_when_playback_is_refused(use_case, uow, urls):
    """被擋下來時不該先去 R2 換發一次 URL。"""
    uow.given(a_timeline_event(status=EventStatus.FAILED))

    with pytest.raises(EventProcessingFailed):
        await use_case.execute(EVENT, ALICE)

    assert urls.issued == []


async def test_reading_does_not_commit(use_case, uow):
    """純讀取不該留下交易痕跡。"""
    uow.given(a_timeline_event())

    await use_case.execute(EVENT, ALICE)

    assert uow.commit_count == 0
