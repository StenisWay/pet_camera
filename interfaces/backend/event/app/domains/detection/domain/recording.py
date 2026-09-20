"""錄影會話:一次錄影從觸發到結束的進行狀態。

07_spec_事件偵測與自動錄影.md 第 2.1、2.2 節的合併與結束規則全部在這裡。

純值物件,不碰 I/O——影格從哪來、怎麼編碼是 worker 的 adapter 的事,這裡只回答
「這個影格算不算活動」「現在該不該結束」。因此這些規則不需要鏡頭就能測。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.domains.detection.domain.exceptions import MotionBelowThreshold


class StopReason(StrEnum):
    SILENCE = "silence"
    MAX_DURATION = "max_duration"
    DISCONNECTED = "disconnected"

# 第 2.1 節:預設門檻 0.6。門檻值本身視為有活動,見 README 假設表。
MOTION_THRESHOLD = Decimal("0.60")
# 第 2.2 節:活動停止超過 5 秒結束錄影;單一事件最長 60 秒。
SILENCE_TIMEOUT = timedelta(seconds=5)
MAX_RECORDING_DURATION = timedelta(seconds=60)


def is_motion(score: Decimal) -> bool:
    return score >= MOTION_THRESHOLD


@dataclass
class RecordingSession:
    event_id: UUID
    device_id: UUID
    started_at: datetime
    last_motion_at: datetime
    peak_score: Decimal

    @classmethod
    def start(
        cls, *, event_id: UUID, device_id: UUID, at: datetime, score: Decimal
    ) -> "RecordingSession":
        """分數超過門檻時開始錄影。低於門檻不該走到這裡。"""
        if not is_motion(score):
            raise MotionBelowThreshold()
        return cls(
            event_id=event_id,
            device_id=device_id,
            started_at=at,
            last_motion_at=at,
            peak_score=score,
        )

    def observe(self, *, at: datetime, score: Decimal) -> None:
        """吃進一個影格的分數。

        超過門檻視為活動延續:只延後 last_motion_at,不動 started_at,也不建立新事件
        ——這就是第 2.1 節「後續活動視為同一事件延續」。低於門檻的影格不延後結束時間,
        否則安靜下來的錄影永遠不會結束。
        """
        if not is_motion(score):
            return
        self.last_motion_at = at
        self.peak_score = max(self.peak_score, score)

    def should_stop(self, now: datetime) -> bool:
        """活動停止超過 SILENCE_TIMEOUT,或已達 MAX_RECORDING_DURATION 上限。"""
        return self.stop_reason(now) is not None

    def stop_reason(self, now: datetime) -> "StopReason | None":
        """結束原因;還不該結束時回 None。

        先看上限再看靜止:兩者同時成立時,60 秒上限是硬性限制(強制結束),
        與「剛好沒動作了」在語意上不同,worker 的日誌要分得出來。

        DISCONNECTED 不會從這裡產生——斷線是 worker 讀不到影格時才知道的事實,
        由呼叫端傳入,不是時間推算得出來的。
        """
        if now - self.started_at >= MAX_RECORDING_DURATION:
            return StopReason.MAX_DURATION
        if now - self.last_motion_at >= SILENCE_TIMEOUT:
            return StopReason.SILENCE
        return None

    def duration_sec(self, ended_at: datetime) -> int:
        """實際錄影長度,四捨五入到秒,至少 1 秒。

        資料表的 CHECK 要求 duration_sec > 0(01_資料模型第 2.3 節),
        所以極短的片段也記為 1 秒,而不是 0。
        """
        seconds = round((ended_at - self.started_at).total_seconds())
        return max(1, seconds)
