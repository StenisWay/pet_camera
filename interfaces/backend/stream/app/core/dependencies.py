"""全服務共用的 provider。

這裡只放「不屬於任何一個領域」的東西:設定、時鐘、ID 產生器、限流。
領域自己的 port(session 儲存、TURN 簽發、Device 查詢、signaling 喚醒)放在
該領域的 presentation/dependencies.py。

實際的 adapter 在 lifespan 時掛到 app.state,這裡只負責取出——測試用
dependency_overrides 換成 fake,完全不需要 Redis 或 TURN server。
"""

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.rate_limit import RateLimitCounter, RateLimiter
from app.shared_kernel.ports import Clock, IdGenerator

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_id_generator(request: Request) -> IdGenerator:
    return request.app.state.id_generator


def get_rate_limit_counter(request: Request) -> RateLimitCounter:
    return request.app.state.rate_limit_counter


def get_session_rate_limiter(
    counter: Annotated[RateLimitCounter, Depends(get_rate_limit_counter)],
    settings: SettingsDep,
) -> RateLimiter:
    """只掛在 POST .../stream/session 上(規格審查 #10)。

    offer 與 candidate 是 ICE 協商期間的高頻往返,套同一個「每分鐘 10 次」會把
    正常連線擋掉——限流的對象是「開新直播」這個昂貴動作,不是 signaling 封包。
    """
    return RateLimiter(
        counter,
        limit=settings.session_rate_limit_requests,
        window_seconds=settings.session_rate_limit_window_seconds,
    )


ClockDep = Annotated[Clock, Depends(get_clock)]
IdGeneratorDep = Annotated[IdGenerator, Depends(get_id_generator)]
SessionRateLimiterDep = Annotated[RateLimiter, Depends(get_session_rate_limiter)]
