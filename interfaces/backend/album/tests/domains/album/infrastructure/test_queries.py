"""AlbumQueries 的整合測試:排序、游標分頁、日期篩選是這一層自己的責任。

標記 integration,需要真實 PostgreSQL(uv run pytest -m integration)。刻意不用
SQLite 代替——tuple 比較的游標與 timestamptz 邊界正是容易被 SQLite 的寬鬆行為蓋掉的地方。
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.domains.album.domain.value_objects import DateRange, PageSize
from app.domains.album.infrastructure.orm import MediaItemRow
from app.domains.album.infrastructure.queries import SqlAlchemyAlbumQueries
from tests.domains.album.builders import TAIPEI, taipei

pytestmark = pytest.mark.integration

OWNER = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
PAGE = PageSize(30)
NO_FILTER = DateRange()


async def given_item(session_factory, *, owner_id=OWNER, captured_at, status="ready"):
    item_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            MediaItemRow(
                id=item_id,
                user_id=owner_id,
                device_id=uuid.uuid4(),
                type="photo",
                object_key=f"media/{owner_id}/{item_id}.jpg",
                status=status,
                captured_at=captured_at,
                drive_export_status="not_exported",
            )
        )
        await session.commit()
    return item_id


@pytest.fixture
async def queries(session_factory):
    async with session_factory() as session:
        yield SqlAlchemyAlbumQueries(session)


async def test_items_are_returned_newest_first(queries, session_factory):
    """12_spec 第 2.1 節:依 captured_at 由新到舊。"""
    old = await given_item(session_factory, captured_at=datetime(2026, 9, 1, 8, tzinfo=UTC))
    new = await given_item(session_factory, captured_at=datetime(2026, 9, 20, 8, tzinfo=UTC))

    page = await queries.list_page(OWNER, cursor=None, page_size=PAGE, date_range=NO_FILTER)

    assert [i.id for i in page.items] == [new, old]


async def test_other_users_items_are_excluded(queries, session_factory):
    mine = await given_item(session_factory, captured_at=datetime(2026, 9, 1, tzinfo=UTC))
    await given_item(
        session_factory, owner_id=uuid.uuid4(), captured_at=datetime(2026, 9, 2, tzinfo=UTC)
    )

    page = await queries.list_page(OWNER, cursor=None, page_size=PAGE, date_range=NO_FILTER)

    assert [i.id for i in page.items] == [mine]


@pytest.mark.parametrize("status", ["processing", "ready", "failed"])
async def test_all_three_statuses_are_returned(queries, session_factory, status):
    """規格審查 #1 的決議:三種 status 都回傳,由前端依 status 決定呈現。"""
    await given_item(
        session_factory, captured_at=datetime(2026, 9, 1, tzinfo=UTC), status=status
    )

    page = await queries.list_page(OWNER, cursor=None, page_size=PAGE, date_range=NO_FILTER)

    assert [i.status for i in page.items] == [status]


async def test_cursor_paging_walks_every_item_exactly_once(queries, session_factory):
    """同一秒保存的項目也不能重複或漏掉——游標是 (captured_at, id) 組合。"""
    same_moment = datetime(2026, 9, 20, 8, tzinfo=UTC)
    expected = {await given_item(session_factory, captured_at=same_moment) for _ in range(5)}

    seen: list[uuid.UUID] = []
    cursor = None
    while True:
        page = await queries.list_page(
            OWNER, cursor=cursor, page_size=PageSize(2), date_range=NO_FILTER
        )
        seen.extend(i.id for i in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert len(seen) == len(set(seen)) == 5
    assert set(seen) == expected


async def test_last_page_has_no_next_cursor(queries, session_factory):
    await given_item(session_factory, captured_at=datetime(2026, 9, 1, tzinfo=UTC))

    page = await queries.list_page(OWNER, cursor=None, page_size=PAGE, date_range=NO_FILTER)

    assert page.next_cursor is None


async def test_single_day_filter_covers_exactly_that_day(queries, session_factory):
    """分組時區是台北(12_spec 第 2.1 節);資料庫存的是 UTC,邊界換算要正確。"""
    wanted = await given_item(session_factory, captured_at=taipei(2026, 9, 20, 23, 59))
    await given_item(session_factory, captured_at=taipei(2026, 9, 21, 0, 0))
    await given_item(session_factory, captured_at=taipei(2026, 9, 19, 23, 59))

    page = await queries.list_page(
        OWNER,
        cursor=None,
        page_size=PAGE,
        date_range=DateRange.build(tz=TAIPEI, day="2026-09-20"),
    )

    assert [i.id for i in page.items] == [wanted]


async def test_day_filter_follows_taipei_not_utc(queries, session_factory):
    """台北 9/21 凌晨 1 點 = UTC 9/20 17:00。用 UTC 分組會把它歸到前一天。"""
    after_midnight = await given_item(session_factory, captured_at=taipei(2026, 9, 21, 1, 0))

    on_the_20th = await queries.list_page(
        OWNER,
        cursor=None,
        page_size=PAGE,
        date_range=DateRange.build(tz=TAIPEI, day="2026-09-20"),
    )
    on_the_21st = await queries.list_page(
        OWNER,
        cursor=None,
        page_size=PAGE,
        date_range=DateRange.build(tz=TAIPEI, day="2026-09-21"),
    )

    assert on_the_20th.items == []
    assert [i.id for i in on_the_21st.items] == [after_midnight]


async def test_range_filter_includes_both_end_days(queries, session_factory):
    """規格審查 #5:起訖日均含,當天 23:59 的項目不可以被漏掉。"""
    first = await given_item(session_factory, captured_at=taipei(2026, 9, 1, 0, 0))
    last = await given_item(session_factory, captured_at=taipei(2026, 9, 7, 23, 59))
    await given_item(session_factory, captured_at=taipei(2026, 9, 8, 0, 1))

    page = await queries.list_page(
        OWNER,
        cursor=None,
        page_size=PAGE,
        date_range=DateRange.build(tz=TAIPEI, date_from="2026-09-01", date_to="2026-09-07"),
    )

    assert {i.id for i in page.items} == {first, last}
