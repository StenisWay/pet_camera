"""RecordingSession:07_spec 第 2.1、2.2 節的錄影合併與結束規則。"""

from decimal import Decimal

import pytest

from app.domains.detection.domain.exceptions import MotionBelowThreshold
from app.domains.detection.domain.recording import MOTION_THRESHOLD, RecordingSession
from tests.domains.detection.builders import DEVICE, EVENT, HIGH, LOW, at


def a_session(*, score: Decimal = HIGH, start_at: float = 0) -> RecordingSession:
    return RecordingSession.start(
        event_id=EVENT, device_id=DEVICE, at=at(start_at), score=score
    )


def test_starting_a_recording_records_the_first_motion():
    session = a_session(score=HIGH)

    assert session.event_id == EVENT
    assert session.device_id == DEVICE
    assert session.started_at == at(0)
    assert session.last_motion_at == at(0)
    assert session.peak_score == HIGH


def test_starting_below_threshold_is_rejected():
    """低於門檻不該開始錄影——呼叫端(worker)應該先比對門檻再決定要不要開始。"""
    with pytest.raises(MotionBelowThreshold):
        a_session(score=LOW)


def test_continued_motion_extends_the_same_session():
    """§2.1:錄影期間偵測到的後續活動視為同一事件延續,不建立新事件。"""
    session = a_session()

    session.observe(at=at(3), score=HIGH)

    assert session.event_id == EVENT  # 仍是同一筆事件
    assert session.started_at == at(0)  # 開始時間不變
    assert session.last_motion_at == at(3)  # 只延後「最後一次活動」


def test_motion_below_threshold_does_not_extend_the_session():
    """低於門檻的影格是「沒有活動」,不能延後結束時間,否則永遠不會結束。"""
    session = a_session()

    session.observe(at=at(3), score=LOW)

    assert session.last_motion_at == at(0)


def test_peak_score_keeps_the_highest_value_of_the_event():
    """§3.4:confidence_score 取事件期間最高值。"""
    session = a_session(score=Decimal("0.70"))

    session.observe(at=at(1), score=Decimal("0.95"))
    session.observe(at=at(2), score=Decimal("0.80"))

    assert session.peak_score == Decimal("0.95")


@pytest.mark.parametrize(
    ("score", "counts_as_motion"),
    [
        (MOTION_THRESHOLD - Decimal("0.01"), False),
        (MOTION_THRESHOLD, True),  # 假設:門檻值本身算有活動(見 README 假設表)
        (MOTION_THRESHOLD + Decimal("0.01"), True),
    ],
)
def test_threshold_boundary(score, counts_as_motion):
    """§2.1 寫「超過門檻值」、§2.2 寫「低於門檻」,門檻值本身兩邊都沒說到。

    採用 >= 門檻視為有活動(規格審查後的 🟡 假設):寧可多錄一點,也不要讓剛好
    落在門檻上的影格被當成沒有活動而提早結束錄影。
    """
    session = a_session()

    session.observe(at=at(3), score=score)

    assert (session.last_motion_at == at(3)) is counts_as_motion
