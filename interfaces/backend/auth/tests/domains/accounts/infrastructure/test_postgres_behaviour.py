"""只有真實 PostgreSQL 能驗的事。

合約測試已經涵蓋了「repository 該有什麼行為」;這裡驗的是**資料庫本身**的保證:
CHECK 約束、ON DELETE CASCADE、timestamptz 的時區還原、條件 UPDATE 的併發仲裁。
用 SQLite 跑這些會綠,但綠得毫無意義——它對這四件事的語意都不一樣。

沒設 AUTH_TEST_DATABASE_URL 時整組跳過。
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.accounts.domain.entities import User
from app.domains.accounts.domain.exceptions import EmailAlreadyRegistered
from app.domains.accounts.domain.value_objects import Email
from app.domains.accounts.infrastructure.orm import PasswordResetTokenRow, UserRow
from app.domains.accounts.infrastructure.unit_of_work import SqlAlchemyAccountsUnitOfWork
from app.domains.sessions.domain.entities import RefreshToken, RevocationReason
from app.domains.sessions.infrastructure.orm import RefreshTokenRow
from app.domains.sessions.infrastructure.unit_of_work import SqlAlchemySessionsUnitOfWork
from tests.database import postgres_session_factory, requires_postgres

pytestmark = requires_postgres

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async with postgres_session_factory() as factory:
        yield factory


def make_user(email: str = "owner@example.com") -> User:
    return User(
        id=uuid.uuid4(),
        email=Email.parse(email),
        password_hash="hashed",
        failed_login_attempts=0,
        locked_until=None,
        created_at=NOW,
    )


async def test_uppercase_email_violates_the_check_constraint(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """01_資料模型 第 2.1 節的 CHECK 是最後一道防線:漏了正規化就直接失敗,
    而不是安靜地產生 A@x.com 與 a@x.com 兩個帳號。"""
    async with session_factory() as session:
        session.add(
            UserRow(
                id=uuid.uuid4(),
                email="NotLowered@Example.com",
                password_hash=None,
                failed_login_attempts=0,
                locked_until=None,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_duplicate_email_surfaces_as_a_domain_error(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """IntegrityError 不該漏到 application 層——那是 SQLAlchemy 的詞彙。"""
    uow = SqlAlchemyAccountsUnitOfWork(session_factory)
    async with uow:
        await uow.users.add(make_user("dup@example.com"))
        await uow.commit()

    async with uow:
        with pytest.raises(EmailAlreadyRegistered):
            await uow.users.add(make_user("dup@example.com"))


async def test_the_session_is_still_usable_after_a_duplicate(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """唯一約束違反會讓交易進入 aborted 狀態;repository 用 savepoint 包住,
    呼叫端捕捉例外後才有辦法繼續。"""
    uow = SqlAlchemyAccountsUnitOfWork(session_factory)
    async with uow:
        await uow.users.add(make_user("taken@example.com"))
        await uow.commit()

    async with uow:
        with pytest.raises(EmailAlreadyRegistered):
            await uow.users.add(make_user("taken@example.com"))
        # 同一個交易裡換一個沒被用掉的 email,仍然要能成功
        await uow.users.add(make_user("free@example.com"))
        await uow.commit()

    async with uow:
        assert await uow.users.get_by_email(Email.parse("free@example.com")) is not None


async def test_locked_until_round_trips_with_its_timezone(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """01_資料模型 第 2.0 節:timestamptz,以 UTC 儲存。存進去是 +08:00 的時間,
    取出來必須是同一個瞬間,而不是少了八小時的裸時間。"""
    taipei = timezone(timedelta(hours=8))
    locked_until = datetime(2026, 9, 20, 20, 30, tzinfo=taipei)

    uow = SqlAlchemyAccountsUnitOfWork(session_factory)
    user = make_user()
    async with uow:
        await uow.users.add(user)
        await uow.commit()

    async with uow:
        loaded = await uow.users.get(user.id)
        assert loaded is not None
        loaded.locked_until = locked_until
        loaded.failed_login_attempts = 5
        await uow.users.save(loaded)
        await uow.commit()

    async with uow:
        reloaded = await uow.users.get(user.id)
    assert reloaded is not None
    assert reloaded.locked_until is not None
    assert reloaded.locked_until == locked_until
    assert reloaded.locked_until.utcoffset() is not None


async def test_deleting_a_user_cascades_to_its_child_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """01_資料模型 第 6 節:refresh_tokens 與 password_reset_tokens 由外鍵帶走,
    所以 DeleteAccount 不必逐一清理——這條測試就是那個假設的依據。"""
    uow = SqlAlchemyAccountsUnitOfWork(session_factory)
    user = make_user()
    async with uow:
        await uow.users.add(user)
        await uow.commit()

    async with session_factory() as session:
        session.add(
            RefreshTokenRow(
                id=uuid.uuid4(),
                user_id=user.id,
                token_hash="fp:refresh",
                expires_at=NOW + timedelta(days=30),
                revoked_at=None,
                revoked_reason=None,
            )
        )
        session.add(
            PasswordResetTokenRow(
                id=uuid.uuid4(),
                user_id=user.id,
                token_hash="fp:reset",
                expires_at=NOW + timedelta(minutes=30),
                used_at=None,
            )
        )
        await session.commit()

    async with uow:
        await uow.users.delete(user.id)
        await uow.commit()

    async with session_factory() as session:
        refresh_rows = (await session.execute(select(RefreshTokenRow))).scalars().all()
        reset_rows = (await session.execute(select(PasswordResetTokenRow))).scalars().all()
    assert refresh_rows == []
    assert reset_rows == []


async def test_concurrent_revoke_lets_exactly_one_transaction_win(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """審查 #11:一個 refresh token 不得換出兩組有效 token。

    兩個**真的並行**的交易同時條件 UPDATE 同一列,PostgreSQL 會讓後到的那個
    等待、然後看到 revoked_at 已經不是 NULL,於是影響 0 列。
    """
    accounts = SqlAlchemyAccountsUnitOfWork(session_factory)
    user = make_user()
    async with accounts:
        await accounts.users.add(user)
        await accounts.commit()

    token = RefreshToken.issue(
        id=uuid.uuid4(), user_id=user.id, token_hash="fp:contended", now=NOW
    )
    seed = SqlAlchemySessionsUnitOfWork(session_factory)
    async with seed:
        await seed.refresh_tokens.add(token)
        await seed.commit()

    async def revoke() -> bool:
        uow = SqlAlchemySessionsUnitOfWork(session_factory)
        async with uow:
            won = await uow.refresh_tokens.revoke(
                token.id, revoked_at=NOW, reason=RevocationReason.ROTATED
            )
            await uow.commit()
        return won

    results = await asyncio.gather(revoke(), revoke())
    assert sorted(results) == [False, True]


async def test_the_partial_index_on_unused_reset_tokens_exists(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """部分索引是 01_資料模型 第 2.9 節明寫的;建錯了查詢會全表掃描而沒人發現。"""
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "select indexdef from pg_indexes "
                    "where tablename = 'password_reset_tokens' "
                    "and indexname = 'ix_password_reset_tokens_user_id_unused'"
                )
            )
        ).scalars().all()
    assert len(rows) == 1
    assert "used_at IS NULL" in rows[0].replace("is null", "IS NULL")
