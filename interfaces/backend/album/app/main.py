"""Album 服務進入點(F6:相簿與 Google Drive 匯出)。

部署形狀見 rule_doc/功能需求/13_ADR_微服務與三節點部署.md:本服務是無狀態複本,
VM-1/VM-2 各跑一份,由 Oracle Load Balancer 分流;Postgres 與 Redis 是 VM-3 的單例。

這裡是 composition root:所有 adapter 在 lifespan 組好掛上 app.state,包含跨領域的
AlbumContent(drive_export 用來讀相簿的 adapter)——領域自己的層級都不必知道對方存在。

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
from app.domains.album.presentation.internal_router import router as internal_router
from app.domains.album.presentation.router import router as album_router
from app.domains.drive_export.presentation.router import router as drive_router

logger = logging.getLogger(__name__)

STALE_EXPORT_SWEEP_INTERVAL_SECONDS = 60


def build_adapters(app: FastAPI) -> None:
    """把外部系統的 adapter 接上。

    import 放在函式內:測試用 dependency_overrides 換掉這些,不需要安裝或連上
    Redis、R2、Google 任何一項。
    """
    from app.core.database import get_session_factory
    from app.core.redis_rate_limit import RedisRateLimitCounter
    from app.core.system import SystemClock, Uuid7Generator
    from app.domains.album.api import AlbumApi
    from app.domains.album.infrastructure.r2_storage import R2ObjectStorage
    from app.domains.drive_export.infrastructure.album_adapter import AlbumApiContent
    from app.domains.drive_export.infrastructure.google import HttpGoogleDrive, HttpGoogleOAuth
    from app.domains.drive_export.infrastructure.redis_state_store import RedisOAuthStateStore

    settings = get_settings()
    session_factory = get_session_factory()

    app.state.clock = SystemClock()
    app.state.id_generator = Uuid7Generator()
    app.state.object_storage = R2ObjectStorage(settings)
    app.state.rate_limit_counter = RedisRateLimitCounter(settings.redis_url)
    app.state.oauth_state_store = RedisOAuthStateStore(settings.redis_url)
    app.state.google_oauth = HttpGoogleOAuth(settings)
    app.state.google_drive = HttpGoogleDrive()
    # 跨領域的接線只發生在這裡
    app.state.album_content = AlbumApiContent(
        AlbumApi(session_factory, app.state.object_storage, app.state.clock)
    )


async def _sweep_stale_exports(app: FastAPI) -> None:
    """規格審查 #7:定期把卡住的 exporting 改判 failed。

    VM-1/VM-2 各跑一份是可接受的——這個掃描是冪等的,兩份複本同時做,最壞情況只是
    同一筆被寫兩次成 failed。
    """
    from datetime import timedelta

    from app.core.database import get_session_factory
    from app.domains.album.application.use_cases.expire_stale_exports import ExpireStaleExports
    from app.domains.album.infrastructure.unit_of_work import SqlAlchemyAlbumUnitOfWork

    settings = get_settings()
    while True:
        await asyncio.sleep(STALE_EXPORT_SWEEP_INTERVAL_SECONDS)
        try:
            use_case = ExpireStaleExports(
                SqlAlchemyAlbumUnitOfWork(get_session_factory()),
                app.state.clock,
                stale_after=timedelta(seconds=settings.export_stale_after_seconds),
            )
            expired = await use_case.execute()
            if expired:
                logger.info("marked %s stale drive exports as failed", expired)
        except Exception:
            logger.warning("stale export sweep failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    build_adapters(app)
    sweeper = asyncio.create_task(_sweep_stale_exports(app))
    try:
        yield
    finally:
        sweeper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweeper
        for resource in (app.state.rate_limit_counter, app.state.oauth_state_store):
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
    app.include_router(album_router)
    app.include_router(drive_router)
    app.include_router(internal_router)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        """Load Balancer 的健康檢查端點,不碰資料庫。

        VM-3 掛掉時不該連帶讓兩台服務節點被判定為不健康(13_ADR 第 3 節)。
        """
        return {"status": "ok"}

    return app


app = create_app()
