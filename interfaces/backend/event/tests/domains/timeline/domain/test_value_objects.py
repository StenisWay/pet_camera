"""把外部輸入轉成內部安全的形狀:游標、分頁上限、日期區間(08_spec 第 2.1 節)。"""

from datetime import UTC, datetime

import pytest

from app.domains.timeline.domain.value_objects import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    DateRange,
    InvalidCursor,
    InvalidDateFilter,
    InvalidPageSize,
    PageSize,
    TimelineCursor,
)
from tests.domains.timeline.builders import EVENT, STARTED

# --- 游標 ---------------------------------------------------------------


def test_cursor_round_trips():
    cursor = TimelineCursor(started_at=STARTED, event_id=EVENT)

    assert TimelineCursor.decode(cursor.encode()) == cursor


def test_cursor_keeps_sub_second_precision():
    """同一秒內的多筆事件靠微秒 + id 區分,精度掉了就會重複或遺漏。"""
    precise = STARTED.replace(microsecond=123456)
    cursor = TimelineCursor(started_at=precise, event_id=EVENT)

    assert TimelineCursor.decode(cursor.encode()).started_at == precise


def test_cursor_is_opaque():
    """游標不該讓前端看出內部欄位,否則它會開始自己組游標。"""
    encoded = TimelineCursor(started_at=STARTED, event_id=EVENT).encode()

    assert str(EVENT) not in encoded
    assert "2026" not in encoded


@pytest.mark.parametrize("value", ["", "not-base64!!", "YWJj", "%%%"])
def test_tampered_cursor_is_a_user_error_not_a_crash(value):
    """竄改的游標是 VAL_001(400),不能變成 500。"""
    with pytest.raises(InvalidCursor):
        TimelineCursor.decode(value)


# --- 分頁上限 -----------------------------------------------------------


def test_default_page_size():
    assert PageSize.of(None).value == DEFAULT_PAGE_SIZE == 20


@pytest.mark.parametrize("limit", [1, 20, MAX_PAGE_SIZE])
def test_page_size_within_range_is_accepted(limit):
    assert PageSize.of(limit).value == limit


@pytest.mark.parametrize("limit", [0, -1, MAX_PAGE_SIZE + 1])
def test_page_size_out_of_range_is_rejected(limit):
    """上限 100:沒有上限的 limit 會讓單一請求拖垮 VM-3。"""
    with pytest.raises(InvalidPageSize):
        PageSize.of(limit)


# --- 日期區間 -----------------------------------------------------------


def test_no_filter_means_no_bounds():
    assert DateRange.resolve() == DateRange(None, None)


def test_single_day_is_resolved_in_the_requested_timezone():
    """台北的 9/20 是 UTC 的 9/19 16:00 ~ 9/20 16:00。

    不換算時區的話,傍晚之後的事件會被歸到隔天(規格審查 #6)。
    """
    range_ = DateRange.resolve(date="2026-09-20", tz="Asia/Taipei")

    assert range_.started_from == datetime(2026, 9, 19, 16, 0, tzinfo=UTC)
    assert range_.started_to == datetime(2026, 9, 20, 16, 0, tzinfo=UTC)


def test_single_day_defaults_to_taipei():
    assert DateRange.resolve(date="2026-09-20") == DateRange.resolve(
        date="2026-09-20", tz="Asia/Taipei"
    )


def test_utc_day_is_a_different_window():
    range_ = DateRange.resolve(date="2026-09-20", tz="UTC")

    assert range_.started_from == datetime(2026, 9, 20, 0, 0, tzinfo=UTC)


def test_range_filter_uses_unix_timestamps():
    """區間篩選走 from/to(Unix timestamp,秒),供 Web 版「過去一個月」使用。"""
    range_ = DateRange.resolve(started_from=1758337200, started_to=1758423600)

    assert range_.started_from == datetime.fromtimestamp(1758337200, tz=UTC)
    assert range_.started_to == datetime.fromtimestamp(1758423600, tz=UTC)


def test_date_and_range_are_mutually_exclusive():
    with pytest.raises(InvalidDateFilter):
        DateRange.resolve(date="2026-09-20", started_from=1758337200)


@pytest.mark.parametrize("date", ["2026-13-01", "20260920", "not-a-date", "2026-09-31"])
def test_malformed_date_is_rejected(date):
    with pytest.raises(InvalidDateFilter):
        DateRange.resolve(date=date)


def test_unknown_timezone_is_rejected():
    with pytest.raises(InvalidDateFilter):
        DateRange.resolve(date="2026-09-20", tz="Mars/Olympus")


def test_reversed_range_is_rejected():
    """to 早於 from 只會回空列表,對使用者來說是無聲的錯誤,不如直接擋下。"""
    with pytest.raises(InvalidDateFilter):
        DateRange.resolve(started_from=1758423600, started_to=1758337200)


@pytest.mark.parametrize("value", [10**20, -(10**20)])
def test_out_of_range_timestamps_are_rejected(value):
    """超出 datetime 可表示範圍的 timestamp 是輸入錯誤(400),不是 500。"""
    with pytest.raises(InvalidDateFilter):
        DateRange.resolve(started_from=value)
