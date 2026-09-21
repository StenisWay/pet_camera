"""OAuthStateStore 的 Redis 實作(VM-3 上的共用單例,13_ADR 第 1.1 節)。

key 形狀與 TTL 見 01_資料模型與儲存規格.md 第 7 節的用途表;state 是一次性的。
"""

import uuid

import redis.asyncio as redis

from app.domains.drive_export.application.ports import OAuthStateStore

OAUTH_STATE_KEY = "drive:oauth:state:{state}"


class RedisOAuthStateStore(OAuthStateStore):
    def __init__(self, url: str) -> None:
        # from_url 不會馬上連線,第一次下指令時才建立連線
        self._client = redis.from_url(url, decode_responses=True)

    async def issue(self, state: str, owner_id: uuid.UUID, *, ttl_seconds: int) -> None:
        await self._client.set(
            OAUTH_STATE_KEY.format(state=state), str(owner_id), ex=ttl_seconds
        )

    async def consume(self, state: str) -> uuid.UUID | None:
        # GETDEL:取出並作廢是一個原子操作,兩個同時進來的回呼只有一個會拿到
        value = await self._client.getdel(OAUTH_STATE_KEY.format(state=state))
        return uuid.UUID(str(value)) if value else None

    async def aclose(self) -> None:
        await self._client.aclose()
