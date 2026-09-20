"""錄影的結束條件:07_spec 第 2.2 節與第 3 節邊界案例。"""

import pytest

from app.domains.detection.domain.recording import RecordingSession, StopReason
from tests.domains.detection.builders import DEVICE, EVENT, HIGH, at


def a_session() -> RecordingSession:
    return RecordingSession.start(event_id=EVENT, device_id=DEVICE, at=at(0), score=HIGH)


@pytest.mark.parametrize(
    ("silent_for", "should_stop"),
    [
        (4.9, False),
        (5.0, True),  # 驗收標準:「活動停止後 5 秒內結束錄影」
        (5.1, True),
    ],
)
def test_stops_after_five_seconds_of_silence(silent_for, should_stop):
    session = a_session()

    assert session.should_stop(at(silent_for)) is should_stop


def test_silence_is_measured_from_the_last_motion_not_from_the_start():
    """持續有動作就不該結束,即使距離錄影開始已經超過 5 秒。"""
    session = a_session()

    session.observe(at=at(4), score=HIGH)
    session.observe(at=at(8), score=HIGH)

    assert session.should_stop(at(10)) is False
    assert session.should_stop(at(13)) is True


def test_silence_stop_reason():
    session = a_session()

    assert session.stop_reason(at(6)) is StopReason.SILENCE


def test_not_stopping_yet_has_no_reason():
    session = a_session()

    assert session.stop_reason(at(1)) is None


@pytest.mark.parametrize(("elapsed", "should_stop"), [(59.9, False), (60.0, True), (61.0, True)])
def test_stops_at_the_sixty_second_cap_even_while_motion_continues(elapsed, should_stop):
    """§2.2:單一事件最長 60 秒。寵物一直動也要強制結束。"""
    session = a_session()
    session.observe(at=at(elapsed), score=HIGH)  # 上限當下仍有活動

    assert session.should_stop(at(elapsed)) is should_stop


def test_max_duration_takes_precedence_over_silence():
    """兩個條件同時成立時,回報上限——這是硬性限制,不是「剛好沒動作」。"""
    session = a_session()

    assert session.stop_reason(at(70)) is StopReason.MAX_DURATION


@pytest.mark.parametrize(
    ("ended_at_seconds", "expected"),
    [
        (12.0, 12),
        (12.4, 12),
        (12.6, 13),
        (0.0, 1),  # 資料表 CHECK 要求 duration_sec > 0
        (0.2, 1),
    ],
)
def test_duration_is_whole_seconds_and_never_zero(ended_at_seconds, expected):
    session = a_session()

    assert session.duration_sec(at(ended_at_seconds)) == expected
