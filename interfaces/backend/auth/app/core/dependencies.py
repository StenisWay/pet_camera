"""兩個領域共用的 provider。

放 core 而不是某個領域的 presentation:時間、ID、亂數、資料庫連線不屬於
accounts 也不屬於 sessions,而「accounts 的組裝點 import sessions 的組裝點」
會直接違反跨領域規則(tools/check_layers.py 規則 4)。

同一個請求裡兩個領域必須看到**同一個**時鐘:各自 new 一個 SystemClock 會在
跨秒的邊界上產生莫名其妙的差異(例如簽出來的 iat 比 refresh token 的 created_at 早一秒)。
"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rate_limit import RateLimitCounter
from app.core.system import Sha256TokenFactory, SystemClock, Uuid7Generator
from app.shared_kernel.ports import Clock, IdGenerator, OpaqueTokenFactory


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """engine 與 session factory 在 lifespan 建立一次;provider 只取出來。"""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return factory


def get_rate_limit_counter(request: Request) -> RateLimitCounter:
    counter: RateLimitCounter = request.app.state.rate_limit_counter
    return counter


def get_clock() -> Clock:
    return SystemClock()


def get_id_generator() -> IdGenerator:
    return Uuid7Generator()


def get_token_factory() -> OpaqueTokenFactory:
    return Sha256TokenFactory()


SessionFactoryDep = Annotated[
    async_sessionmaker[AsyncSession], Depends(get_session_factory)
]
RateLimitCounterDep = Annotated[RateLimitCounter, Depends(get_rate_limit_counter)]
ClockDep = Annotated[Clock, Depends(get_clock)]
IdsDep = Annotated[IdGenerator, Depends(get_id_generator)]
TokensDep = Annotated[OpaqueTokenFactory, Depends(get_token_factory)]
