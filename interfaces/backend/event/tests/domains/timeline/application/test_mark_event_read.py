"""MarkEventRead:08_spec 第 2.3 節的已讀標記。"""

import uuid

import pytest

from app.domains.timeline.application.use_cases.mark_event_read import MarkEventRead
from app.domains.timeline.domain.entities import EventStatus
from app.domains.timeline.domain.exceptions import DeviceNotFound, EventNotFound
from tests.domains.timeline.builders import ALICE, BOB, DEVICE, EVENT, a_timeline_event
from tests.domains.timeline.fakes import FakeDeviceOwnership, FakeTimelineUnitOfWork


@pytest.fixture
def uow() -> FakeTimelineUnitOfWork:
    return FakeTimelineUnitOfWork()


@pytest.fixture
def use_case(uow) -> MarkEventRead:
    return MarkEventRead(uow=uow, ownership=FakeDeviceOwnership({DEVICE: ALICE}))


async def test_playing_an_event_marks_it_read(use_case, uow):
    uow.given(a_timeline_event(is_read=False))

    result = await use_case.execute(EVENT, ALICE, is_read=True)

    assert result.is_read is True
    assert (await uow.events.get(EVENT)).is_read is True
    assert uow.commit_count == 1


async def test_it_can_be_marked_unread_again(use_case, uow):
    """規格審查 #10:誤點之後改回未讀。"""
    uow.given(a_timeline_event(is_read=True))

    await use_case.execute(EVENT, ALICE, is_read=False)

    assert (await uow.events.get(EVENT)).is_read is False


async def test_unknown_event_is_not_found(use_case, uow):
    with pytest.raises(EventNotFound):
        await use_case.execute(uuid.uuid4(), ALICE, is_read=True)

    assert uow.commit_count == 0


async def test_someone_elses_event_cannot_be_touched(use_case, uow):
    uow.given(a_timeline_event(is_read=False))

    with pytest.raises(DeviceNotFound):
        await use_case.execute(EVENT, BOB, is_read=True)

    assert uow.commit_count == 0
    assert (await uow.events.get(EVENT)).is_read is False


async def test_only_the_read_flag_is_written(use_case, uow):
    """repository 只保存 is_read,timeline 碰不到 F2 擁有的狀態欄位。"""
    uow.given(a_timeline_event(status=EventStatus.READY, is_read=False))

    await use_case.execute(EVENT, ALICE, is_read=True)

    stored = await uow.events.get(EVENT)
    assert stored.status is EventStatus.READY
    assert stored.video_object_key is not None
