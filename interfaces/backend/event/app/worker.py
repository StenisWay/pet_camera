"""F2 偵測 worker 的進入點。

這不是 HTTP 服務:它是 VM-3 上的單例,鏡頭的 RTSP 直連它,不經 Load Balancer
(13_ADR 第 1 節)。與 Postgres 同機,所以事件寫入不跨網路——ADR 第 4 節說 worker
的寫入選可用性(重試),只在 Postgres 本身不可用時才本機重試。

執行:
    uv run python -m app.worker            # 需要 FrameSource / ClipEncoder 的實作

**目前缺 RTSP 與 ffmpeg 的 adapter**(見 README 的已知限制)。錄影的業務規則
(事件合併、5 秒靜止、60 秒上限、上傳重試、狀態收斂)已經完整實作並測試,
缺的是把影格與檔案接進來的那一層:實作 FrameSource 與 ClipEncoder 之後,
把它們傳進 build_worker 就能跑。
"""

import asyncio
from uuid import UUID

from app.core.config import Settings, get_settings
from app.core.database import get_session_factory
from app.core.system import Uuid7Generator
from app.domains.detection.application.ports import ClipEncoder, FrameSource
from app.domains.detection.application.use_cases.detect_motion import DetectMotion
from app.domains.detection.application.use_cases.finish_recording import FinishRecording
from app.domains.detection.infrastructure.backoff import ExponentialBackoff
from app.domains.detection.infrastructure.push_adapter import HttpPushNotifier
from app.domains.detection.infrastructure.storage_adapter import R2MediaUploader
from app.domains.detection.infrastructure.unit_of_work import SqlAlchemyDetectionUnitOfWork


def build_worker(
    *,
    device_id: UUID,
    frames: FrameSource,
    encoder: ClipEncoder,
    settings: Settings | None = None,
) -> DetectMotion:
    """組裝一支鏡頭的偵測迴圈(composition root)。

    一個實例對應一支鏡頭;多支鏡頭就建多個實例,用 asyncio.gather 一起跑。
    """
    settings = settings or get_settings()
    finish = FinishRecording(
        uow=SqlAlchemyDetectionUnitOfWork(get_session_factory()),
        uploader=R2MediaUploader(settings),
        backoff=ExponentialBackoff(),
        notifier=HttpPushNotifier(
            base_url=settings.push_service_url, api_key=settings.internal_api_key
        ),
    )
    return DetectMotion(
        device_id=device_id,
        frames=frames,
        encoder=encoder,
        finish_recording=finish,
        ids=Uuid7Generator(),
    )


async def run_forever(workers: list[DetectMotion]) -> None:
    """每支鏡頭一個迴圈,一支斷線不影響其他支。

    DetectMotion.run() 在斷線時會收掉進行中的錄影然後回傳,所以這裡重新啟動它,
    等於「鏡頭回來就繼續錄」。
    """
    await asyncio.gather(*(worker.run() for worker in workers))


def main() -> None:
    raise NotImplementedError(
        "需要 FrameSource(RTSP + 移動偵測)與 ClipEncoder(ffmpeg)的實作。"
        "業務規則已完成,見 app/domains/detection/,以及 README 的「已知限制」。"
    )


if __name__ == "__main__":
    main()
