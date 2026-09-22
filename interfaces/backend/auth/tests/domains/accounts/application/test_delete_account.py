"""DeleteAccount use case。

規格:05_spec_帳號設定.md 第 2.2 節、01_資料模型與儲存規格.md 第 6 節(規格審查 #5)。

串聯順序是 Device → Album → 刪 users,**全部成功才刪帳號**。任一步失敗就整個
操作失敗、帳號維持可用,符合 13_ADR 第 4 節「Auth 一律選一致性(C)」。
"""

import pytest

from app.domains.accounts.application.dtos import DeleteAccountCommand
from app.domains.accounts.application.use_cases.delete_account import DeleteAccount
from app.domains.accounts.domain.entities import User
from app.domains.accounts.domain.exceptions import (
    AccountNotFound,
    DeleteConfirmationMismatch,
    InvalidCurrentPassword,
)
from app.domains.accounts.domain.value_objects import Email, RawPassword
from app.shared_kernel.errors import ServiceUnavailable
from tests.domains.accounts.application.conftest import NOW
from tests.domains.accounts.fakes import (
    FakeAccountPurger,
    FakeAccountsUnitOfWork,
    FakePasswordHasher,
    FixedClock,
    SequentialIdGenerator,
)

EMAIL = "owner@example.com"
PASSWORD = "correct1"


def build(
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    clock: FixedClock,
    purgers: list[FakeAccountPurger],
) -> DeleteAccount:
    return DeleteAccount(uow, hasher=hasher, clock=clock, purgers=purgers)


@pytest.fixture
def use_case(
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    clock: FixedClock,
    device_purger: FakeAccountPurger,
    album_purger: FakeAccountPurger,
) -> DeleteAccount:
    return build(uow, hasher, clock, [device_purger, album_purger])


async def seed(
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
    *,
    with_password: bool = True,
) -> User:
    user = User(
        id=ids.new_id(),
        email=Email.parse(EMAIL),
        password_hash=hasher.hash(RawPassword.parse(PASSWORD)) if with_password else None,
        failed_login_attempts=0,
        locked_until=None,
        created_at=NOW,
    )
    async with uow:
        await uow.users.add(user)
        await uow.commit()
    return user


async def test_deleting_purges_other_services_first_then_the_account(
    use_case: DeleteAccount,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
    device_purger: FakeAccountPurger,
    album_purger: FakeAccountPurger,
) -> None:
    user = await seed(uow, hasher, ids)

    await use_case.execute(DeleteAccountCommand(user_id=user.id, confirmation=PASSWORD))

    assert device_purger.purged == [user.id]
    assert album_purger.purged == [user.id]
    async with uow:
        assert await uow.users.get(user.id) is None


async def test_wrong_password_raises_auth_009_and_purges_nothing(
    use_case: DeleteAccount,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
    device_purger: FakeAccountPurger,
    album_purger: FakeAccountPurger,
) -> None:
    user = await seed(uow, hasher, ids)

    with pytest.raises(InvalidCurrentPassword) as exc_info:
        await use_case.execute(
            DeleteAccountCommand(user_id=user.id, confirmation="wrong123")
        )

    assert exc_info.value.code == "AUTH_009"
    assert device_purger.purged == []
    assert album_purger.purged == []
    async with uow:
        assert await uow.users.get(user.id) is not None


async def test_oauth_only_account_confirms_with_its_email(
    use_case: DeleteAccount,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    """05_spec 第 2.2 節:沒有密碼可輸入時改以 Email 文字比對。"""
    user = await seed(uow, hasher, ids, with_password=False)

    await use_case.execute(
        DeleteAccountCommand(user_id=user.id, confirmation="  Owner@Example.COM ")
    )

    async with uow:
        assert await uow.users.get(user.id) is None


async def test_oauth_only_account_with_a_wrong_email_raises_val_001(
    use_case: DeleteAccount,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    user = await seed(uow, hasher, ids, with_password=False)

    with pytest.raises(DeleteConfirmationMismatch) as exc_info:
        await use_case.execute(
            DeleteAccountCommand(user_id=user.id, confirmation="someone@else.com")
        )
    assert exc_info.value.code == "VAL_001"


async def test_device_purge_failure_leaves_the_account_usable(
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    clock: FixedClock,
    ids: SequentialIdGenerator,
    album_purger: FakeAccountPurger,
) -> None:
    user = await seed(uow, hasher, ids)
    failing = FakeAccountPurger("device", fails=True)
    use_case = build(uow, hasher, clock, [failing, album_purger])

    with pytest.raises(ServiceUnavailable) as exc_info:
        await use_case.execute(DeleteAccountCommand(user_id=user.id, confirmation=PASSWORD))

    assert exc_info.value.code == "SRV_002"
    # 第一步失敗就不該走到第二步
    assert album_purger.purged == []
    async with uow:
        assert await uow.users.get(user.id) is not None


async def test_album_purge_failure_also_keeps_the_account(
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    clock: FixedClock,
    ids: SequentialIdGenerator,
    device_purger: FakeAccountPurger,
) -> None:
    """中間狀態是「帳號還在但裝置已清空」——可重試,優於跨服務分散式交易。"""
    user = await seed(uow, hasher, ids)
    failing = FakeAccountPurger("album", fails=True)
    use_case = build(uow, hasher, clock, [device_purger, failing])

    with pytest.raises(ServiceUnavailable):
        await use_case.execute(DeleteAccountCommand(user_id=user.id, confirmation=PASSWORD))

    assert device_purger.purged == [user.id]
    async with uow:
        assert await uow.users.get(user.id) is not None


async def test_retrying_after_a_partial_purge_succeeds(
    use_case: DeleteAccount,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    clock: FixedClock,
    ids: SequentialIdGenerator,
    device_purger: FakeAccountPurger,
    album_purger: FakeAccountPurger,
) -> None:
    """05_spec 第 2.2 節:兩個內部端點都要求冪等,重試時已清空必須視為成功。"""
    user = await seed(uow, hasher, ids)
    failing_album = FakeAccountPurger("album", fails=True)
    first_try = build(uow, hasher, clock, [device_purger, failing_album])

    with pytest.raises(ServiceUnavailable):
        await first_try.execute(DeleteAccountCommand(user_id=user.id, confirmation=PASSWORD))

    await use_case.execute(DeleteAccountCommand(user_id=user.id, confirmation=PASSWORD))

    assert device_purger.purged == [user.id, user.id]  # 第二次重複呼叫,冪等
    async with uow:
        assert await uow.users.get(user.id) is None


async def test_unknown_user_is_rejected(
    use_case: DeleteAccount, ids: SequentialIdGenerator
) -> None:
    with pytest.raises(AccountNotFound):
        await use_case.execute(
            DeleteAccountCommand(user_id=ids.new_id(), confirmation=PASSWORD)
        )
