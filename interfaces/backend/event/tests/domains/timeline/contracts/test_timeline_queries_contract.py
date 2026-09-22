"""TimelineQueries 與 TimelineEventRepository 的行為承諾,每個實作都要通過。

分頁是這個讀取端最容易出錯的地方,而錯法(重複、遺漏)在 fake 上很容易「剛好對」。
把同一份測試也跑在 SQLAlchemy 上,才敢用 fake 去測 application。

開發時 `pytest -m "not integration"` 只跑 fake;CI 兩個實作都跑。
"""

import uuid
from collections.abc import Callable
from datetime import timedelta

import pytest

from app.domains.timeline.application.ports import TimelineQueries, TimelineUnitOfWork
from app.domains.timeline.domain.entities import TimelineEvent
from app.domains.timeline.domain.value_objects import DateRange, PageSize
from tests.domains.timeline.builders import DEVICE, STARTED, a_timeline_event
from tests.domains.timeline.fakes import FakeTimelineQueries, FakeTimelineUnitOfWork

QueriesFactory = Callable[[], TimelineQueries]
UowFactory = Callable[[], TimelineUnitOfWork]

ALL_TIME = DateRange(None, None)
OTHER_DEVICE = uuid.UUID("00000000-0000-0000-0000-0000000000d9")


@pytest.fixture(params=["fake", pytest.param("sqlalchemy", marks=pytest.mark.integration)])
def backend(request):
    """回傳 (seed, queries_factory, uow_factory) 三件套,兩個實作共用同一份測試。"""
    if request.param == "fake":
        store: dict[uuid.UUID, TimelineEvent] = {}
        queries = FakeTimelineQueries()

        def seed(*events: TimelineEvent) -> None:
            queries.given(*events)
            for event in events:
                store[event.id] = event

        return seed, (lambda: queries), (lambda: FakeTimelineUnitOfWork(store))

    from app.domains.detection.domain.entities import Event, UploadedMedia
    from app.domains.detection.infrastructure.unit_of_work import (
        SqlAlchemyDetectionUnitOfWork,
    )
    from app.domains.timeline.infrastructure.queries import SqlAlchemyTimelineQueries
    from app.domains.timeline.infrastructure.unit_of_work import (
        SqlAlchemyTimelineUnitOfWork,
    )

    session_factory = request.getfixturevalue("session_factory")

    def seed(*events: TimelineEvent) -> None:
        """timeline 不建立事件(那是 detection 的職責),所以用 detection 的寫入側鋪資料。"""
        import asyncio

        async def _write() -> None:
            async with SqlAlchemyDetectionUnitOfWork(session_factory) as uow:
                for view in events:
                    event = Event.begin(
                        id=view.id, device_id=view.device_id, started_at=view.started_at
                    )
                    if view.video_object_key:
                        event.mark_ready(
                            UploadedMedia(
                                video_object_key=view.video_object_key,
                                thumbnail_object_key=view.thumbnail_object_key,
                                confidence_score=view.confidence_score,
                                duration_sec=view.duration_sec,
                                ended_at=view.ended_at,
                                is_partial=view.is_partial,
                            )
                        )
                    await uow.events.save(event)
                await uow.commit()

        asyncio.get_event_loop().run_until_complete(_write())

    return (
        seed,
        (lambda: SqlAlchemyTimelineQueries(session_factory)),
        (lambda: SqlAlchemyTimelineUnitOfWork(session_factory)),
    )


async def page_of(queries: TimelineQueries, *, limit: int = 20, cursor=None):
    return await queries.list_by_device(
        DEVICE, cursor=cursor, page_size=PageSize(limit), date_range=ALL_TIME
    )


async def test_empty_device_returns_an_empty_page(backend):
    _, queries_factory, _ = backend

    page = await page_of(queries_factory())

    assert page.items == []
    assert page.next_cursor is None


async def test_events_come_back_newest_first(backend):
    seed, queries_factory, _ = backend
    seed(
        a_timeline_event(id=uuid.UUID(int=1), started_at=STARTED - timedelta(minutes=5)),
        a_timeline_event(id=uuid.UUID(int=2), started_at=STARTED),
    )

    page = await page_of(queries_factory())

    assert [item.id for item in page.items] == [uuid.UUID(int=2), uuid.UUID(int=1)]


async def test_other_devices_are_not_included(backend):
    seed, queries_factory, _ = backend
    seed(
        a_timeline_event(id=uuid.UUID(int=1)),
        a_timeline_event(id=uuid.UUID(int=2), device_id=OTHER_DEVICE),
    )

    page = await page_of(queries_factory())

    assert [item.id for item in page.items] == [uuid.UUID(int=1)]


async def test_next_cursor_is_none_on_the_last_page(backend):
    seed, queries_factory, _ = backend
    seed(a_timeline_event(id=uuid.UUID(int=1)))

    page = await page_of(queries_factory(), limit=20)

    assert page.next_cursor is None


async def test_next_cursor_is_set_when_more_rows_exist(backend):
    seed, queries_factory, _ = backend
    seed(*[a_timeline_event(id=uuid.UUID(int=i)) for i in range(1, 4)])

    page = await page_of(queries_factory(), limit=2)

    assert len(page.items) == 2
    assert page.next_cursor is not None


async def test_paging_covers_every_row_exactly_once(backend):
    """驗收標準:捲動列表持續載入更舊事件,無重複或遺漏。"""
    seed, queries_factory, _ = backend
    seed(
        *[
            a_timeline_event(id=uuid.UUID(int=i), started_at=STARTED - timedelta(minutes=i))
            for i in range(1, 8)
        ]
    )

    seen: list[uuid.UUID] = []
    cursor = None
    for _ in range(5):
        page = await page_of(queries_factory(), limit=3, cursor=cursor)
        seen.extend(item.id for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert len(seen) == len(set(seen)) == 7


async def test_rows_sharing_a_timestamp_are_still_paged_correctly(backend):
    """同一秒的多筆事件靠 id 決勝;只比時間的話,分頁會吃掉其中幾筆。"""
    seed, queries_factory, _ = backend
    seed(*[a_timeline_event(id=uuid.UUID(int=i), started_at=STARTED) for i in range(1, 6)])

    seen: list[uuid.UUID] = []
    cursor = None
    for _ in range(5):
        page = await page_of(queries_factory(), limit=2, cursor=cursor)
        seen.extend(item.id for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert len(seen) == len(set(seen)) == 5


async def test_date_range_filters_by_started_at(backend):
    seed, queries_factory, _ = backend
    seed(
        a_timeline_event(id=uuid.UUID(int=1), started_at=STARTED),
        a_timeline_event(id=uuid.UUID(int=2), started_at=STARTED - timedelta(days=3)),
    )

    page = await queries_factory().list_by_device(
        DEVICE,
        cursor=None,
        page_size=PageSize(20),
        date_range=DateRange(STARTED - timedelta(days=1), STARTED + timedelta(days=1)),
    )

    assert [item.id for item in page.items] == [uuid.UUID(int=1)]


async def test_the_upper_bound_of_a_date_range_is_exclusive(backend):
    """單日查詢的上界是隔天 00:00,含進去的話那一天的第一筆會出現在前一天。"""
    seed, queries_factory, _ = backend
    seed(a_timeline_event(id=uuid.UUID(int=1), started_at=STARTED))

    page = await queries_factory().list_by_device(
        DEVICE,
        cursor=None,
        page_size=PageSize(20),
        date_range=DateRange(STARTED - timedelta(days=1), STARTED),
    )

    assert page.items == []


async def test_getting_an_unknown_event_returns_none(backend):
    _, _, uow_factory = backend

    async with uow_factory() as uow:
        assert await uow.events.get(uuid.uuid4()) is None


async def test_read_state_is_persisted_after_commit(backend):
    seed, _, uow_factory = backend
    event = a_timeline_event(id=uuid.UUID(int=1), is_read=False)
    seed(event)

    async with uow_factory() as uow:
        loaded = await uow.events.get(event.id)
        loaded.mark_read(True)
        await uow.events.save_read_state(loaded)
        await uow.commit()

    async with uow_factory() as uow:
        assert (await uow.events.get(event.id)).is_read is True


async def test_read_state_without_commit_is_rolled_back(backend):
    seed, _, uow_factory = backend
    event = a_timeline_event(id=uuid.UUID(int=1), is_read=False)
    seed(event)

    async with uow_factory() as uow:
        loaded = await uow.events.get(event.id)
        loaded.mark_read(True)
        await uow.events.save_read_state(loaded)

    async with uow_factory() as uow:
        assert (await uow.events.get(event.id)).is_read is False


async def test_saving_read_state_does_not_touch_the_event_lifecycle(backend):
    """timeline 只擁有 is_read;status 與 object key 屬於 detection,不可被覆寫。"""
    seed, _, uow_factory = backend
    event = a_timeline_event(id=uuid.UUID(int=1))
    seed(event)

    async with uow_factory() as uow:
        loaded = await uow.events.get(event.id)
        loaded.status = "processing"  # 就算有人這樣亂改
        loaded.video_object_key = None
        loaded.mark_read(True)
        await uow.events.save_read_state(loaded)
        await uow.commit()

    async with uow_factory() as uow:
        stored = await uow.events.get(event.id)

    assert stored.status == event.status
    assert stored.video_object_key == event.video_object_key
