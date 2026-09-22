"""sessions 的 repository 正式實作。

revoke 與 revoke_all_for_user 都是**條件更新**,回傳 rowcount:
rotation 的併發仲裁完全靠這個值(02_spec 第 2.3.1 節、規格審查 #11)。
先讀後寫會有競態——兩個請求可能同時讀到「還沒撤銷」,於是各自換出一組有效 token。
"""

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.sessions.domain.entities import RefreshToken, RevocationReason
from app.domains.sessions.domain.repositories import RefreshTokenRepository
from app.domains.sessions.infrastructure.orm import RefreshTokenRow


def _to_entity(row: RefreshTokenRow) -> RefreshToken:
    return RefreshToken(
        id=row.id,
        user_id=row.user_id,
        token_hash=row.token_hash,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
        revoked_reason=(
            RevocationReason(row.revoked_reason) if row.revoked_reason else None
        ),
    )


class SqlAlchemyRefreshTokenRepository(RefreshTokenRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_fingerprint(self, fingerprint: str) -> RefreshToken | None:
        row = (
            await self.session.execute(
                select(RefreshTokenRow).where(RefreshTokenRow.token_hash == fingerprint)
            )
        ).scalar_one_or_none()
        return _to_entity(row) if row is not None else None

    async def add(self, token: RefreshToken) -> None:
        self.session.add(
            RefreshTokenRow(
                id=token.id,
                user_id=token.user_id,
                token_hash=token.token_hash,
                expires_at=token.expires_at,
                revoked_at=token.revoked_at,
                revoked_reason=(
                    token.revoked_reason.value if token.revoked_reason else None
                ),
            )
        )
        await self.session.flush()

    async def revoke(
        self, token_id: uuid.UUID, *, revoked_at: datetime, reason: RevocationReason
    ) -> bool:
        result = cast(
            "CursorResult[Any]",
            await self.session.execute(
                update(RefreshTokenRow)
                .where(
                    RefreshTokenRow.id == token_id,
                    RefreshTokenRow.revoked_at.is_(None),
                )
                .values(revoked_at=revoked_at, revoked_reason=reason.value)
            ),
        )
        return result.rowcount == 1

    async def revoke_all_for_user(
        self,
        user_id: uuid.UUID,
        *,
        revoked_at: datetime,
        reason: RevocationReason,
        except_token_id: uuid.UUID | None = None,
    ) -> int:
        statement = (
            update(RefreshTokenRow)
            .where(
                RefreshTokenRow.user_id == user_id,
                RefreshTokenRow.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at, revoked_reason=reason.value)
        )
        if except_token_id is not None:
            statement = statement.where(RefreshTokenRow.id != except_token_id)
        result = cast("CursorResult[Any]", await self.session.execute(statement))
        return int(result.rowcount)

    async def delete_all_for_user(self, user_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(RefreshTokenRow).where(RefreshTokenRow.user_id == user_id)
        )
        await self.session.flush()
