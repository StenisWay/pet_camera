"""POST /internal/notifications/event-ready 背後的流程(09_spec 第 2 節)。"""

import uuid

import pytest

from app.domains.notifications.application.ports import (
    Channel,
    DeliveryResult,
    DeviceInfo,
    Recipient,
)
from app.domains.notifications.application.use_cases.notify_event_ready import DispatchStatus
from app.domains.notifications.domain.model import DeepLinkTarget
from tests.domains.notifications.builders import (
    DEVICE_ID,
    EVENT_ID,
    OWNER,
    THUMBNAIL_KEY,
    a_ready_event,
)

PHONE = Recipient(id=uuid.UUID(int=101), channel=Channel.APP, token="fcm-1")
BROWSER = Recipient(id=uuid.UUID(int=102), channel=Channel.WEB, token='{"endpoint": "x"}')


@pytest.fixture(autouse=True)
def owned_device_with_two_endpoints(devices, recipients):
    devices.given(DeviceInfo(id=DEVICE_ID, name="客廳", owner_id=OWNER))
    recipients.given(OWNER, PHONE, BROWSER)


async def test_first_event_is_pushed_to_every_endpoint_of_the_owner(use_case, gateway):
    report = await use_case.execute(a_ready_event())

    assert report.status is DispatchStatus.SENT
    assert [r for r, _ in gateway.sent] == [PHONE, BROWSER]
    notification = gateway.sent[0][1]
    assert notification.title == "客廳 偵測到活動"
    assert notification.target == DeepLinkTarget(device_id=DEVICE_ID, event_id=EVENT_ID)


async def test_notification_carries_a_presigned_thumbnail(use_case, gateway, thumbnails):
    """第 2.2 節附圖;效期 30 分鐘由 ThumbnailLinks 的實作負責(審查 #6)。"""
    await use_case.execute(a_ready_event())

    assert thumbnails.signed == [THUMBNAIL_KEY]
    assert gateway.sent[0][1].image_url.startswith("https://r2.example.test/thumbnails/")


async def test_device_name_is_read_at_send_time(use_case, devices, gateway):
    """審查 #2:使用者剛改過的鏡頭名稱要立刻反映在通知標題上。"""
    devices.given(DeviceInfo(id=DEVICE_ID, name="臥室", owner_id=OWNER))

    await use_case.execute(a_ready_event())

    assert gateway.sent[0][1].title == "臥室 偵測到活動"


async def test_unpaired_device_is_discarded_without_touching_the_window(
    use_case, devices, window, gateway
):
    """審查 #13 / 驗收:已解除配對的裝置產生的事件不觸發任何推播,也不算錯誤。"""
    devices.given(DeviceInfo(id=DEVICE_ID, name="客廳", owner_id=None))

    report = await use_case.execute(a_ready_event())

    assert report.status is DispatchStatus.DEVICE_UNOWNED
    assert gateway.sent == []
    assert window.counts == {}


async def test_unknown_device_is_discarded(use_case, gateway):
    report = await use_case.execute(a_ready_event(device_id=uuid.uuid4()))

    assert report.status is DispatchStatus.DEVICE_UNOWNED
    assert gateway.sent == []


async def test_three_events_in_a_window_give_one_push_and_one_digest(use_case, gateway):
    """驗收:5 分鐘內連續 3 次觸發,只收到 1 次首發 + 1 次合併通知(第 3 次靜默)。"""
    await use_case.execute(a_ready_event(event_id=uuid.uuid4()))
    await use_case.execute(a_ready_event(event_id=uuid.uuid4()))
    third = await use_case.execute(a_ready_event(event_id=uuid.uuid4()))

    bodies = [n.body for r, n in gateway.sent if r == PHONE]
    assert bodies == ["高信心", "偵測到多次活動"]
    assert third.status is DispatchStatus.SILENCED


async def test_digest_does_not_sign_a_thumbnail(use_case, thumbnails):
    await use_case.execute(a_ready_event(event_id=uuid.uuid4()))
    await use_case.execute(a_ready_event(event_id=uuid.uuid4()))

    assert len(thumbnails.signed) == 1


async def test_window_restarts_after_it_expires(use_case, window, gateway):
    """第 2.3 節:時間窗結束後有新事件重新開始計算。"""
    for _ in range(3):
        await use_case.execute(a_ready_event(event_id=uuid.uuid4()))
    window.expire(DEVICE_ID)
    gateway.sent.clear()

    await use_case.execute(a_ready_event(event_id=uuid.uuid4()))

    assert [n.body for _, n in gateway.sent] == ["高信心", "高信心"]


async def test_windows_are_per_device(use_case, devices, recipients, gateway):
    other_device = devices.given(DeviceInfo(id=uuid.uuid4(), name="陽台", owner_id=OWNER))
    await use_case.execute(a_ready_event())

    await use_case.execute(
        a_ready_event(device_id=other_device.id, thumbnail_object_key=None, event_id=uuid.uuid4())
    )

    assert [n.title for r, n in gateway.sent if r == PHONE] == [
        "客廳 偵測到活動",
        "陽台 偵測到活動",
    ]


async def test_window_outage_pushes_every_event(use_case, window, gateway):
    """13_ADR 第 4 節:計數窗連不到 → 寧可短暫多推播,不可漏推。"""
    window.available = False

    for _ in range(3):
        await use_case.execute(a_ready_event(event_id=uuid.uuid4()))

    assert [n.body for r, n in gateway.sent if r == PHONE] == ["高信心"] * 3


async def test_owner_without_endpoints_is_a_quiet_no_op(use_case, recipients, gateway):
    recipients.by_user.clear()

    report = await use_case.execute(a_ready_event())

    assert report.status is DispatchStatus.NO_RECIPIENTS
    assert gateway.sent == []


async def test_gone_endpoint_is_removed_and_others_still_receive(use_case, recipients, gateway):
    """第 2.5 節 / PUSH_003:刪除失效端點,不影響同一次通知對其他端點的發送。"""
    gateway.results[PHONE.id] = DeliveryResult.ENDPOINT_GONE

    report = await use_case.execute(a_ready_event())

    assert recipients.removed == [PHONE.id]
    assert [r for r, _ in gateway.sent] == [BROWSER]
    assert report.delivered == 1
    assert report.removed_endpoints == 1


async def test_transient_send_failure_keeps_the_endpoint(use_case, recipients, gateway):
    """逾時或 5xx 不代表端點失效,刪掉會讓使用者從此收不到通知。"""
    gateway.raising.add(PHONE.id)
    gateway.results[BROWSER.id] = DeliveryResult.FAILED

    report = await use_case.execute(a_ready_event())

    assert recipients.removed == []
    assert report.delivered == 0


async def test_failure_to_remove_a_gone_endpoint_does_not_stop_the_others(
    use_case, recipients, gateway
):
    gateway.results[PHONE.id] = DeliveryResult.ENDPOINT_GONE
    recipients.fail_remove = True

    report = await use_case.execute(a_ready_event())

    assert [r for r, _ in gateway.sent] == [BROWSER]
    assert report.removed_endpoints == 0


async def test_device_lookup_is_retried_on_transient_failure(use_case, devices, gateway):
    """13_ADR 第 4 節:發送路徑選可用性,延後重試而不是立即失敗。"""
    devices.failures_before_success = 2

    report = await use_case.execute(a_ready_event())

    assert report.status is DispatchStatus.SENT
    assert devices.calls == 3


async def test_endpoint_lookup_is_retried_on_transient_failure(use_case, recipients):
    recipients.failures_before_success = 1

    report = await use_case.execute(a_ready_event())

    assert report.status is DispatchStatus.SENT


async def test_gives_up_quietly_after_the_retries_are_exhausted(use_case, devices, gateway, caplog):
    """背景任務沒有人等結果:放棄時要留下 ERROR 紀錄,但不可把例外往外丟。"""
    devices.failures_before_success = 99

    with caplog.at_level("ERROR"):
        report = await use_case.execute(a_ready_event())

    assert report.status is DispatchStatus.GAVE_UP
    assert devices.calls == 3  # 第一次 + 兩次重試
    assert gateway.sent == []
    assert str(EVENT_ID) in caplog.text


async def test_thumbnail_signing_failure_still_sends_without_image(use_case, thumbnails, gateway):
    thumbnails.available = False

    await use_case.execute(a_ready_event())

    assert len(gateway.sent) == 2
    assert gateway.sent[0][1].image_url is None


async def test_foreign_thumbnail_key_is_never_signed(use_case, thumbnails, gateway):
    await use_case.execute(a_ready_event(thumbnail_object_key="media/someone/else.jpg"))

    assert thumbnails.signed == []
    assert gateway.sent[0][1].image_url is None
