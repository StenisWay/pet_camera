"""推播的業務規則(09_spec 第 2.2、2.3 節)。"""

import uuid

import pytest

from app.domains.notifications.domain.exceptions import InvalidConfidenceScore
from app.domains.notifications.domain.model import DeepLinkTarget, Occurrence
from tests.domains.notifications.builders import DEVICE_ID, EVENT_ID, a_ready_event

IMAGE = "https://r2.example.test/thumb.jpg?signed=1"


# ---- 防洗版(第 2.3 節,審查 #3) ----


@pytest.mark.parametrize(
    ("count", "expected"),
    [(1, Occurrence.FIRST), (2, Occurrence.SECOND), (3, Occurrence.LATER), (50, Occurrence.LATER)],
)
def test_position_in_the_window_decides_the_occurrence(count, expected):
    """INCR 回傳值 1 為首發、2 為合併、3 以上靜默。"""
    assert Occurrence.from_window_count(count) is expected


def test_unknown_window_count_is_treated_as_a_first_occurrence():
    """Redis 連不到時計數窗視為未開始——寧可短暫多推播,不可漏推(13_ADR 第 4 節)。"""
    assert Occurrence.from_window_count(None) is Occurrence.FIRST


def test_later_events_in_the_window_are_silent():
    """驗收:5 分鐘內連續 3 次觸發,第 3 次靜默。"""
    assert a_ready_event().notification_for(Occurrence.LATER, "客廳", IMAGE) is None


# ---- 首發通知的內容(第 2.2 節) ----


def test_first_notification_names_the_device_and_links_to_the_event():
    notification = a_ready_event().notification_for(Occurrence.FIRST, "客廳", IMAGE)

    assert notification.title == "客廳 偵測到活動"
    assert notification.target == DeepLinkTarget(device_id=DEVICE_ID, event_id=EVENT_ID)
    assert notification.image_url == IMAGE


@pytest.mark.parametrize(
    ("score", "description"), [(0.8, "高信心"), (0.99, "高信心"), (0.79, "一般"), (0.6, "一般")]
)
def test_body_describes_confidence_with_a_high_threshold_of_0_8(score, description):
    """審查 #7:>= 0.8 為高信心,否則為一般。"""
    notification = a_ready_event(confidence_score=score).notification_for(
        Occurrence.FIRST, "客廳", IMAGE
    )

    assert notification.body == description


# ---- 合併通知(審查 #3、#14) ----


def test_second_notification_is_a_digest_pointing_at_the_camera():
    """合併通知不指向單一事件,改導向該裝置的攝影機畫面;不顯示精確次數。"""
    notification = a_ready_event().notification_for(Occurrence.SECOND, "客廳", IMAGE)

    assert notification.title == "客廳 偵測到活動"
    assert notification.body == "偵測到多次活動"
    assert notification.target == DeepLinkTarget(device_id=DEVICE_ID, event_id=None)
    assert notification.image_url is None


# ---- 輸入的業務檢查 ----


@pytest.mark.parametrize("score", [-0.1, 1.01])
def test_confidence_score_outside_0_to_1_is_rejected(score):
    with pytest.raises(InvalidConfidenceScore):
        a_ready_event(confidence_score=score)


def test_only_this_devices_thumbnail_may_be_signed():
    """內部端點帶來的 object key 只接受 thumbnails/{device_id}/ 底下的——
    否則一個被攻破的呼叫端就能讓本服務替任意 R2 物件簽出連結。"""
    other = uuid.uuid4()

    assert a_ready_event().signable_thumbnail_key is not None
    assert a_ready_event(thumbnail_object_key=f"media/{other}/x.jpg").signable_thumbnail_key is None
    assert (
        a_ready_event(
            thumbnail_object_key=f"thumbnails/{other}/2026/09/20/x.jpg"
        ).signable_thumbnail_key
        is None
    )
    assert (
        a_ready_event(
            thumbnail_object_key=f"thumbnails/{DEVICE_ID}/../{other}/x.jpg"
        ).signable_thumbnail_key
        is None
    )
    assert a_ready_event(thumbnail_object_key=None).signable_thumbnail_key is None
