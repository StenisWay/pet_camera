"""Push 服務進入點(F4:推播通知)。

部署形狀見 rule_doc/功能需求/13_ADR_微服務與三節點部署.md:本服務是無狀態複本,
VM-1/VM-2 各跑一份,由 Oracle Load Balancer 分流;Postgres 與 Redis 是 VM-3 的單例。

這裡是 composition root:所有 adapter 在 lifespan 組好掛上 app.state,包含跨領域的
收件端點查詢(notifications 透過 push_tokens.api 取得)——兩個領域的內層互不知道對方存在。

engine 是 lazy 的,import 本模組不會建立任何連線。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.http_errors import register_exception_handlers
from app.domains.notifications.presentation.internal_router import router as internal_router
from app.domains.push_tokens.presentation.router import router as push_tokens_router


def build_adapters(app: FastAPI) -> None:
    """把外部系統的 adapter 接上。

    import 放在函式內:測試用 dependency_overrides 換掉這些,不需要安裝或連上
    Redis、R2、FCM 任何一項。
    """
    from app.core.database import get_session_factory
    from app.core.redis_rate_limit import RedisRateLimitCounter
    from app.core.system import SystemClock, Uuid7Generator
    from app.domains.notifications.infrastructure.device_directory import HttpDeviceDirectory
    from app.domains.notifications.infrastructure.gateways import build_push_gateway
    from app.domains.notifications.infrastructure.r2_thumbnails import R2ThumbnailLinks
    from app.domains.notifications.infrastructure.recipient_adapter import (
        PushTokensRecipientDirectory,
    )
    from app.domains.notifications.infrastructure.redis_window import RedisNotificationWindow
    from app.domains.push_tokens.api import PushTokensApi

    settings = get_settings()

    app.state.clock = SystemClock()
    app.state.id_generator = Uuid7Generator()
    app.state.rate_limit_counter = RedisRateLimitCounter(settings.redis_url)
    app.state.device_directory = HttpDeviceDirectory(settings)
    app.state.notification_window = RedisNotificationWindow(
        settings.redis_url, window_seconds=settings.dedup_window_seconds
    )
    app.state.thumbnail_links = R2ThumbnailLinks(settings)
    app.state.push_gateway = build_push_gateway(settings)
    # 跨領域的接線只發生在這裡
    app.state.recipient_directory = PushTokensRecipientDirectory(
        PushTokensApi.from_session_factory(get_session_factory())
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    build_adapters(app)
    try:
        yield
    finally:
        for name in (
            "rate_limit_counter",
            "notification_window",
            "device_directory",
            "push_gateway",
        ):
            closer = getattr(getattr(app.state, name, None), "aclose", None)
            if closer is not None:
                await closer()


def create_app(*, lifespan_enabled: bool = True) -> FastAPI:
    """工廠函式,讓測試可以建立乾淨的 app 實例。"""
    app = FastAPI(
        title=get_settings().app_name,
        lifespan=lifespan if lifespan_enabled else None,
    )
    register_exception_handlers(app)
    app.include_router(push_tokens_router)
    app.include_router(internal_router)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        """Load Balancer 的健康檢查端點,不碰資料庫。

        VM-3 掛掉時不該連帶讓兩台服務節點被判定為不健康(13_ADR 第 3 節)。
        """
        return {"status": "ok"}

    return app


app = create_app()
