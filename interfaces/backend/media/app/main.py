"""Media 服務進入點(F5:剪輯與截圖)。

部署形狀見 rule_doc/功能需求/13_ADR_微服務與三節點部署.md:本服務是無狀態複本,
VM-1/VM-2 各跑一份,由 Oracle Load Balancer 分流;Postgres、Redis 與事件偵測/轉碼
worker 都是 VM-3 的單例。

這裡是 composition root:所有 adapter 在 lifespan 建立後掛上 app.state,
presentation 的 provider 只負責從 app.state 取——測試因此可以完全不碰外部系統。

注意:目前**不連線任何真實資料庫**,engine 是 lazy 的,import 本模組不會建立連線。
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.http_errors import register_exception_handlers
from app.domains.media.presentation.internal_router import router as internal_router
from app.domains.media.presentation.router import router as media_router

logger = logging.getLogger(__name__)

STALE_SWEEP_INTERVAL_SECONDS = 60


def build_adapters(app: FastAPI) -> None:
    """把外部系統的 adapter 接上。

    import 放在函式內:測試用 dependency_overrides 換掉這些,不需要安裝或連上
    Postgres、Redis、R2 或 VM-3 的 worker。
    """
    from app.core.database import get_session_factory
    from app.core.redis_rate_limit import RedisRateLimitCounter
    from app.core.system import SystemClock, Uuid7Generator
    from app.domains.media.infrastructure.device_adapter import HttpDeviceDirectory
    from app.domains.media.infrastructure.event_adapter import HttpEventSource
    from app.domains.media.infrastructure.r2_storage import R2MediaStorage
    from app.domains.media.infrastructure.unit_of_work import SqlAlchemyMediaUnitOfWork
    from app.domains.media.infrastructure.worker_adapter import HttpWorker

    settings = get_settings()
    session_factory = get_session_factory()

    app.state.uow_factory = lambda: SqlAlchemyMediaUnitOfWork(session_factory)
    app.state.clock = SystemClock()
    app.state.id_generator = Uuid7Generator()
    app.state.media_storage = R2MediaStorage(settings)
    app.state.rate_limit_counter = RedisRateLimitCounter(settings.redis_url)
    app.state.device_directory = HttpDeviceDirectory(settings)
    app.state.event_source = HttpEventSource(settings)
    # 擷幀與轉碼是同一個 worker 的兩種能力,共用一條 HTTP client
    worker = HttpWorker(settings)
    app.state.frame_source = worker
    app.state.clip_worker = worker


async def _sweep_stale_processing(app: FastAPI) -> None:
    """審查 #9:定期把卡住的 processing 改判 failed。

    VM-1/VM-2 各跑一份是可接受的——掃描是冪等的,兩份複本同時做,最壞情況只是
    同一筆被寫兩次成 failed。
    """
    from datetime import timedelta

    from app.domains.media.application.use_cases.expire_stale_processing import (
        ExpireStaleProcessing,
    )

    settings = get_settings()
    while True:
        await asyncio.sleep(STALE_SWEEP_INTERVAL_SECONDS)
        try:
            use_case = ExpireStaleProcessing(
                app.state.uow_factory(),
                app.state.clock,
                stale_after=timedelta(seconds=settings.processing_stale_after_seconds),
            )
            expired = await use_case.execute()
            if expired:
                logger.info("marked %s stale media items as failed", expired)
        except Exception:
            logger.warning("stale processing sweep failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    build_adapters(app)
    sweeper = asyncio.create_task(_sweep_stale_processing(app))
    try:
        yield
    finally:
        sweeper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweeper
        for resource in (
            app.state.rate_limit_counter,
            app.state.device_directory,
            app.state.event_source,
            app.state.frame_source,
        ):
            closer = getattr(resource, "aclose", None)
            if closer is not None:
                await closer()


def create_app(*, lifespan_enabled: bool = True) -> FastAPI:
    """工廠函式,讓測試可以建立乾淨的 app 實例。"""
    app = FastAPI(
        title=get_settings().app_name,
        lifespan=lifespan if lifespan_enabled else None,
    )
    register_exception_handlers(app)
    app.include_router(media_router)
    app.include_router(internal_router)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        """Load Balancer 的健康檢查端點,不碰資料庫。

        VM-3 掛掉時不該連帶讓兩台服務節點被判定為不健康(13_ADR 第 3 節)。
        """
        return {"status": "ok"}

    return app


app = create_app()
