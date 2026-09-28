"""Stream 訊令服務進入點(F1:即時串流)。

部署形狀見 rule_doc/功能需求/13_ADR_微服務與三節點部署.md:本服務是無狀態複本,
VM-1/VM-2 各跑一份,由 Oracle Load Balancer 分流;Redis 與 TURN server 是 VM-3 的單例。

本服務**不擁有任何 Postgres 資料表**。session 是短效狀態,只進共用 Redis——
但不是「放本機記憶體也行」:同一個 session 的建立 / offer / 結束三個請求會被 LB 分派
到不同複本(06_spec 第 2.1 節)。

這裡是 composition root:所有 adapter 在 lifespan 組好掛上 app.state,
各層只認自己定義的 port。
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.http_errors import register_exception_handlers
from app.domains.streaming.presentation.internal_router import router as internal_router
from app.domains.streaming.presentation.router import router as stream_router

logger = logging.getLogger(__name__)


def build_adapters(app: FastAPI) -> None:
    """把外部系統的 adapter 接上。

    import 放在函式內:測試直接覆寫 app.state,不需要連上 Redis、TURN 或 Device 服務。
    """
    import httpx
    import redis.asyncio as redis

    from app.core.redis_rate_limit import RedisRateLimitCounter
    from app.core.security import SharedSecretCameraAuthenticator
    from app.core.system import SystemClock, Uuid7Generator
    from app.domains.streaming.infrastructure.device_directory import HttpDeviceDirectory
    from app.domains.streaming.infrastructure.redis_session_repository import (
        RedisStreamSessionRepository,
    )
    from app.domains.streaming.infrastructure.redis_signaling import RedisSignalingEvents
    from app.domains.streaming.infrastructure.turn import CoturnCredentialIssuer

    settings = get_settings()
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    device_client = httpx.AsyncClient(
        base_url=settings.device_service_base_url,
        timeout=settings.device_service_timeout_seconds,
    )

    app.state.redis = redis_client
    app.state.device_http = device_client
    app.state.clock = SystemClock()
    app.state.id_generator = Uuid7Generator()
    app.state.session_repository = RedisStreamSessionRepository(redis_client, app.state.clock)
    app.state.signaling_events = RedisSignalingEvents(redis_client)
    app.state.rate_limit_counter = RedisRateLimitCounter(settings.redis_url)
    app.state.turn_issuer = CoturnCredentialIssuer(
        urls=settings.turn_urls,
        secret=settings.turn_static_secret,
        ttl=timedelta(seconds=settings.turn_credential_ttl_seconds),
    )
    app.state.device_directory = HttpDeviceDirectory(
        device_client, internal_api_key=settings.internal_api_key
    )
    app.state.camera_authenticator = SharedSecretCameraAuthenticator(settings.internal_api_key)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    build_adapters(app)
    try:
        yield
    finally:
        await app.state.device_http.aclose()
        await app.state.rate_limit_counter.aclose()
        await app.state.redis.aclose()


def create_app(*, lifespan_enabled: bool = True) -> FastAPI:
    """工廠函式,讓測試可以建立乾淨的 app 實例。"""
    app = FastAPI(
        title=get_settings().app_name,
        lifespan=lifespan if lifespan_enabled else None,
    )
    register_exception_handlers(app)
    app.include_router(stream_router)
    app.include_router(internal_router)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        """Load Balancer 的健康檢查端點,不碰 Redis。

        VM-3 掛掉時不該連帶讓兩台服務節點被判定為不健康(13_ADR 第 3 節)。
        """
        return {"status": "ok"}

    return app


app = create_app()
