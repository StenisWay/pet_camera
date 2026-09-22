"""RegisterUser use case。

規格:02_spec_登入註冊與密碼重設.md 第 2.2 節。
畫面規格(screens/*/01_page_登入註冊忘記密碼.md)明訂註冊成功導回登入頁、
不自動登入,所以本 use case 不簽發任何 token。
"""

import pytest

from app.domains.accounts.application.dtos import RegisterUserCommand
from app.domains.accounts.application.use_cases.register_user import RegisterUser
from app.domains.accounts.domain.exceptions import (
    EmailAlreadyRegistered,
    InvalidEmail,
    WeakPassword,
)
from app.domains.accounts.domain.value_objects import Email
from tests.domains.accounts.fakes import (
    FakeAccountsUnitOfWork,
    FakePasswordHasher,
    FixedClock,
    SequentialIdGenerator,
)


@pytest.fixture
def use_case(
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    clock: FixedClock,
    ids: SequentialIdGenerator,
) -> RegisterUser:
    return RegisterUser(uow, hasher=hasher, clock=clock, ids=ids)


async def test_registering_stores_the_user_and_commits_once(
    use_case: RegisterUser, uow: FakeAccountsUnitOfWork
) -> None:
    result = await use_case.execute(
        RegisterUserCommand(email="New@Example.com", password="abcd1234")
    )

    assert result.email == "new@example.com"
    assert uow.commits == 1
    async with uow:
        stored = await uow.users.get(result.user_id)
    assert stored is not None
    assert stored.email == Email.parse("new@example.com")


async def test_the_plaintext_password_is_never_stored(
    use_case: RegisterUser, uow: FakeAccountsUnitOfWork
) -> None:
    result = await use_case.execute(
        RegisterUserCommand(email="new@example.com", password="abcd1234")
    )
    async with uow:
        stored = await uow.users.get(result.user_id)
    assert stored is not None
    assert stored.password_hash is not None
    assert "abcd1234" != stored.password_hash


async def test_duplicate_email_raises_auth_004_and_does_not_commit(
    use_case: RegisterUser, uow: FakeAccountsUnitOfWork
) -> None:
    await use_case.execute(RegisterUserCommand(email="dup@example.com", password="abcd1234"))
    assert uow.commits == 1

    with pytest.raises(EmailAlreadyRegistered) as exc_info:
        await use_case.execute(
            RegisterUserCommand(email="dup@example.com", password="other567")
        )
    assert exc_info.value.code == "AUTH_004"
    assert uow.commits == 1  # 第二次沒有提交任何東西


async def test_email_differing_only_in_case_is_the_same_account(
    use_case: RegisterUser, uow: FakeAccountsUnitOfWork
) -> None:
    """§2.1 Email 正規化:否則 A@x.com 會撞上 DB 的 CHECK 約束而回 SRV_001。"""
    await use_case.execute(RegisterUserCommand(email="a@x.com", password="abcd1234"))
    with pytest.raises(EmailAlreadyRegistered):
        await use_case.execute(RegisterUserCommand(email="  A@X.COM ", password="abcd1234"))


async def test_weak_password_is_rejected_before_anything_is_written(
    use_case: RegisterUser, uow: FakeAccountsUnitOfWork
) -> None:
    with pytest.raises(WeakPassword):
        await use_case.execute(RegisterUserCommand(email="new@example.com", password="short"))
    assert uow.commits == 0


async def test_malformed_email_is_rejected(use_case: RegisterUser) -> None:
    with pytest.raises(InvalidEmail):
        await use_case.execute(RegisterUserCommand(email="not-an-email", password="abcd1234"))
