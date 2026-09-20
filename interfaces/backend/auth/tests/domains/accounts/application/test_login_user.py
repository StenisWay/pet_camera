"""LoginUser use case。

規格:02_spec_登入註冊與密碼重設.md 第 2.3 節。
本 use case 的核心不是「密碼對不對」(那在 domain 測完了),而是編排:
載入、鎖定判斷、把失敗計數寫回去、成功時請 sessions 簽發 token。
"""

import pytest

from app.domains.accounts.application.dtos import LoginCommand
from app.domains.accounts.application.use_cases.login_user import LoginUser
from app.domains.accounts.domain.entities import MAX_LOGIN_ATTEMPTS, User
from app.domains.accounts.domain.exceptions import (
    AccountLocked,
    InvalidCredentials,
    WeakPassword,
)
from app.domains.accounts.domain.value_objects import Email, RawPassword
from app.shared_kernel.platform import Platform
from tests.domains.accounts.application.conftest import NOW
from tests.domains.accounts.fakes import (
    FakeAccountsUnitOfWork,
    FakeLoginAttemptTracker,
    FakePasswordHasher,
    FakeSessionService,
    FixedClock,
    SequentialIdGenerator,
)

EMAIL = "owner@example.com"
PASSWORD = "correct1"


@pytest.fixture
def use_case(
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    clock: FixedClock,
    sessions: FakeSessionService,
    attempts: FakeLoginAttemptTracker,
) -> LoginUser:
    return LoginUser(uow, hasher=hasher, clock=clock, sessions=sessions, attempts=attempts)


async def seed_user(
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> User:
    user = User.register(
        id=ids.new_id(),
        email=Email.parse(EMAIL),
        password=RawPassword.parse(PASSWORD),
        hasher=hasher,
        now=NOW,
    )
    async with uow:
        await uow.users.add(user)
        await uow.commit()
    return user


async def test_successful_web_login_issues_a_session_and_commits(
    use_case: LoginUser,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
    sessions: FakeSessionService,
) -> None:
    user = await seed_user(uow, hasher, ids)
    before = uow.commits

    result = await use_case.execute(
        LoginCommand(email="  Owner@Example.com ", password=PASSWORD, platform=Platform.WEB)
    )

    assert result.user_id == user.id
    assert result.refresh_token is not None
    assert sessions.issued == [(user.id, Platform.WEB)]
    assert uow.commits == before + 1


async def test_app_login_gets_no_refresh_token(
    use_case: LoginUser,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    """§2.3:App 不使用 refresh token。"""
    await seed_user(uow, hasher, ids)
    result = await use_case.execute(
        LoginCommand(email=EMAIL, password=PASSWORD, platform=Platform.APP)
    )
    assert result.refresh_token is None


async def test_wrong_password_still_commits_the_failure_counter(
    use_case: LoginUser,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    """失敗計數不 commit 的話,連續 5 次永遠湊不滿,鎖定形同虛設。"""
    user = await seed_user(uow, hasher, ids)
    before = uow.commits

    with pytest.raises(InvalidCredentials):
        await use_case.execute(
            LoginCommand(email=EMAIL, password="wrong123", platform=Platform.WEB)
        )

    assert uow.commits == before + 1
    async with uow:
        stored = await uow.users.get(user.id)
    assert stored is not None
    assert stored.failed_login_attempts == 1


async def test_five_wrong_passwords_lock_the_account(
    use_case: LoginUser,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    await seed_user(uow, hasher, ids)
    command = LoginCommand(email=EMAIL, password="wrong123", platform=Platform.WEB)

    for _ in range(MAX_LOGIN_ATTEMPTS - 1):
        with pytest.raises(InvalidCredentials):
            await use_case.execute(command)

    with pytest.raises(AccountLocked):
        await use_case.execute(command)

    # 鎖定後即使密碼正確也進不去
    with pytest.raises(AccountLocked):
        await use_case.execute(
            LoginCommand(email=EMAIL, password=PASSWORD, platform=Platform.WEB)
        )


async def test_no_session_is_issued_when_authentication_fails(
    use_case: LoginUser,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
    sessions: FakeSessionService,
) -> None:
    await seed_user(uow, hasher, ids)
    with pytest.raises(InvalidCredentials):
        await use_case.execute(
            LoginCommand(email=EMAIL, password="wrong123", platform=Platform.WEB)
        )
    assert sessions.issued == []


async def test_unknown_account_raises_the_same_error_as_a_wrong_password(
    use_case: LoginUser, attempts: FakeLoginAttemptTracker
) -> None:
    with pytest.raises(InvalidCredentials) as exc_info:
        await use_case.execute(
            LoginCommand(email="nobody@example.com", password="abcd1234", platform=Platform.WEB)
        )
    assert exc_info.value.code == "AUTH_003"
    # 不存在的帳號沒有列可以寫,計數落在 tracker(規格審查 #7)
    assert attempts.failures == {"nobody@example.com": 1}


async def test_unknown_account_locks_out_after_five_attempts_too(
    use_case: LoginUser,
) -> None:
    """審查 #7:若只對存在的帳號鎖定,回應差異本身就是一個帳號列舉器。"""
    command = LoginCommand(
        email="nobody@example.com", password="abcd1234", platform=Platform.WEB
    )
    for _ in range(MAX_LOGIN_ATTEMPTS - 1):
        with pytest.raises(InvalidCredentials):
            await use_case.execute(command)

    with pytest.raises(AccountLocked) as exc_info:
        await use_case.execute(command)
    assert exc_info.value.code == "AUTH_005"
    assert exc_info.value.retry_after_seconds == 15 * 60


async def test_unknown_account_stays_locked_on_subsequent_attempts(
    use_case: LoginUser,
) -> None:
    command = LoginCommand(
        email="nobody@example.com", password="abcd1234", platform=Platform.WEB
    )
    for _ in range(MAX_LOGIN_ATTEMPTS):
        with pytest.raises((InvalidCredentials, AccountLocked)):
            await use_case.execute(command)

    with pytest.raises(AccountLocked):
        await use_case.execute(command)


async def test_tracker_outage_fails_open_for_unknown_accounts(
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    clock: FixedClock,
    sessions: FakeSessionService,
) -> None:
    """§2.3:Redis 不可用時不鎖定,但也不能讓登入請求整個失敗。"""
    tracker = FakeLoginAttemptTracker(unavailable=True)
    use_case = LoginUser(uow, hasher=hasher, clock=clock, sessions=sessions, attempts=tracker)
    command = LoginCommand(
        email="nobody@example.com", password="abcd1234", platform=Platform.WEB
    )
    for _ in range(MAX_LOGIN_ATTEMPTS + 2):
        with pytest.raises(InvalidCredentials):
            await use_case.execute(command)


async def test_malformed_password_is_rejected_without_touching_the_account(
    use_case: LoginUser,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
    attempts: FakeLoginAttemptTracker,
) -> None:
    """§2.1 的欄位規則涵蓋登入表單;不合規的輸入連查都不用查。"""
    user = await seed_user(uow, hasher, ids)
    with pytest.raises(WeakPassword):
        await use_case.execute(
            LoginCommand(email=EMAIL, password="short", platform=Platform.WEB)
        )
    assert attempts.failures == {}
    async with uow:
        stored = await uow.users.get(user.id)
    assert stored is not None
    assert stored.failed_login_attempts == 0
