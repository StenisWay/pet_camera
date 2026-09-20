"""FastAPI 應用組裝點。

router 由各領域的 presentation 提供;本檔只負責把它們掛起來、註冊例外處理,
以及在 lifespan 內建立/關閉跨請求共用的連線(Redis、HTTP client)。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.http_errors import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    register_exception_handlers(app)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
