"""錄影結束後的後處理:寫入事件 → 上傳 → 收斂狀態 → 推播。

對應 07_spec_事件偵測與自動錄影.md 第 3 節。
"""

from app.domains.detection.application.dtos import EventResult, FinishRecordingCommand
from app.domains.detection.application.ports import (
    Backoff,
    DetectionUnitOfWork,
    MediaUploader,
    PushNotifier,
)
from app.domains.detection.domain.entities import Event, UploadedMedia
from app.domains.detection.domain.exceptions import UploadFailed
from app.domains.detection.domain.object_keys import thumbnail_key, video_key
from app.domains.detection.domain.recording import StopReason

UPLOAD_MAX_ATTEMPTS = 3


class FinishRecording:
    """錄影停止的那一刻,worker 呼叫這裡把片段變成一筆可播放的事件。

    交易切成兩段是刻意的:第一段先讓事件以 processing 出現在時間軸(§3.1),
    第二段才在上傳完成後收斂狀態(§3.4/3.5)。上傳可能花掉數秒到數十秒,
    把它包在同一個交易裡會讓連線在整段上傳期間都被佔住。
    """

    def __init__(
        self,
        *,
        uow: DetectionUnitOfWork,
        uploader: MediaUploader,
        backoff: Backoff,
        notifier: PushNotifier,
    ) -> None:
        self.uow = uow
        self.uploader = uploader
        self.backoff = backoff
        self.notifier = notifier

    async def execute(self, command: FinishRecordingCommand) -> EventResult:
        session = command.session
        event = Event.begin(
            id=session.event_id, device_id=session.device_id, started_at=session.started_at
        )

        # §3.1:先寫入 processing,時間軸立刻看得到「處理中」卡片
        async with self.uow:
            await self.uow.events.save(event)
            await self.uow.commit()

        uploaded = await self._upload_with_retry(command)

        # §3.4 / §3.5:上傳的結果決定事件的終態
        if uploaded is None:
            event.mark_failed()
        else:
            event.mark_ready(uploaded)

        async with self.uow:
            await self.uow.events.save(event)
            await self.uow.commit()

        if uploaded is not None:
            await self._notify(event)

        return EventResult.from_entity(event)

    async def _upload_with_retry(self, command: FinishRecordingCommand) -> UploadedMedia | None:
        """§3 邊界案例:重試 3 次、指數退避;全部失敗回 None。

        每一輪都從頭上傳兩個檔案,失敗時先清掉這一輪已經送上去的物件——否則
        「影片上去了、縮圖失敗」會在 R2 留下沒有任何事件指向它的孤兒檔案
        (驗收標準:不產生孤兒資料)。
        """
        session = command.session
        keys = {
            "video": video_key(
                device_id=session.device_id,
                event_id=session.event_id,
                started_at=session.started_at,
            ),
            "thumbnail": thumbnail_key(
                device_id=session.device_id,
                event_id=session.event_id,
                started_at=session.started_at,
            ),
        }

        for attempt in range(1, UPLOAD_MAX_ATTEMPTS + 1):
            done: list[str] = []
            try:
                await self.uploader.upload(keys["video"], command.video, content_type="video/mp4")
                done.append(keys["video"])
                await self.uploader.upload(
                    keys["thumbnail"], command.thumbnail, content_type="image/jpeg"
                )
            except UploadFailed:
                if done:
                    await self.uploader.delete_many(done)
                if attempt < UPLOAD_MAX_ATTEMPTS:
                    await self.backoff.wait(attempt)
                continue

            return UploadedMedia(
                video_object_key=keys["video"],
                thumbnail_object_key=keys["thumbnail"],
                confidence_score=session.peak_score,
                duration_sec=session.duration_sec(command.ended_at),
                ended_at=command.ended_at,
                # 斷線的片段仍可播放,只是不完整(EVENT_003)
                is_partial=command.stop_reason is StopReason.DISCONNECTED,
            )
        return None

    async def _notify(self, event: Event) -> None:
        """§3.6:ready 之後觸發推播。

        推播失敗不回頭改事件狀態——事件已經 ready 是事實,通知沒送出是另一回事,
        把它變成 failed 反而會讓使用者看不到明明存在的影片。
        """
        try:
            await self.notifier.notify_event_ready(
                device_id=event.device_id,
                event_id=event.id,
                confidence_score=event.confidence_score,
                thumbnail_object_key=event.thumbnail_object_key,
                started_at=event.started_at,
            )
        except Exception:  # noqa: BLE001 — Push 的任何故障都不該影響事件本身
            pass
