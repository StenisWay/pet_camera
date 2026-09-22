"""偵測迴圈:把一支鏡頭的影格串流變成一連串事件。

這是 F2 worker 的核心(07_spec 第 2 節)。一個實例對應一支鏡頭。

迴圈本身不碰任何 I/O:影格從 FrameSource 來、檔案由 ClipEncoder 產生、寫入與上傳
交給 FinishRecording。所以「什麼算同一個事件」「什麼時候該結束」這些規則,
不需要鏡頭、不需要 ffmpeg、也不需要資料庫就測得出來。
"""

from datetime import datetime
from uuid import UUID

from app.domains.detection.application.dtos import FinishRecordingCommand
from app.domains.detection.application.ports import ClipEncoder, FrameSource
from app.domains.detection.application.use_cases.finish_recording import FinishRecording
from app.domains.detection.domain.exceptions import CameraDisconnected
from app.domains.detection.domain.recording import (
    Frame,
    RecordingSession,
    StopReason,
    is_motion,
)
from app.shared_kernel.ports import IdGenerator


class DetectMotion:
    def __init__(
        self,
        *,
        device_id: UUID,
        frames: FrameSource,
        encoder: ClipEncoder,
        finish_recording: FinishRecording,
        ids: IdGenerator,
    ) -> None:
        self.device_id = device_id
        self.frames = frames
        self.encoder = encoder
        self.finish_recording = finish_recording
        self.ids = ids

    async def run(self) -> None:
        """一直跑到串流結束或斷線。

        中途斷線、或 worker 關機時串流正常結束,進行中的錄影都要收掉——留一筆
        永遠停在 processing 的事件,時間軸上就是一張永遠轉圈的卡片。
        """
        session: RecordingSession | None = None
        try:
            async for frame in self.frames.frames():
                session = await self._observe(frame, session)
        except CameraDisconnected:
            pass

        if session is not None:
            await self._stop(session, session.last_motion_at, StopReason.DISCONNECTED)

    async def _observe(
        self, frame: Frame, session: RecordingSession | None
    ) -> RecordingSession | None:
        if session is None:
            return self._start(frame) if is_motion(frame.score) else None

        session.observe(at=frame.at, score=frame.score)
        reason = session.stop_reason(frame.at)
        if reason is None:
            return session

        await self._stop(session, self._ended_at(session, frame, reason), reason)

        # 達 60 秒上限時活動通常還在繼續:切成下一段,而不是把剩下的動作丟掉。
        # 靜止結束時這個影格照定義不是活動,所以不會開新的錄影。
        return self._start(frame) if is_motion(frame.score) else None

    def _start(self, frame: Frame) -> RecordingSession:
        return RecordingSession.start(
            event_id=self.ids.new_id(),
            device_id=self.device_id,
            at=frame.at,
            score=frame.score,
        )

    @staticmethod
    def _ended_at(session: RecordingSession, frame: Frame, reason: StopReason) -> datetime:
        """靜止結束的片段收在最後一次活動,不要把後面那幾秒的空景也錄進去;
        60 秒上限則是當下硬生生切斷,結束時間就是這一刻。"""
        return frame.at if reason is StopReason.MAX_DURATION else session.last_motion_at

    async def _stop(
        self, session: RecordingSession, ended_at: datetime, reason: StopReason
    ) -> None:
        clip = await self.encoder.encode(session, ended_at)
        await self.finish_recording.execute(
            FinishRecordingCommand(
                session=session,
                video=clip.video,
                thumbnail=clip.thumbnail,
                ended_at=ended_at,
                stop_reason=reason,
            )
        )
