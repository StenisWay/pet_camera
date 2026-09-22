"""ChangePassword use case。

規格:05_spec_帳號設定.md 第 2.1 節(修改密碼 / 設定密碼)。
"""

import pytest

from app.domains.accounts.application.dtos import ChangePasswordCommand
from app.domains.accounts.application.use_cases.change_password import ChangePassword
from app.domains.accounts.domain.entities import User
from app.domains.accounts.domain.exceptions import (
    AccountNotFound,
    InvalidCurrentPassword,
    WeakPassword,
)
from app.domains.accounts.domain.value_objects import Email, RawPassword
from tests.domains.accounts.application.conftest import NOW
from tests.domains.accounts.fakes import (
    FakeAccountsUnitOfWork,
    FakePasswordHasher,
    FakeSessionService,
    FixedClock,
    SequentialIdGenerator,
)

CURRENT = "correct1"
NEW = "brandnew2"


@pytest.fixture
def use_case(
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    clock: FixedClock,
    sessions: FakeSessionService,
) -> ChangePassword:
    return ChangePassword(uow, hasher=hasher, clock=clock, sessions=sessions)


async def seed(
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
    *,
    with_password: bool = True,
) -> User:
    user = User(
        id=ids.new_id(),
        email=Email.parse("owner@example.com"),
        password_hash=hasher.hash(RawPassword.parse(CURRENT)) if with_password else None,
        failed_login_attempts=0,
        locked_until=None,
        created_at=NOW,
    )
    async with uow:
        await uow.users.add(user)
        await uow.commit()
    return user


async def test_changing_the_password_with_the_correct_current_one(
    use_case: ChangePassword,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    user = await seed(uow, hasher, ids)

    await use_case.execute(
        ChangePasswordCommand(user_id=user.id, current_password=CURRENT, new_password=NEW)
    )

    async with uow:
        stored = await uow.users.get(user.id)
    assert stored is not None
    stored.authenticate(RawPassword.parse(NEW), hasher=hasher, now=NOW)


async def test_wrong_current_password_raises_auth_008_and_changes_nothing(
    use_case: ChangePassword,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    user = await seed(uow, hasher, ids)
    before = uow.commits

    with pytest.raises(InvalidCurrentPassword) as exc_info:
        await use_case.execute(
            ChangePasswordCommand(
                user_id=user.id, current_password="wrong123", new_password=NEW
            )
        )

    assert exc_info.value.code == "AUTH_008"
    assert uow.commits == before


async def test_oauth_only_account_sets_a_password_without_the_current_one(
    use_case: ChangePassword,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    """05_spec 第 2.1 節:password_hash 為 null 時顯示「設定密碼」。"""
    user = await seed(uow, hasher, ids, with_password=False)

    await use_case.execute(
        ChangePasswordCommand(user_id=user.id, current_password=None, new_password=NEW)
    )

    async with uow:
        stored = await uow.users.get(user.id)
    assert stored is not None
    assert stored.has_password() is True


async def test_account_with_a_password_must_supply_the_current_one(
    use_case: ChangePassword,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    user = await seed(uow, hasher, ids)

    with pytest.raises(InvalidCurrentPassword):
        await use_case.execute(
            ChangePasswordCommand(user_id=user.id, current_password=None, new_password=NEW)
        )


async def test_other_sessions_are_revoked_but_the_current_one_survives(
    use_case: ChangePassword,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
    sessions: FakeSessionService,
) -> None:
    """05_spec 第 2.1 節:改密碼的動機常是懷疑外洩,不撤銷等於沒效果;
    但也不該把剛改完密碼的使用者自己踢回登入頁。"""
    user = await seed(uow, hasher, ids)

    await use_case.execute(
        ChangePasswordCommand(
            user_id=user.id,
            current_password=CURRENT,
            new_password=NEW,
            current_refresh_token="this-tabs-refresh-token",
        )
    )

    assert sessions.revoked == [(user.id, "this-tabs-refresh-token")]


async def test_weak_new_password_is_rejected(
    use_case: ChangePassword,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    user = await seed(uow, hasher, ids)

    with pytest.raises(WeakPassword) as exc_info:
        await use_case.execute(
            ChangePasswordCommand(
                user_id=user.id, current_password=CURRENT, new_password="short"
            )
        )
    assert exc_info.value.code == "AUTH_006"


async def test_unknown_user_is_rejected(
    use_case: ChangePassword, ids: SequentialIdGenerator
) -> None:
    """token 有效但帳號已被刪除:不是 401,是這個 token 指向的東西不存在了。"""
    with pytest.raises(AccountNotFound):
        await use_case.execute(
            ChangePasswordCommand(
                user_id=ids.new_id(), current_password=CURRENT, new_password=NEW
            )
        )
