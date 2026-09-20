"""ListTimeline:08_spec 第 2.1 節的列表、篩選、分頁與縮圖。"""

import uuid
from datetime import timedelta

import pytest

from app.domains.timeline.application.dtos import ListTimelineQuery
from app.domains.timeline.application.use_cases.list_timeline import ListTimeline
from app.domains.timeline.domain.entities import EventStatus
from app.domains.timeline.domain.exceptions import DeviceNotFound
from app.domains.timeline.domain.value_objects import (
    InvalidCursor,
    InvalidDateFilter,
    InvalidPageSize,
)
from app.shared_kernel.errors import ServiceUnavailable
from tests.domains.timeline.builders import ALICE, BOB, DEVICE, STARTED, a_timeline_event, days
from tests.domains.timeline.fakes import (
    FakeDeviceOwnership,
    FakeMediaUrlIssuer,
    FakeTimelineQueries,
)
from tests.fakes import FixedClock

NOW = STARTED + timedelta(hours=1)


@pytest.fixture
def queries() -> FakeTimelineQueries:
    return FakeTimelineQueries()


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
def use_case(queries, ownership, urls, clock) -> ListTimeline:
    return ListTimeline(queries=queries, ownership=ownership, urls=urls, clock=clock)


def a_query(**overrides) -> ListTimelineQuery:
    return ListTimelineQuery(**{"device_id": DEVICE, "requester_id": ALICE, **overrides})


async def test_someone_elses_device_looks_like_it_does_not_exist(use_case):
    """規格審查 #2:非本人一律 404 DEVICE_005,不回 403——403 等於承認 id 存在。"""
    with pytest.raises(DeviceNotFound):
        await use_case.execute(a_query(requester_id=BOB))


async def test_unknown_device_is_also_a_not_found(use_case):
    with pytest.raises(DeviceNotFound):
        await use_case.execute(a_query(device_id=uuid.uuid4()))


async def test_events_are_returned_newest_first(use_case, queries):
    old = a_timeline_event(id=uuid.UUID(int=1), started_at=STARTED - days(1))
    new = a_timeline_event(id=uuid.UUID(int=2), started_at=STARTED)
    queries.given(old, new)

    page = await use_case.execute(a_query())

    assert [item.id for item in page.items] == [new.id, old.id]


async def test_all_three_statuses_are_listed(use_case, queries):
    """07_spec 第 4 節:時間軸要呈現 processing 與 failed 卡片,不只 ready。"""
    for i, status in enumerate(EventStatus, start=1):
        queries.given(a_timeline_event(id=uuid.UUID(int=i), status=status))

    page = await use_case.execute(a_query())

    assert {item.status for item in page.items} == set(EventStatus)


async def test_thumbnail_url_is_issued_for_usable_thumbnails(use_case, queries, urls):
    """規格審查 #3:列表直接夾帶縮圖的 presigned URL,前端才拿得到圖。"""
    event = a_timeline_event()
    queries.given(event)

    page = await use_case.execute(a_query())

    assert page.items[0].thumbnail_url == f"https://r2.example.com/{event.thumbnail_object_key}?signed=1"
    assert urls.issued == [event.thumbnail_object_key]


async def test_expired_thumbnail_has_no_url(use_case, queries, urls, clock):
    """過了 30 天保留期,前端顯示佔位圖示(TIMELINE_004)。"""
    queries.given(a_timeline_event())
    clock.set(STARTED + days(31))

    page = await use_case.execute(a_query())

    assert page.items[0].thumbnail_url is None
    assert urls.issued == []  # 不對已經不存在的物件浪費一次換發


async def test_processing_event_has_no_thumbnail_url(use_case, queries):
    queries.given(a_timeline_event(status=EventStatus.PROCESSING))

    page = await use_case.execute(a_query())

    assert page.items[0].thumbnail_url is None


async def test_paging_does_not_repeat_or_skip(use_case, queries):
    """驗收標準:捲動列表持續載入更舊事件,無重複或遺漏。"""
    for i in range(1, 6):
        queries.given(
            a_timeline_event(id=uuid.UUID(int=i), started_at=STARTED - timedelta(minutes=i))
        )

    first = await use_case.execute(a_query(limit=2))
    second = await use_case.execute(a_query(limit=2, cursor=first.next_cursor))
    third = await use_case.execute(a_query(limit=2, cursor=second.next_cursor))

    seen = [item.id for page in (first, second, third) for item in page.items]
    assert len(seen) == len(set(seen)) == 5
    assert third.next_cursor is None


async def test_events_in_the_same_second_are_not_lost(queries, use_case):
    """同一秒的多筆事件靠 id 決勝,否則分頁會吃掉其中幾筆。"""
    for i in range(1, 4):
        queries.given(a_timeline_event(id=uuid.UUID(int=i), started_at=STARTED))

    first = await use_case.execute(a_query(limit=2))
    second = await use_case.execute(a_query(limit=2, cursor=first.next_cursor))

    seen = [item.id for page in (first, second) for item in page.items]
    assert len(set(seen)) == 3


async def test_single_day_filter_uses_the_requested_timezone(use_case, queries):
    """規格審查 #6:台北的 9/20 不等於 UTC 的 9/20。"""
    # UTC 09-19 16:00 = 台北 09-20 00:00,屬於台北的 9/20
    queries.given(a_timeline_event(id=uuid.UUID(int=1), started_at=STARTED - timedelta(hours=11)))
    # UTC 09-19 15:00 = 台北 09-19 23:00,屬於前一天
    queries.given(a_timeline_event(id=uuid.UUID(int=2), started_at=STARTED - timedelta(hours=12)))

    page = await use_case.execute(a_query(date="2026-09-20", tz="Asia/Taipei"))

    assert [item.id for item in page.items] == [uuid.UUID(int=1)]


async def test_range_filter_uses_unix_timestamps(use_case, queries):
    inside = a_timeline_event(id=uuid.UUID(int=1), started_at=STARTED)
    outside = a_timeline_event(id=uuid.UUID(int=2), started_at=STARTED - days(10))
    queries.given(inside, outside)

    page = await use_case.execute(
        a_query(
            started_from=int((STARTED - days(1)).timestamp()),
            started_to=int((STARTED + days(1)).timestamp()),
        )
    )

    assert [item.id for item in page.items] == [inside.id]


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"limit": 0}, InvalidPageSize),
        ({"limit": 101}, InvalidPageSize),
        ({"cursor": "tampered!!"}, InvalidCursor),
        ({"date": "2026-13-01"}, InvalidDateFilter),
        ({"date": "2026-09-20", "started_from": 1758337200}, InvalidDateFilter),
    ],
)
async def test_bad_input_is_a_user_error(use_case, overrides, error):
    """全部收斂成 VAL_001(400),不能變成 500。"""
    with pytest.raises(error):
        await use_case.execute(a_query(**overrides))


async def test_input_is_validated_before_the_ownership_check(use_case, queries):
    """壞掉的輸入不該先去問 Device 服務——省一次跨服務往返。"""
    with pytest.raises(InvalidPageSize):
        await use_case.execute(a_query(requester_id=BOB, limit=999))


async def test_database_failure_is_not_an_empty_list(use_case, queries):
    """13_ADR 第 4 節:Event 的讀取選一致性,寧可回錯誤也不可顯示假的空結果。"""
    queries.unavailable = ServiceUnavailable()

    with pytest.raises(ServiceUnavailable):
        await use_case.execute(a_query())
