"""FinishRecording:07_spec 第 3 節的後處理流程與第 3 節邊界案例的重試。"""

from decimal import Decimal

import pytest

from app.domains.detection.application.dtos import FinishRecordingCommand
from app.domains.detection.application.use_cases.finish_recording import FinishRecording
from app.domains.detection.domain.entities import EventStatus
from app.domains.detection.domain.exceptions import UploadFailed
from app.domains.detection.domain.recording import RecordingSession, StopReason
from tests.domains.detection.builders import DEVICE, EVENT, HIGH, at
from tests.domains.detection.fakes import (
    FakeDetectionUnitOfWork,
    FakeMediaUploader,
    FakePushNotifier,
    NoWaitBackoff,
)

VIDEO = b"fake-mp4-bytes"
THUMB = b"fake-jpeg-bytes"


@pytest.fixture
def uow() -> FakeDetectionUnitOfWork:
    return FakeDetectionUnitOfWork()


@pytest.fixture
def uploader() -> FakeMediaUploader:
    return FakeMediaUploader()


@pytest.fixture
def notifier() -> FakePushNotifier:
    return FakePushNotifier()


@pytest.fixture
def backoff() -> NoWaitBackoff:
    return NoWaitBackoff()


@pytest.fixture
def use_case(uow, uploader, backoff, notifier) -> FinishRecording:
    return FinishRecording(uow=uow, uploader=uploader, backoff=backoff, notifier=notifier)


def a_session(peak: Decimal = HIGH) -> RecordingSession:
    session = RecordingSession.start(event_id=EVENT, device_id=DEVICE, at=at(0), score=peak)
    session.observe(at=at(10), score=peak)
    return session


def a_command(
    *, peak: Decimal = HIGH, reason: StopReason = StopReason.SILENCE
) -> FinishRecordingCommand:
    return FinishRecordingCommand(
        session=a_session(peak),
        video=VIDEO,
        thumbnail=THUMB,
        ended_at=at(12),
        stop_reason=reason,
    )


async def test_successful_upload_makes_the_event_ready(use_case, uow):
    """§3.2~3.4:產生檔案 → 上傳 → status = ready。"""
    result = await use_case.execute(a_command(peak=Decimal("0.95")))

    stored = await uow.events.get(EVENT)
    assert stored.status is EventStatus.READY
    assert stored.confidence_score == Decimal("0.95")  # 事件期間最高值
    assert stored.duration_sec == 12
    assert stored.ended_at == at(12)
    assert result.status is EventStatus.READY


async def test_the_event_is_visible_as_processing_before_the_upload_finishes(
    uow, uploader, backoff, notifier
):
    """§3.1:事件先以 processing 寫入,時間軸才看得到「處理中」卡片。

    如果等上傳完成才寫入,60 秒的錄影 + 上傳期間使用者什麼都看不到,
    也就撐不住「事件可見延遲 < 30 秒」的 NFR。
    """
    seen: list[EventStatus | None] = []

    class SpyUploader(FakeMediaUploader):
        async def upload(self, key, data, *, content_type):
            event = await uow.events.get(EVENT)
            seen.append(event.status if event else None)
            await super().upload(key, data, content_type=content_type)

    use_case = FinishRecording(
        uow=uow, uploader=SpyUploader(), backoff=backoff, notifier=notifier
    )
    await use_case.execute(a_command())

    assert seen[0] is EventStatus.PROCESSING


async def test_both_video_and_thumbnail_are_uploaded_with_the_naming_rule(use_case, uploader):
    """01_資料模型 第 3.1 節的 key 規則。"""
    await use_case.execute(a_command())

    assert uploader.uploaded == {
        f"videos/{DEVICE}/2026/09/20/{EVENT}.mp4": VIDEO,
        f"thumbnails/{DEVICE}/2026/09/20/{EVENT}.jpg": THUMB,
    }


async def test_push_is_triggered_only_after_the_event_is_ready(use_case, uow, notifier):
    """§3.6:status = ready 後才觸發推播。

    body 的形狀對應 Push 服務的 EventReadyNotification(push/__init__.py):
    夾帶縮圖 key 與 started_at,但**不夾帶裝置名稱**——那是 Device 的資料,
    由 Push 自己取即時值,使用者剛改過的鏡頭名稱才會反映在通知標題上。
    """
    await use_case.execute(a_command(peak=Decimal("0.95")))

    assert notifier.sent == [
        {
            "device_id": DEVICE,
            "event_id": EVENT,
            "confidence_score": Decimal("0.95"),
            "thumbnail_object_key": f"thumbnails/{DEVICE}/2026/09/20/{EVENT}.jpg",
            "started_at": at(0),
        }
    ]


async def test_upload_is_retried_up_to_three_times(uow, backoff, notifier):
    """§3 邊界案例:重試 3 次,指數退避。第 3 次成功就該是 ready。"""
    uploader = FakeMediaUploader(fail_times=2)
    use_case = FinishRecording(uow=uow, uploader=uploader, backoff=backoff, notifier=notifier)

    await use_case.execute(a_command())

    assert (await uow.events.get(EVENT)).status is EventStatus.READY
    assert backoff.waits == [1, 2]  # 兩次失敗之間各等一次


async def test_event_fails_after_three_failed_attempts(uow, backoff, notifier):
    """§3.5 + §5:全部失敗 → status = failed,前端顯示 EVENT_001。"""
    uploader = FakeMediaUploader(fail_times=99)
    use_case = FinishRecording(uow=uow, uploader=uploader, backoff=backoff, notifier=notifier)

    result = await use_case.execute(a_command())

    stored = await uow.events.get(EVENT)
    assert stored.status is EventStatus.FAILED
    assert stored.video_object_key is None  # 「不建立可播放內容」
    assert result.status is EventStatus.FAILED
    assert uploader.attempts == 3


async def test_failed_upload_does_not_trigger_push(uow, backoff, notifier):
    """沒有東西可看的事件不該送推播。"""
    use_case = FinishRecording(
        uow=uow, uploader=FakeMediaUploader(fail_times=99), backoff=backoff, notifier=notifier
    )

    await use_case.execute(a_command())

    assert notifier.sent == []


async def test_a_failed_event_leaves_no_orphan_objects(uow, backoff, notifier):
    """驗收標準:「上傳失敗時不產生孤兒資料」。

    第一個檔案上傳成功、第二個失敗時,已經送上去的那個要清掉。
    """
    class ThumbnailFailsUploader(FakeMediaUploader):
        async def upload(self, key, data, *, content_type):
            if key.startswith("thumbnails/"):
                raise UploadFailed()
            await super().upload(key, data, content_type=content_type)

    uploader = ThumbnailFailsUploader()
    use_case = FinishRecording(uow=uow, uploader=uploader, backoff=backoff, notifier=notifier)

    await use_case.execute(a_command())

    assert (await uow.events.get(EVENT)).status is EventStatus.FAILED
    assert uploader.deleted  # 已上傳的影片被清掉了


async def test_push_failure_does_not_undo_a_ready_event(uow, uploader, backoff):
    """推播是事件之後的事:Push 掛掉不該讓已經 ready 的事件變成 failed。"""
    use_case = FinishRecording(
        uow=uow, uploader=uploader, backoff=backoff, notifier=FakePushNotifier(fails=True)
    )

    await use_case.execute(a_command())

    assert (await uow.events.get(EVENT)).status is EventStatus.READY


async def test_disconnected_recording_is_marked_partial(use_case, uow):
    """§3 邊界案例:鏡頭斷線 → 仍上傳,但標記 is_partial(EVENT_003)。"""
    await use_case.execute(a_command(reason=StopReason.DISCONNECTED))

    stored = await uow.events.get(EVENT)
    assert stored.status is EventStatus.READY
    assert stored.is_partial is True


@pytest.mark.parametrize("reason", [StopReason.SILENCE, StopReason.MAX_DURATION])
async def test_normal_stop_reasons_produce_a_complete_clip(use_case, uow, reason):
    """正常結束(靜止 5 秒 / 60 秒上限)的片段是完整的,不該顯示 EVENT_003。"""
    await use_case.execute(a_command(reason=reason))

    assert (await uow.events.get(EVENT)).is_partial is False
