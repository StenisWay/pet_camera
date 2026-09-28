"""Device 服務的 FastAPI app(F0.2 裝置配對 + F0.3 裝置管理)。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.database import get_engine
from app.core.http_errors import register_exception_handlers
from app.domains.devices.presentation import internal_router, router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    # 沒有任何請求進來過就不會建立 engine,不必為了關閉而先連一次資料庫
    if get_engine.cache_info().currsize:
        await get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(router.router)
    app.include_router(internal_router.router)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        """LB 健康檢查。刻意不碰資料庫:VM-3 的 Postgres 掛掉時,

        VM-1/VM-2 上的服務複本本身還活著,不該被 LB 一起摘掉
        (13_ADR 第 4 節的降級規則是「回 SRV_002」,不是「整台下線」)。
        """
        return {"status": "ok"}

    return app


app = create_app()
