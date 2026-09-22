"""DetectMotion:把影格串流變成事件。07_spec 第 2 節與第 6 節驗收標準。

影像解碼與 ffmpeg 是 adapter 的事,這裡用假的影格來源驗證錄影的**業務規則**:
什麼時候開始、什麼算同一個事件、什麼時候結束。
"""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest

from app.domains.detection.application.dtos import EncodedClip
from app.domains.detection.application.ports import ClipEncoder, FrameSource
from app.domains.detection.application.use_cases.detect_motion import DetectMotion
from app.domains.detection.application.use_cases.finish_recording import FinishRecording
from app.domains.detection.domain.entities import EventStatus
from app.domains.detection.domain.exceptions import CameraDisconnected
from app.domains.detection.domain.recording import Frame, RecordingSession
from tests.domains.detection.builders import DEVICE, HIGH, LOW, at
from tests.domains.detection.fakes import (
    FakeDetectionUnitOfWork,
    FakeMediaUploader,
    FakePushNotifier,
    NoWaitBackoff,
)
from tests.fakes import SequentialIds


class ScriptedFrames(FrameSource):
    """照腳本吐影格;disconnect_after 模擬鏡頭斷線。"""

    def __init__(self, script: list[tuple[float, Decimal]], *, disconnect: bool = False) -> None:
        self.script = script
        self.disconnect = disconnect

    async def frames(self) -> AsyncIterator[Frame]:
        for seconds, score in self.script:
            yield Frame(at=at(seconds), score=score)
        if self.disconnect:
            raise CameraDisconnected()


class FakeEncoder(ClipEncoder):
    def __init__(self) -> None:
        self.calls: list[RecordingSession] = []

    async def encode(self, session: RecordingSession, ended_at) -> EncodedClip:
        self.calls.append(session)
        return EncodedClip(video=b"mp4", thumbnail=b"jpg")


@pytest.fixture
def uow() -> FakeDetectionUnitOfWork:
    return FakeDetectionUnitOfWork()


@pytest.fixture
def encoder() -> FakeEncoder:
    return FakeEncoder()


def a_worker(uow, encoder, frames: ScriptedFrames) -> DetectMotion:
    finish = FinishRecording(
        uow=uow,
        uploader=FakeMediaUploader(),
        backoff=NoWaitBackoff(),
        notifier=FakePushNotifier(),
    )
    return DetectMotion(
        device_id=DEVICE,
        frames=frames,
        encoder=encoder,
        finish_recording=finish,
        ids=SequentialIds(),
    )


async def events_of(uow) -> list:
    return sorted(uow.events.committed.values(), key=lambda e: e.started_at)


async def test_quiet_camera_produces_no_events(uow, encoder):
    await a_worker(uow, encoder, ScriptedFrames([(0, LOW), (1, LOW), (10, LOW)])).run()

    assert await events_of(uow) == []


async def test_continuous_motion_produces_exactly_one_event(uow, encoder):
    """驗收標準:連續動作只產生一筆事件(§2.1)。"""
    script = [(float(i), HIGH) for i in range(0, 10)] + [(20.0, LOW)]

    await a_worker(uow, encoder, ScriptedFrames(script)).run()

    events = await events_of(uow)
    assert len(events) == 1
    assert events[0].status is EventStatus.READY


async def test_a_gap_longer_than_the_silence_timeout_starts_a_new_event(uow, encoder):
    """靜止超過 5 秒後再有動作,是新的一個事件。"""
    script = [(0, HIGH), (1, HIGH), (10, LOW), (11, HIGH), (12, HIGH), (30, LOW)]

    await a_worker(uow, encoder, ScriptedFrames(script)).run()

    assert len(await events_of(uow)) == 2


async def test_brief_pauses_do_not_split_the_event(uow, encoder):
    """短暫停頓(不到 5 秒)仍算同一個事件,不該被切成兩筆。"""
    script = [(0, HIGH), (3, LOW), (6, HIGH), (9, HIGH), (20, LOW)]

    await a_worker(uow, encoder, ScriptedFrames(script)).run()

    assert len(await events_of(uow)) == 1


async def test_recording_is_cut_at_sixty_seconds(uow, encoder):
    """驗收標準:單一事件錄影超過 60 秒強制結束(§2.2)。"""
    script = [(float(i), HIGH) for i in range(0, 91, 5)]

    await a_worker(uow, encoder, ScriptedFrames(script)).run()

    events = await events_of(uow)
    assert all(e.duration_sec <= 60 for e in events)
    assert len(events) >= 2  # 動作還在繼續,所以切成下一段而不是整段丟掉


async def test_camera_disconnect_still_saves_what_was_recorded(uow, encoder):
    """§3 邊界案例:錄影中鏡頭斷線,已錄製部分仍上傳,標記 is_partial。"""
    await a_worker(uow, encoder, ScriptedFrames([(0, HIGH), (2, HIGH)], disconnect=True)).run()

    events = await events_of(uow)
    assert len(events) == 1
    assert events[0].status is EventStatus.READY
    assert events[0].is_partial is True


async def test_disconnect_while_idle_produces_nothing(uow, encoder):
    """沒有在錄影時斷線,不該生出一筆空事件。"""
    await a_worker(uow, encoder, ScriptedFrames([(0, LOW)], disconnect=True)).run()

    assert await events_of(uow) == []


async def test_stream_ending_normally_closes_the_open_recording(uow, encoder):
    """串流正常結束(worker 關機)時,進行中的錄影要收掉,不能留在 processing。"""
    await a_worker(uow, encoder, ScriptedFrames([(0, HIGH), (1, HIGH)])).run()

    events = await events_of(uow)
    assert len(events) == 1
    assert events[0].status is EventStatus.READY


async def test_each_event_gets_its_own_id(uow, encoder):
    script = [(0, HIGH), (10, LOW), (11, HIGH), (30, LOW)]

    await a_worker(uow, encoder, ScriptedFrames(script)).run()

    events = await events_of(uow)
    assert len({e.id for e in events}) == len(events)


async def test_the_encoder_is_only_asked_for_clips_that_exist(uow, encoder):
    await a_worker(uow, encoder, ScriptedFrames([(0, LOW), (1, LOW)])).run()

    assert encoder.calls == []
