"""UserRepository 的合約測試。

介面 docstring 寫下的行為承諾,逐條在這裡驗證。同一份測試之後會再跑一次
SQLAlchemy 實作(tests/domains/accounts/infrastructure/),這樣「application 用 fake
測出來的綠燈」才可信——fake 跟正式實作行為不一致的話,這裡就會紅。
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.domains.accounts.domain.entities import User
from app.domains.accounts.domain.exceptions import EmailAlreadyRegistered
from app.domains.accounts.domain.value_objects import Email
from tests.domains.accounts.fakes import FakeAccountsUnitOfWork

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


@pytest.fixture
def uow() -> FakeAccountsUnitOfWork:
    return FakeAccountsUnitOfWork()


def make_user(email: str = "owner@example.com") -> User:
    return User(
        id=uuid.uuid4(),
        email=Email.parse(email),
        password_hash="hashed:correct1",
        failed_login_attempts=0,
        locked_until=None,
        created_at=NOW,
    )


async def test_get_by_email_returns_none_when_absent(uow: FakeAccountsUnitOfWork) -> None:
    async with uow:
        assert await uow.users.get_by_email(Email.parse("nobody@example.com")) is None


async def test_added_user_is_retrievable_after_commit(uow: FakeAccountsUnitOfWork) -> None:
    user = make_user()
    async with uow:
        await uow.users.add(user)
        await uow.commit()

    async with uow:
        found = await uow.users.get_by_email(user.email)
        assert found is not None
        assert found.id == user.id


async def test_changes_are_rolled_back_without_commit(uow: FakeAccountsUnitOfWork) -> None:
    user = make_user()
    async with uow:
        await uow.users.add(user)
        # 刻意不 commit

    async with uow:
        assert await uow.users.get_by_email(user.email) is None


async def test_adding_a_duplicate_email_raises_the_domain_conflict(
    uow: FakeAccountsUnitOfWork,
) -> None:
    """§2.2:唯一性靠約束,不靠先查再寫;衝突要以領域例外的形式浮現。"""
    async with uow:
        await uow.users.add(make_user("dup@example.com"))
        await uow.commit()

    async with uow:
        with pytest.raises(EmailAlreadyRegistered):
            await uow.users.add(make_user("dup@example.com"))


async def test_saving_a_user_persists_the_lockout_counters(
    uow: FakeAccountsUnitOfWork,
) -> None:
    user = make_user()
    async with uow:
        await uow.users.add(user)
        await uow.commit()

    async with uow:
        loaded = await uow.users.get(user.id)
        assert loaded is not None
        loaded.failed_login_attempts = 3
        loaded.locked_until = NOW + timedelta(minutes=15)
        await uow.users.save(loaded)
        await uow.commit()

    async with uow:
        reloaded = await uow.users.get(user.id)
        assert reloaded is not None
        assert reloaded.failed_login_attempts == 3
        assert reloaded.locked_until == NOW + timedelta(minutes=15)


async def test_modifying_a_loaded_user_without_save_does_not_persist(
    uow: FakeAccountsUnitOfWork,
) -> None:
    """get() 回傳的是新物件;忘了 save 就不算數——這條讓漏 save 在測試就被抓到。"""
    user = make_user()
    async with uow:
        await uow.users.add(user)
        await uow.commit()

    async with uow:
        loaded = await uow.users.get(user.id)
        assert loaded is not None
        loaded.failed_login_attempts = 99
        await uow.commit()

    async with uow:
        reloaded = await uow.users.get(user.id)
        assert reloaded is not None
        assert reloaded.failed_login_attempts == 0


async def test_deleting_a_user_removes_it(uow: FakeAccountsUnitOfWork) -> None:
    user = make_user()
    async with uow:
        await uow.users.add(user)
        await uow.commit()

    async with uow:
        await uow.users.delete(user.id)
        await uow.commit()

    async with uow:
        assert await uow.users.get(user.id) is None
