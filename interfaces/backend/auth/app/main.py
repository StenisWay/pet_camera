"""FastAPI 應用組裝點。

lifespan 負責建立跨請求共用的連線(資料庫 engine、Redis、httpx client),掛到
app.state;provider 函式只從那裡取出來,不自己建——否則每個請求都會開一條連線。

router 由各領域的 presentation 提供;兩個領域共用 /auth 前綴,由 Load Balancer
依路徑分流到本服務(13_ADR 第 1 節)。
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import redis.asyncio as redis
from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.core.database import get_session_factory
from app.core.http_errors import register_exception_handlers
from app.core.rate_limit import RateLimitCounter
from app.domains.accounts.infrastructure.mailer import LoggingEmailSender
from app.domains.accounts.infrastructure.purgers import album_purger, device_purger
from app.domains.accounts.presentation.router import router as accounts_router
from app.domains.sessions.presentation.router import router as sessions_router

logger = logging.getLogger(__name__)


class RedisRateLimitCounter(RateLimitCounter):
    """共用 Redis 的計數窗(01_資料模型 第 7.1 節)。"""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    async def hit(self, key: str, *, window_seconds: int) -> int:
        count = int(await self._client.incr(key))
        if count == 1:
            # 計數窗從第一次請求起算
            await self._client.expire(key, window_seconds)
        return count


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = get_settings()

    app.state.session_factory = get_session_factory()
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    app.state.rate_limit_counter = RedisRateLimitCounter(app.state.redis)
    app.state.email_sender = LoggingEmailSender()

    internal_client = httpx.AsyncClient(timeout=settings.internal_call_timeout_seconds)
    app.state.internal_client = internal_client
    # 順序就是刪除帳號的清除順序:Device → Album(05_spec 第 2.2 節)
    app.state.account_purgers = [
        device_purger(
            internal_client,
            base_url=settings.device_service_base_url,
            api_key=settings.internal_api_key,
        ),
        album_purger(
            internal_client,
            base_url=settings.album_service_base_url,
            api_key=settings.internal_api_key,
        ),
    ]

    if settings.jwt_secret == "change-me" and not settings.debug:
        logger.warning("AUTH_JWT_SECRET 仍是預設值——正式環境務必改掉")

    try:
        yield
    finally:
        await internal_client.aclose()
        await app.state.redis.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(accounts_router)
    app.include_router(sessions_router)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
