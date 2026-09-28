"""剪輯範圍的業務規則(11_spec 第 2.2 節 + 規格審查 #4、#5、#14)。

完全不碰資料庫、HTTP 或任何框架——這是最快的一層測試。
"""

import pytest

from app.domains.media.domain.entities import MAX_CLIP_SECONDS, ClipRange
from app.domains.media.domain.exceptions import ClipRangeInvalid, ClipTooLong


def test_valid_range_exposes_its_duration():
    """剪輯長度即 media_items.duration_sec(資料模型 §2.4)。"""
    assert ClipRange(start_sec=5, end_sec=20).duration_sec == 15


@pytest.mark.parametrize(
    ("start_sec", "end_sec"),
    [
        (-1, 10),  # 負數
        (10, 10),  # 零長度
        (20, 10),  # 起訖顛倒
    ],
)
def test_invalid_range_is_rejected(start_sec, end_sec):
    """審查 #14:範圍類錯誤回 VAL_001,不是 CLIP_003。"""
    with pytest.raises(ClipRangeInvalid):
        ClipRange(start_sec=start_sec, end_sec=end_sec)


def test_range_longer_than_limit_is_rejected():
    """審查 #4:上限對齊 F2 的單一事件錄影上限 60 秒,CLIP_003 才測得到。"""
    with pytest.raises(ClipTooLong):
        ClipRange(start_sec=0, end_sec=MAX_CLIP_SECONDS + 1)


def test_range_exactly_at_limit_is_allowed():
    """邊界值:剛好 60 秒可以剪。"""
    assert ClipRange(start_sec=0, end_sec=MAX_CLIP_SECONDS).duration_sec == MAX_CLIP_SECONDS


def test_range_beyond_source_length_is_rejected():
    """剪輯來源僅限單一事件影片內的時間範圍(11_spec 第 2.2 節)。"""
    with pytest.raises(ClipRangeInvalid):
        ClipRange(start_sec=30, end_sec=50).ensure_within(source_duration_sec=45)


def test_range_within_source_length_is_accepted():
    ClipRange(start_sec=30, end_sec=45).ensure_within(source_duration_sec=45)
