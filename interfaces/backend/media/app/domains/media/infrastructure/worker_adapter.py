"""FrameSource 與 ClipWorker 接到 VM-3 的偵測/轉碼 worker(規格審查 #2、#3)。

為什麼是 worker 而不是本服務自己做:
- 擷幀:F1 的 WebRTC media 經 TURN 直達前端,不經過 Media 服務;唯一持有鏡頭影像
  的是直連 RTSP 的偵測 worker(13_ADR 第 1 節)。
- 轉碼:ffmpeg 是 CPU 密集工作,ADR 第 6 節把 2 OCPU 分給 VM-3 就是為了它。

刻意不引入工作佇列:ADR 第 1.1 節把共用 Redis 的用途限定在三項,不含佇列。派工是
一次同步的內部 HTTP 呼叫(受理即回),完成後 worker 回呼本服務的內部端點。
"""

import base64
import uuid

import httpx

from app.core.config import Settings
from app.domains.media.application.ports import CapturedFrame, ClipWorker, FrameSource
from app.domains.media.domain.exceptions import ScreenshotSourceUnavailable


class HttpWorker(FrameSource, ClipWorker):
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.worker_url,
            headers={"X-Internal-Api-Key": settings.internal_api_key},
            # 擷幀是同步路徑的一環,逾時要短——使用者在等 Toast
            timeout=10.0,
        )

    async def _capture(self, payload: dict[str, object]) -> CapturedFrame:
        try:
            response = await self._client.post("/internal/frames", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ScreenshotSourceUnavailable() from exc

        body = response.json()
        return CapturedFrame(
            image=base64.b64decode(body["image"]),
            thumbnail=base64.b64decode(body["thumbnail"]),
        )

    async def capture_live_frame(self, device_id: uuid.UUID) -> CapturedFrame:
        return await self._capture({"device_id": str(device_id)})

    async def capture_event_frame(
        self, event_id: uuid.UUID, *, offset_sec: int
    ) -> CapturedFrame:
        return await self._capture({"event_id": str(event_id), "offset_sec": offset_sec})

    async def dispatch(
        self,
        *,
        media_item_id: uuid.UUID,
        source_event_id: uuid.UUID,
        start_sec: int,
        end_sec: int,
        object_key: str,
        thumbnail_object_key: str,
    ) -> None:
        response = await self._client.post(
            "/internal/clips",
            json={
                "media_item_id": str(media_item_id),
                "source_event_id": str(source_event_id),
                "start_sec": start_sec,
                "end_sec": end_sec,
                "object_key": object_key,
                "thumbnail_object_key": thumbnail_object_key,
            },
        )
        # 派不出去就讓例外往上拋,由 use case 把項目標成 failed
        response.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()
