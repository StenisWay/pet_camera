import uuid

import pytest

from app.domains.album.application.dtos import ListAlbumQuery
from app.domains.album.application.use_cases.list_album import ListAlbum
from app.domains.album.domain.exceptions import InvalidDateFilter, InvalidPageSize
from tests.domains.album.builders import OWNER, TAIPEI, an_item, taipei


@pytest.fixture
def use_case(queries) -> ListAlbum:
    return ListAlbum(queries, default_page_size=30, max_page_size=100, timezone=TAIPEI)


async def test_lists_only_the_requesting_users_items(use_case, uow):
    mine = uow.given(an_item(owner_id=OWNER))
    uow.given(an_item(owner_id=uuid.uuid4()))

    page = await use_case.execute(ListAlbumQuery(owner_id=OWNER))

    assert [i.id for i in page.items] == [mine.id]


async def test_date_and_range_filters_are_mutually_exclusive(use_case):
    """規格審查 #5:date(App 單日)與 from/to(Web 區間)不可同時使用。"""
    with pytest.raises(InvalidDateFilter):
        await use_case.execute(
            ListAlbumQuery(owner_id=OWNER, date="2026-09-20", date_from="2026-09-01")
        )


@pytest.mark.parametrize("bad", ["2026/09/20", "20260920", "2026-13-01", "yesterday"])
async def test_malformed_date_is_rejected(use_case, bad):
    """日期一律 YYYY-MM-DD。"""
    with pytest.raises(InvalidDateFilter):
        await use_case.execute(ListAlbumQuery(owner_id=OWNER, date=bad))


async def test_blank_date_is_treated_as_no_filter(use_case, queries):
    """Web 端清空篩選欄時送出的是 ?date=,那是「不篩選」,不是格式錯誤。"""
    await use_case.execute(ListAlbumQuery(owner_id=OWNER, date="", date_from="  "))

    assert queries.last_call["date_range"].start is None


async def test_inverted_range_is_rejected(use_case):
    with pytest.raises(InvalidDateFilter):
        await use_case.execute(
            ListAlbumQuery(owner_id=OWNER, date_from="2026-09-20", date_to="2026-09-01")
        )


async def test_range_filter_includes_both_end_days(use_case, uow):
    """規格審查 #5:起訖日均含——當天(台北時間)23:59 保存的項目不可以被漏掉。"""
    first = uow.given(an_item(captured_at=taipei(2026, 9, 1, 0, 0)))
    last = uow.given(an_item(captured_at=taipei(2026, 9, 7, 23, 59)))
    uow.given(an_item(captured_at=taipei(2026, 9, 8, 0, 1)))

    page = await use_case.execute(
        ListAlbumQuery(owner_id=OWNER, date_from="2026-09-01", date_to="2026-09-07")
    )

    assert {i.id for i in page.items} == {first.id, last.id}


async def test_limit_is_clamped_to_max_page_size(use_case, queries):
    await use_case.execute(ListAlbumQuery(owner_id=OWNER, limit=10_000))

    assert queries.last_call["page_size"].value == 100


async def test_missing_limit_uses_the_default(use_case, queries):
    await use_case.execute(ListAlbumQuery(owner_id=OWNER))

    assert queries.last_call["page_size"].value == 30


@pytest.mark.parametrize("bad", [0, -1])
async def test_non_positive_limit_is_rejected(use_case, bad):
    """limit=0 不可以被靜默當成「沒給」而變成預設值。"""
    with pytest.raises(InvalidPageSize):
        await use_case.execute(ListAlbumQuery(owner_id=OWNER, limit=bad))


async def test_single_day_filter_covers_exactly_that_day(use_case, uow):
    """規格審查 #5:App 端的 date= 是單日篩選,跨過午夜的項目不算在內。"""
    wanted = uow.given(an_item(captured_at=taipei(2026, 9, 20, 23, 59)))
    uow.given(an_item(captured_at=taipei(2026, 9, 21, 0, 0)))
    uow.given(an_item(captured_at=taipei(2026, 9, 19, 23, 59)))

    page = await use_case.execute(ListAlbumQuery(owner_id=OWNER, date="2026-09-20"))

    assert [i.id for i in page.items] == [wanted.id]


async def test_day_grouping_follows_taipei_time_not_utc(use_case, uow):
    """12_spec 第 2.1 節:依日期分組用台北時間。

    台北 9/21 凌晨 1 點拍的照片,在 UTC 還是 9/20 17:00——如果用 UTC 分組,
    使用者會在「9月20日」那一組看到自己半夜拍的東西,日期整個跑掉。
    """
    after_midnight_in_taipei = uow.given(an_item(captured_at=taipei(2026, 9, 21, 1, 0)))

    on_the_20th = await use_case.execute(ListAlbumQuery(owner_id=OWNER, date="2026-09-20"))
    on_the_21st = await use_case.execute(ListAlbumQuery(owner_id=OWNER, date="2026-09-21"))

    assert on_the_20th.items == []
    assert [i.id for i in on_the_21st.items] == [after_midnight_in_taipei.id]
