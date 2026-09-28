"""測試替身:有真實行為的 fake,不是 mock。

明確繼承正式介面,與 infrastructure 的實作是「同一份合約的兩個實作」,
由 tests/domains/push_tokens/contracts/ 的合約測試保證兩者行為一致。
"""

import copy
import uuid
from types import TracebackType
from typing import Self

from app.domains.push_tokens.application.ports import PushTokensUnitOfWork
from app.domains.push_tokens.domain.entities import ClientPlatform, PushToken
from app.domains.push_tokens.domain.repositories import PushTokenRepository


class FakePushTokenRepository(PushTokenRepository):
    def __init__(self) -> None:
        self.committed: dict[uuid.UUID, PushToken] = {}
        self.pending: dict[uuid.UUID, PushToken] = {}
        self.deleted: set[uuid.UUID] = set()

    def _visible(self) -> dict[uuid.UUID, PushToken]:
        merged = {**self.committed, **self.pending}
        return {k: v for k, v in merged.items() if k not in self.deleted}

    async def get(self, push_token_id: uuid.UUID) -> PushToken | None:
        # 回傳複本:模擬「從資料庫載入」,忘了 save 的修改不會被保存
        return copy.deepcopy(self._visible().get(push_token_id))

    async def find_by_endpoint(self, platform: ClientPlatform, token: str) -> PushToken | None:
        for registration in self._visible().values():
            if registration.platform is platform and registration.token == token:
                return copy.deepcopy(registration)
        return None

    async def list_by_user(self, user_id: uuid.UUID) -> list[PushToken]:
        mine = [t for t in self._visible().values() if t.user_id == user_id]
        return [copy.deepcopy(t) for t in sorted(mine, key=lambda t: (t.created_at, t.id))]

    async def save(self, push_token: PushToken) -> PushToken:
        existing = await self.find_by_endpoint(push_token.platform, push_token.token)
        if existing is not None and existing.id != push_token.id:
            existing.rebind_to(push_token.user_id)
            push_token = existing
        self.pending[push_token.id] = copy.deepcopy(push_token)
        self.deleted.discard(push_token.id)
        return copy.deepcopy(push_token)

    async def delete(self, push_token_id: uuid.UUID) -> None:
        self.deleted.add(push_token_id)


class FakePushTokensUnitOfWork(PushTokensUnitOfWork):
    def __init__(self) -> None:
        self.tokens = FakePushTokenRepository()
        self.commit_count = 0
        # 模擬 VM-3 的 Postgres 連不到(審查 #12)
        self.unavailable: BaseException | None = None

    async def __aenter__(self) -> Self:
        if self.unavailable is not None:
            raise self.unavailable
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # 未 commit 的變更丟棄 = rollback
        self.tokens.pending.clear()
        self.tokens.deleted.clear()

    async def commit(self) -> None:
        self.tokens.committed.update(self.tokens.pending)
        for push_token_id in self.tokens.deleted:
            self.tokens.committed.pop(push_token_id, None)
        self.tokens.pending.clear()
        self.tokens.deleted.clear()
        self.commit_count += 1

    def given(self, push_token: PushToken) -> PushToken:
        """Arrange 用:直接放入已提交的資料。"""
        self.tokens.committed[push_token.id] = copy.deepcopy(push_token)
        return push_token
