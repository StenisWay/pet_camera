"""RequestPasswordReset use case。

規格:02_spec_登入註冊與密碼重設.md 第 2.4 節。
這個 use case 的全部難處都在「什麼都不能洩漏」:email 不存在、寄信失敗,
對外的回應都必須與成功完全一致。
"""

import uuid
from datetime import timedelta

import pytest

from app.domains.accounts.application.dtos import RequestPasswordResetCommand
from app.domains.accounts.application.use_cases.request_password_reset import (
    RequestPasswordReset,
)
from app.domains.accounts.domain.entities import User
from app.domains.accounts.domain.exceptions import InvalidEmail
from app.domains.accounts.domain.value_objects import Email, RawPassword
from app.shared_kernel.errors import RateLimited
from tests.domains.accounts.application.conftest import NOW
from tests.domains.accounts.fakes import (
    FakeAccountsUnitOfWork,
    FakeEmailSender,
    FakePasswordHasher,
    FakePasswordResetThrottle,
    FakeTokenFactory,
    FixedClock,
    SequentialIdGenerator,
)

EMAIL = "owner@example.com"
RESET_URL = "https://app.example.com/reset-password?token={token}"


def build(
    uow: FakeAccountsUnitOfWork,
    clock: FixedClock,
    ids: SequentialIdGenerator,
    tokens: FakeTokenFactory,
    mailer: FakeEmailSender,
    throttle: FakePasswordResetThrottle,
) -> RequestPasswordReset:
    return RequestPasswordReset(
        uow,
        clock=clock,
        ids=ids,
        tokens=tokens,
        mailer=mailer,
        throttle=throttle,
        reset_url_template=RESET_URL,
    )


@pytest.fixture
def use_case(
    uow: FakeAccountsUnitOfWork,
    clock: FixedClock,
    ids: SequentialIdGenerator,
    tokens: FakeTokenFactory,
    mailer: FakeEmailSender,
    throttle: FakePasswordResetThrottle,
) -> RequestPasswordReset:
    return build(uow, clock, ids, tokens, mailer, throttle)


async def seed_user(
    uow: FakeAccountsUnitOfWork, hasher: FakePasswordHasher, ids: SequentialIdGenerator
) -> User:
    user = User.register(
        id=ids.new_id(),
        email=Email.parse(EMAIL),
        password=RawPassword.parse("correct1"),
        hasher=hasher,
        now=NOW,
    )
    async with uow:
        await uow.users.add(user)
        await uow.commit()
    return user


async def test_known_email_gets_a_reset_link_with_the_plaintext_token(
    use_case: RequestPasswordReset,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
    mailer: FakeEmailSender,
) -> None:
    await seed_user(uow, hasher, ids)

    await use_case.execute(RequestPasswordResetCommand(email=EMAIL, client_ip="203.0.113.1"))

    assert len(mailer.sent) == 1
    to, url = mailer.sent[0]
    assert to == EMAIL
    assert url == RESET_URL.format(token="secret-1")


async def test_only_the_fingerprint_of_the_reset_token_is_stored(
    use_case: RequestPasswordReset,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    """§2.4:DB 外洩不等於可以重設任何人的密碼。"""
    await seed_user(uow, hasher, ids)

    await use_case.execute(RequestPasswordResetCommand(email=EMAIL, client_ip="203.0.113.1"))

    async with uow:
        stored = await uow.reset_tokens.get_by_fingerprint("fp:secret-1")
        assert await uow.reset_tokens.get_by_fingerprint("secret-1") is None
    assert stored is not None
    assert stored.expires_at == NOW + timedelta(minutes=30)
    assert stored.used_at is None


async def test_unknown_email_looks_exactly_like_success(
    use_case: RequestPasswordReset,
    uow: FakeAccountsUnitOfWork,
    mailer: FakeEmailSender,
) -> None:
    """§2.4:不論 email 是否已註冊,一律回傳相同成功訊息。"""
    before = uow.commits

    await use_case.execute(
        RequestPasswordResetCommand(email="nobody@example.com", client_ip="203.0.113.1")
    )

    assert mailer.sent == []
    assert uow.commits == before  # 沒有建立任何 token


async def test_mail_failure_is_swallowed(
    uow: FakeAccountsUnitOfWork,
    clock: FixedClock,
    ids: SequentialIdGenerator,
    tokens: FakeTokenFactory,
    throttle: FakePasswordResetThrottle,
    hasher: FakePasswordHasher,
) -> None:
    """寄信失敗回錯誤,等於告訴呼叫端「這個 email 存在」(§2.4)。"""
    await seed_user(uow, hasher, ids)
    mailer = FakeEmailSender(fails=True)
    use_case = build(uow, clock, ids, tokens, mailer, throttle)

    await use_case.execute(RequestPasswordResetCommand(email=EMAIL, client_ip="203.0.113.1"))

    assert mailer.sent == []


async def test_email_is_normalized_before_lookup(
    use_case: RequestPasswordReset,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
    mailer: FakeEmailSender,
) -> None:
    await seed_user(uow, hasher, ids)

    await use_case.execute(
        RequestPasswordResetCommand(email="  Owner@Example.COM ", client_ip="203.0.113.1")
    )

    assert len(mailer.sent) == 1


async def test_throttle_is_checked_on_both_email_and_ip(
    use_case: RequestPasswordReset, throttle: FakePasswordResetThrottle
) -> None:
    """§2.4:email 與來源 IP 兩個維度各 5 次/小時。"""
    await use_case.execute(
        RequestPasswordResetCommand(email=EMAIL, client_ip="203.0.113.1")
    )
    assert throttle.checked == [(EMAIL, "203.0.113.1")]


async def test_throttled_request_is_rejected_before_anything_happens(
    uow: FakeAccountsUnitOfWork,
    clock: FixedClock,
    ids: SequentialIdGenerator,
    tokens: FakeTokenFactory,
    mailer: FakeEmailSender,
    hasher: FakePasswordHasher,
) -> None:
    await seed_user(uow, hasher, ids)
    use_case = build(uow, clock, ids, tokens, mailer, FakePasswordResetThrottle(allow=False))

    with pytest.raises(RateLimited) as exc_info:
        await use_case.execute(
            RequestPasswordResetCommand(email=EMAIL, client_ip="203.0.113.1")
        )

    assert exc_info.value.code == "RATE_001"
    assert mailer.sent == []
    assert tokens.generated == []


async def test_malformed_email_is_rejected(use_case: RequestPasswordReset) -> None:
    with pytest.raises(InvalidEmail):
        await use_case.execute(
            RequestPasswordResetCommand(email="not-an-email", client_ip="203.0.113.1")
        )


async def test_repeated_requests_each_get_their_own_token(
    use_case: RequestPasswordReset,
    uow: FakeAccountsUnitOfWork,
    hasher: FakePasswordHasher,
    ids: SequentialIdGenerator,
) -> None:
    """§2.4:同一帳號重複申請時舊 token 不主動失效,各自依 30 分鐘期限過期。"""
    await seed_user(uow, hasher, ids)
    command = RequestPasswordResetCommand(email=EMAIL, client_ip="203.0.113.1")

    await use_case.execute(command)
    await use_case.execute(command)

    async with uow:
        first = await uow.reset_tokens.get_by_fingerprint("fp:secret-1")
        second = await uow.reset_tokens.get_by_fingerprint("fp:secret-2")
    assert first is not None and first.used_at is None
    assert second is not None and second.used_at is None
    assert first.id != second.id
    assert isinstance(first.user_id, uuid.UUID)
