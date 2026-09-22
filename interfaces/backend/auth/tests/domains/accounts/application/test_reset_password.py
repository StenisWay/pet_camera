"""ResetPassword use case。

規格:02_spec_登入註冊與密碼重設.md 第 2.4 節步驟 4、5。
"""

import uuid
from datetime import timedelta

import pytest

from app.domains.accounts.application.dtos import ResetPasswordCommand
from app.domains.accounts.application.use_cases.reset_password import ResetPassword
from app.domains.accounts.domain.entities import PasswordResetToken, User
from app.domains.accounts.domain.exceptions import InvalidResetToken, WeakPassword
from app.domains.accounts.domain.value_objects import Email, RawPassword
from tests.domains.accounts.application.conftest import NOW
from tests.domains.accounts.fakes import (
    FakeAccountsUnitOfWork,
    FakePasswordHasher,
    FakePasswordResetTokenRepository,
    FakeSessionService,
    FakeTokenFactory,
    FixedClock,
    SequentialIdGenerator,
)

EMAIL = "owner@example.com"
OLD_PASSWORD = "correct1"
NEW_PASSWORD = "brandnew2"
SECRET = "secret-1"


@pytest.fixture
def use_case(
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    clock: FixedClock,
    tokens: FakeTokenFactory,
    sessions: FakeSessionService,
) -> ResetPassword:
    return ResetPassword(uow, hasher=hasher, clock=clock, tokens=tokens, sessions=sessions)


async def seed(
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
    *,
    expires_in: timedelta = timedelta(minutes=30),
    used: bool = False,
) -> User:
    user = User.register(
        id=ids.new_id(),
        email=Email.parse(EMAIL),
        password=RawPassword.parse(OLD_PASSWORD),
        hasher=hasher,
        now=NOW,
    )
    token = PasswordResetToken(
        id=ids.new_id(),
        user_id=user.id,
        token_hash="fp:" + SECRET,
        expires_at=NOW + expires_in,
        used_at=NOW if used else None,
        created_at=NOW,
    )
    async with uow:
        await uow.users.add(user)
        await uow.reset_tokens.add(token)
        await uow.commit()
    return user


async def test_valid_token_sets_the_new_password(
    use_case: ResetPassword,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    user = await seed(uow, hasher, ids)

    await use_case.execute(ResetPasswordCommand(token=SECRET, new_password=NEW_PASSWORD))

    async with uow:
        stored = await uow.users.get(user.id)
    assert stored is not None
    stored.authenticate(RawPassword.parse(NEW_PASSWORD), hasher=hasher, now=NOW)


async def test_the_old_password_stops_working(
    use_case: ResetPassword,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    user = await seed(uow, hasher, ids)

    await use_case.execute(ResetPasswordCommand(token=SECRET, new_password=NEW_PASSWORD))

    async with uow:
        stored = await uow.users.get(user.id)
    assert stored is not None
    assert stored.password_hash != hasher.hash(RawPassword.parse(OLD_PASSWORD))


async def test_the_token_is_consumed(
    use_case: ResetPassword,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    await seed(uow, hasher, ids)

    await use_case.execute(ResetPasswordCommand(token=SECRET, new_password=NEW_PASSWORD))

    async with uow:
        token = await uow.reset_tokens.get_by_fingerprint("fp:" + SECRET)
    assert token is not None
    assert token.used_at == NOW


async def test_the_same_link_cannot_be_used_twice(
    use_case: ResetPassword,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    await seed(uow, hasher, ids)
    await use_case.execute(ResetPasswordCommand(token=SECRET, new_password=NEW_PASSWORD))

    with pytest.raises(InvalidResetToken) as exc_info:
        await use_case.execute(ResetPasswordCommand(token=SECRET, new_password="another34"))
    assert exc_info.value.code == "AUTH_007"


async def test_all_refresh_tokens_are_revoked_after_a_reset(
    use_case: ResetPassword,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
    sessions: FakeSessionService,
) -> None:
    """§2.4:能重設密碼的人未必是原本持有 session 的人,不撤銷等於趕不走對方。"""
    user = await seed(uow, hasher, ids)

    await use_case.execute(ResetPasswordCommand(token=SECRET, new_password=NEW_PASSWORD))

    assert sessions.revoked == [(user.id, None)]  # 不保留任何一個


async def test_expired_token_is_rejected(
    use_case: ResetPassword,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    await seed(uow, hasher, ids, expires_in=timedelta(seconds=-1))

    with pytest.raises(InvalidResetToken):
        await use_case.execute(ResetPasswordCommand(token=SECRET, new_password=NEW_PASSWORD))


async def test_unknown_token_is_rejected(use_case: ResetPassword) -> None:
    with pytest.raises(InvalidResetToken):
        await use_case.execute(
            ResetPasswordCommand(token="never-issued", new_password=NEW_PASSWORD)
        )


async def test_weak_new_password_is_rejected_without_consuming_the_token(
    use_case: ResetPassword,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    """打錯一次密碼規則就讓連結報銷,使用者只能回去重新申請一次——太粗暴。"""
    await seed(uow, hasher, ids)

    with pytest.raises(WeakPassword):
        await use_case.execute(ResetPasswordCommand(token=SECRET, new_password="short"))

    async with uow:
        token = await uow.reset_tokens.get_by_fingerprint("fp:" + SECRET)
    assert token is not None
    assert token.used_at is None

    # 改用合規的密碼仍然可以成功
    await use_case.execute(ResetPasswordCommand(token=SECRET, new_password=NEW_PASSWORD))


async def test_reset_unlocks_a_locked_out_account(
    use_case: ResetPassword,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    user = await seed(uow, hasher, ids)
    async with uow:
        locked = await uow.users.get(user.id)
        assert locked is not None
        locked.failed_login_attempts = 5
        locked.locked_until = NOW + timedelta(minutes=15)
        await uow.users.save(locked)
        await uow.commit()

    await use_case.execute(ResetPasswordCommand(token=SECRET, new_password=NEW_PASSWORD))

    async with uow:
        stored = await uow.users.get(user.id)
    assert stored is not None
    assert stored.locked_until is None
    stored.authenticate(RawPassword.parse(NEW_PASSWORD), hasher=hasher, now=NOW)


async def test_token_for_a_deleted_account_is_rejected(
    use_case: ResetPassword,
    uow: FakeAccountsUnitOfWork,
    ids: SequentialIdGenerator,
) -> None:
    """帳號在申請與點擊之間被刪掉:token 還在,但沒有對象可以重設。"""
    orphan = PasswordResetToken(
        id=ids.new_id(),
        user_id=uuid.uuid4(),
        token_hash="fp:" + SECRET,
        expires_at=NOW + timedelta(minutes=30),
        used_at=None,
        created_at=NOW,
    )
    async with uow:
        await uow.reset_tokens.add(orphan)
        await uow.commit()

    with pytest.raises(InvalidResetToken):
        await use_case.execute(ResetPasswordCommand(token=SECRET, new_password=NEW_PASSWORD))


async def test_losing_the_race_to_consume_the_token_changes_nothing(
    use_case: ResetPassword,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """兩個請求同時拿同一個連結:mark_used 影響 0 列的那一方必須什麼都不做。

    序列化地點兩次會先被 ensure_usable 擋下,測不到這條路;真正的併發只有
    mark_used 的回傳值能仲裁,所以這裡直接把它壓成 False。
    """
    user = await seed(uow, hasher, ids)
    original_hash = (await _load(uow, user.id)).password_hash

    async def always_loses(*args: object, **kwargs: object) -> bool:
        return False

    monkeypatch.setattr(
        FakePasswordResetTokenRepository, "mark_used", always_loses, raising=True
    )

    with pytest.raises(InvalidResetToken):
        await use_case.execute(ResetPasswordCommand(token=SECRET, new_password=NEW_PASSWORD))

    assert (await _load(uow, user.id)).password_hash == original_hash


async def _load(uow: FakeAccountsUnitOfWork, user_id: uuid.UUID) -> User:
    async with uow:
        loaded = await uow.users.get(user_id)
    assert loaded is not None
    return loaded
