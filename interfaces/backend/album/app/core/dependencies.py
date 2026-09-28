"""全服務共用的 provider。

這裡只放「不屬於任何一個領域」的東西:設定、session factory、時鐘、ID 產生器、
限流。領域自己的 port(例如相簿的物件儲存)放在該領域的 presentation/dependencies.py。

實際的 adapter 在 lifespan 時掛到 app.state,這裡只負責取出——測試用
dependency_overrides 換成 fake,完全不需要 Redis / R2 / Google。
"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.database import get_session_factory
from app.core.rate_limit import RateLimitCounter, RateLimiter
from app.shared_kernel.ports import Clock, IdGenerator

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_session_factory_dep() -> async_sessionmaker[AsyncSession]:
    return get_session_factory()


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_id_generator(request: Request) -> IdGenerator:
    return request.app.state.id_generator


def get_rate_limit_counter(request: Request) -> RateLimitCounter:
    return request.app.state.rate_limit_counter


def get_rate_limiter(
    counter: Annotated[RateLimitCounter, Depends(get_rate_limit_counter)],
    settings: SettingsDep,
) -> RateLimiter:
    return RateLimiter(
        counter,
        limit=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )


SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory_dep)]
ClockDep = Annotated[Clock, Depends(get_clock)]
IdGeneratorDep = Annotated[IdGenerator, Depends(get_id_generator)]
RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]
