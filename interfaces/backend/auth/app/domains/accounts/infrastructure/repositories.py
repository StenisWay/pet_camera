"""accounts 的 repository 正式實作。

與 tests/domains/accounts/fakes.py 的 fake 是同一份合約的兩個實作,
由 tests/domains/accounts/contracts/ 的合約測試保證行為一致。

repository 只 flush,不 commit——交易邊界由 UnitOfWork 決定。
"""

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.accounts.domain.entities import PasswordResetToken, User
from app.domains.accounts.domain.exceptions import EmailAlreadyRegistered
from app.domains.accounts.domain.repositories import (
    PasswordResetTokenRepository,
    UserRepository,
)
from app.domains.accounts.domain.value_objects import Email
from app.domains.accounts.infrastructure.mappers import (
    apply_user_to_row,
    reset_token_to_entity,
    reset_token_to_new_row,
    user_to_entity,
    user_to_new_row,
)
from app.domains.accounts.infrastructure.orm import PasswordResetTokenRow, UserRow


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        row = await self.session.get(UserRow, user_id)
        return user_to_entity(row) if row is not None else None

    async def get_by_email(self, email: Email) -> User | None:
        row = (
            await self.session.execute(select(UserRow).where(UserRow.email == email.value))
        ).scalar_one_or_none()
        return user_to_entity(row) if row is not None else None

    async def add(self, user: User) -> None:
        self.session.add(user_to_new_row(user))
        try:
            # 用 savepoint 包住:唯一約束違反會讓整個交易進入 aborted 狀態,
            # 沒有 savepoint 的話呼叫端就算捕捉了例外也無法繼續用這個 session
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raise EmailAlreadyRegistered() from exc

    async def save(self, user: User) -> None:
        row = await self.session.get(UserRow, user.id)
        if row is None:
            return
        apply_user_to_row(user, row)
        await self.session.flush()

    async def delete(self, user_id: uuid.UUID) -> None:
        row = await self.session.get(UserRow, user_id)
        if row is None:
            return
        # 三張子表由外鍵 ON DELETE CASCADE 帶走(01_資料模型 第 6 節)
        await self.session.delete(row)
        await self.session.flush()


class SqlAlchemyPasswordResetTokenRepository(PasswordResetTokenRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_fingerprint(self, fingerprint: str) -> PasswordResetToken | None:
        row = (
            await self.session.execute(
                select(PasswordResetTokenRow).where(
                    PasswordResetTokenRow.token_hash == fingerprint
                )
            )
        ).scalar_one_or_none()
        return reset_token_to_entity(row) if row is not None else None

    async def add(self, token: PasswordResetToken) -> None:
        self.session.add(reset_token_to_new_row(token))
        await self.session.flush()

    async def mark_used(self, token_id: uuid.UUID, *, used_at: datetime) -> bool:
        """條件更新:`used_at is null` 是判斷依據,影響列數就是仲裁結果。

        先讀再寫會有競態——兩個請求可能同時讀到「還沒用過」。
        """
        result = cast(
            "CursorResult[Any]",
            await self.session.execute(
                update(PasswordResetTokenRow)
                .where(
                    PasswordResetTokenRow.id == token_id,
                    PasswordResetTokenRow.used_at.is_(None),
                )
                .values(used_at=used_at)
            ),
        )
        return result.rowcount == 1
