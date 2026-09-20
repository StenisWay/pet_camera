"""PasswordResetTokenRepository 的合約測試(fake 與 SQLAlchemy 各跑一次)。

重點在 mark_used() 的回傳值:同一個連結被點兩次、或兩個請求同時進來時,
只有一次能回 True(02_spec 第 2.4 節的「一次性」)。
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.domains.accounts.application.ports import AccountsUnitOfWork
from app.domains.accounts.domain.entities import PasswordResetToken

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def make_token(owner_id: uuid.UUID, fingerprint: str = "fp:secret-1") -> PasswordResetToken:
    return PasswordResetToken.issue(
        id=uuid.uuid4(), user_id=owner_id, token_hash=fingerprint, now=NOW
    )


async def test_get_by_fingerprint_returns_none_when_absent(
    uow: AccountsUnitOfWork,
) -> None:
    async with uow:
        assert await uow.reset_tokens.get_by_fingerprint("fp:nothing") is None


async def test_added_token_is_retrievable_after_commit(
    uow: AccountsUnitOfWork, owner_id: uuid.UUID
) -> None:
    token = make_token(owner_id)
    async with uow:
        await uow.reset_tokens.add(token)
        await uow.commit()

    async with uow:
        found = await uow.reset_tokens.get_by_fingerprint(token.token_hash)
        assert found is not None
        assert found.id == token.id
        assert found.user_id == owner_id
        assert found.expires_at == NOW + timedelta(minutes=30)


async def test_changes_are_rolled_back_without_commit(
    uow: AccountsUnitOfWork, owner_id: uuid.UUID
) -> None:
    token = make_token(owner_id)
    async with uow:
        await uow.reset_tokens.add(token)

    async with uow:
        assert await uow.reset_tokens.get_by_fingerprint(token.token_hash) is None


async def test_mark_used_succeeds_once_and_then_reports_no_op(
    uow: AccountsUnitOfWork, owner_id: uuid.UUID
) -> None:
    token = make_token(owner_id)
    async with uow:
        await uow.reset_tokens.add(token)
        await uow.commit()

    async with uow:
        assert await uow.reset_tokens.mark_used(token.id, used_at=NOW) is True
        await uow.commit()

    async with uow:
        assert await uow.reset_tokens.mark_used(token.id, used_at=NOW) is False


async def test_marking_an_unknown_token_reports_no_op(uow: AccountsUnitOfWork) -> None:
    async with uow:
        assert await uow.reset_tokens.mark_used(uuid.uuid4(), used_at=NOW) is False


async def test_used_token_is_no_longer_usable(
    uow: AccountsUnitOfWork, owner_id: uuid.UUID
) -> None:
    token = make_token(owner_id)
    async with uow:
        await uow.reset_tokens.add(token)
        await uow.commit()
    async with uow:
        await uow.reset_tokens.mark_used(token.id, used_at=NOW)
        await uow.commit()

    async with uow:
        found = await uow.reset_tokens.get_by_fingerprint(token.token_hash)
    assert found is not None
    assert found.used_at == NOW
