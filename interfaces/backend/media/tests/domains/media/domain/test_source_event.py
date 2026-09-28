"""來源事件能不能當剪輯/截圖的素材(規格審查 #7、#8、#13)。"""

from datetime import timedelta

import pytest

from app.domains.media.domain.exceptions import (
    ClipRangeInvalid,
    ClipSourceExpired,
    ClipSourceNotReady,
    MediaItemNotFound,
)
from tests.domains.media.builders import NOW, OTHER_USER, OWNER, an_event

RETENTION = timedelta(days=7)


def test_event_is_owned_by_its_owner_only():
    """IDOR:events 表沒有 user_id,擁有者由 Event 服務的內部端點提供(審查 #7)。"""
    event = an_event(owner_id=OWNER)

    assert event.is_owned_by(OWNER)
    assert not event.is_owned_by(OTHER_USER)


def test_other_users_event_is_reported_as_not_found():
    """審查 #6:不可洩漏資源存在性,非本人與不存在回同一個例外。"""
    event = an_event(owner_id=OTHER_USER)

    with pytest.raises(MediaItemNotFound):
        event.ensure_usable_by(OWNER, now=NOW, retention=RETENTION)


@pytest.mark.parametrize("status", ["processing", "failed"])
def test_event_without_ready_video_cannot_be_used(status):
    """11_spec 第 2.2 節(剪輯)+ 審查 #13(回放截圖套用同一條)。"""
    event = an_event(status=status)

    with pytest.raises(ClipSourceNotReady):
        event.ensure_usable_by(OWNER, now=NOW, retention=RETENTION)


def test_event_older_than_retention_is_expired():
    """審查 #8:以 started_at + 7 天在 DB 層判定,不為了這件事多打一次 R2。

    資料模型 §3.2:影片過期後 events 紀錄仍保留、video_object_key 不清空,
    所以「檔案還在不在」無法從資料列本身看出來。
    """
    event = an_event(started_at=NOW - RETENTION - timedelta(seconds=1))

    with pytest.raises(ClipSourceExpired):
        event.ensure_usable_by(OWNER, now=NOW, retention=RETENTION)


def test_event_just_inside_retention_is_still_usable():
    """邊界值:剛好在保留期內仍可剪輯。"""
    event = an_event(started_at=NOW - RETENTION + timedelta(seconds=1))

    event.ensure_usable_by(OWNER, now=NOW, retention=RETENTION)


@pytest.mark.parametrize("offset_sec", [-1, 46])
def test_offset_outside_the_video_is_rejected(offset_sec):
    """審查 #5:截圖時間點須落在 0..duration_sec 之間。"""
    with pytest.raises(ClipRangeInvalid):
        an_event(duration_sec=45).ensure_covers(offset_sec)


@pytest.mark.parametrize("offset_sec", [0, 45])
def test_offset_at_the_boundaries_is_accepted(offset_sec):
    """邊界值:第一秒與最後一秒都可以截。"""
    an_event(duration_sec=45).ensure_covers(offset_sec)
