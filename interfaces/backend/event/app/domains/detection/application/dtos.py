"""application 的輸入輸出 DTO。不用 Pydantic——application 不依賴框架。"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.domains.detection.domain.entities import Event, EventStatus
from app.domains.detection.domain.recording import RecordingSession, StopReason


@dataclass(frozen=True)
class EncodedClip:
    """ffmpeg 的產物,交給 FinishRecording 上傳。"""

    video: bytes
    thumbnail: bytes


@dataclass(frozen=True)
class FinishRecordingCommand:
    session: RecordingSession
    video: bytes
    thumbnail: bytes
    ended_at: datetime
    stop_reason: StopReason


@dataclass(frozen=True)
class EventResult:
    id: UUID
    device_id: UUID
    status: EventStatus
    confidence_score: Decimal
    duration_sec: int | None
    is_partial: bool

    @classmethod
    def from_entity(cls, event: Event) -> "EventResult":
        return cls(
            id=event.id,
            device_id=event.device_id,
            status=event.status,
            confidence_score=event.confidence_score,
            duration_sec=event.duration_sec,
            is_partial=event.is_partial,
        )
