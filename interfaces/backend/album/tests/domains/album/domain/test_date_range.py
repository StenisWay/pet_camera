"""日期篩選值物件:把「使用者說的日期」換算成「資料庫裡的 UTC 區間」。

換算錯一小時,使用者就會在錯的日期分組裡看到自己的照片,所以邊界要逐一釘死。
"""

from datetime import UTC, datetime

import pytest

from app.domains.album.domain.exceptions import InvalidDateFilter
from app.domains.album.domain.value_objects import DateRange
from tests.domains.album.builders import TAIPEI


def utc(year, month, day, hour=0, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_single_day_spans_taipei_midnight_to_midnight():
    """台北 9/20 一整天 = UTC 9/19 16:00 起、9/20 16:00 止(台北是 UTC+8)。"""
    day = DateRange.build(tz=TAIPEI, day="2026-09-20")

    assert day.start == utc(2026, 9, 19, 16, 0)
    assert day.end == utc(2026, 9, 20, 16, 0)


def test_range_upper_bound_includes_the_whole_end_day():
    """to 是「含當日」:上界取隔天 00:00(台北),才不會漏掉當天 23:59 的項目。"""
    period = DateRange.build(tz=TAIPEI, date_from="2026-09-01", date_to="2026-09-07")

    assert period.start == utc(2026, 8, 31, 16, 0)
    assert period.end == utc(2026, 9, 7, 16, 0)


def test_the_same_day_means_different_instants_in_different_zones():
    """時區不是裝飾:同一個 2026-09-20,台北與 UTC 指的是不同的時間區間。"""
    taipei_day = DateRange.build(tz=TAIPEI, day="2026-09-20")
    utc_day = DateRange.build(tz=UTC, day="2026-09-20")

    assert taipei_day.start != utc_day.start


def test_open_ended_range_leaves_the_missing_bound_unset():
    period = DateRange.build(tz=TAIPEI, date_from="2026-09-01")

    assert period.start == utc(2026, 8, 31, 16, 0)
    assert period.end is None


def test_no_filter_at_all_is_an_empty_range():
    period = DateRange.build(tz=TAIPEI)

    assert period.start is None
    assert period.end is None


def test_date_and_range_are_mutually_exclusive():
    with pytest.raises(InvalidDateFilter):
        DateRange.build(tz=TAIPEI, day="2026-09-20", date_to="2026-09-21")


@pytest.mark.parametrize("bad", ["2026/09/20", "20260920", "2026-13-01", "20-09-2026"])
def test_only_strict_iso_dates_are_accepted(bad):
    with pytest.raises(InvalidDateFilter):
        DateRange.build(tz=TAIPEI, day=bad)


def test_same_day_range_is_allowed():
    """from 與 to 同一天是合法的「只看這天」,不該被當成顛倒的區間。"""
    period = DateRange.build(tz=TAIPEI, date_from="2026-09-20", date_to="2026-09-20")

    assert period.start == utc(2026, 9, 19, 16, 0)
    assert period.end == utc(2026, 9, 20, 16, 0)


def test_inverted_range_is_rejected():
    with pytest.raises(InvalidDateFilter):
        DateRange.build(tz=TAIPEI, date_from="2026-09-20", date_to="2026-09-01")
