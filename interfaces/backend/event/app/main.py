"""建立 FastAPI app。

Event 服務的對外面貌只有 F3 的時間軸讀取 API 與一個內部端點;F2 的偵測 worker
是獨立行程(app/worker.py),跑在 VM-3,不經 Load Balancer(13_ADR 第 1 節)。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.http_errors import register_exception_handlers
from app.domains.detection.presentation.router import internal_router
from app.domains.timeline.presentation.router import devices_router, events_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """目前沒有需要在啟動時建立的資源。

    engine 是 lazy 的(core/database.py),第一個請求才會真正連線——健康檢查
    因此在資料庫掛掉時仍然回得了 200,LB 不會把兩台節點同時判死。
    """
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    register_exception_handlers(app)
    app.include_router(devices_router)
    app.include_router(events_router)
    app.include_router(internal_router)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        """LB 的健康檢查。刻意不碰資料庫與 R2:這支要回答的是「這個複本還活著嗎」,
        不是「整個系統健康嗎」——把資料層的故障傳染到這裡,會讓 LB 同時拔掉兩台
        還能正常服務降級路徑的節點。"""
        return {"status": "ok"}

    return app


app = create_app()
