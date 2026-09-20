"""sessions 的測試替身。明確繼承正式介面,與 SQLAlchemy 實作跑同一份合約測試。"""

import copy
import uuid
from datetime import datetime
from typing import Self

from app.domains.sessions.application.ports import AccessTokenSigner, SessionsUnitOfWork
from app.domains.sessions.domain.entities import RefreshToken, RevocationReason
from app.domains.sessions.domain.repositories import RefreshTokenRepository


class FakeRefreshTokenRepository(RefreshTokenRepository):
    def __init__(self, committed: dict[uuid.UUID, RefreshToken]) -> None:
        self._committed = committed
        self.pending: dict[uuid.UUID, RefreshToken] = {}
        self.deleted: set[uuid.UUID] = set()

    def _visible(self) -> dict[uuid.UUID, RefreshToken]:
        merged = {**self._committed, **self.pending}
        return {k: v for k, v in merged.items() if k not in self.deleted}

    async def get_by_fingerprint(self, fingerprint: str) -> RefreshToken | None:
        for token in self._visible().values():
            if token.token_hash == fingerprint:
                return copy.deepcopy(token)
        return None

    async def add(self, token: RefreshToken) -> None:
        self.pending[token.id] = copy.deepcopy(token)

    async def revoke(
        self, token_id: uuid.UUID, *, revoked_at: datetime, reason: RevocationReason
    ) -> bool:
        # 條件更新:只有「目前還沒撤銷」才算這次撤銷成功
        token = self._visible().get(token_id)
        if token is None or token.revoked_at is not None:
            return False
        updated = copy.deepcopy(token)
        updated.revoked_at = revoked_at
        updated.revoked_reason = reason
        self.pending[token_id] = updated
        return True

    async def revoke_all_for_user(
        self,
        user_id: uuid.UUID,
        *,
        revoked_at: datetime,
        reason: RevocationReason,
        except_token_id: uuid.UUID | None = None,
    ) -> int:
        revoked = 0
        for token in list(self._visible().values()):
            if token.user_id != user_id or token.revoked_at is not None:
                continue
            if except_token_id is not None and token.id == except_token_id:
                continue
            updated = copy.deepcopy(token)
            updated.revoked_at = revoked_at
            updated.revoked_reason = reason
            self.pending[token.id] = updated
            revoked += 1
        return revoked

    async def delete_all_for_user(self, user_id: uuid.UUID) -> None:
        for token in list(self._visible().values()):
            if token.user_id == user_id:
                self.deleted.add(token.id)


class FakeSessionsUnitOfWork(SessionsUnitOfWork):
    refresh_tokens: FakeRefreshTokenRepository

    def __init__(self) -> None:
        self._store: dict[uuid.UUID, RefreshToken] = {}
        self.commits = 0
        self.refresh_tokens = FakeRefreshTokenRepository(self._store)

    async def __aenter__(self) -> Self:
        self.refresh_tokens = FakeRefreshTokenRepository(self._store)
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.refresh_tokens.pending.clear()

    async def commit(self) -> None:
        self.commits += 1
        self._store.update(self.refresh_tokens.pending)
        for token_id in self.refresh_tokens.deleted:
            self._store.pop(token_id, None)
        self.refresh_tokens.pending.clear()


class FakeAccessTokenSigner(AccessTokenSigner):
    """把 claims 原樣記下來,測試可以直接斷言簽了什麼,不必解 JWT。"""

    def __init__(self) -> None:
        self.signed: list[dict[str, str | int]] = []

    def sign(self, claims: dict[str, str | int]) -> str:
        self.signed.append(dict(claims))
        return f"signed:{claims['sub']}:{claims['iat']}"
