"""IssueSession use case。

規格:02_spec_登入註冊與密碼重設.md 第 2.3、2.6 節。
"""

import uuid
from datetime import timedelta

from app.domains.sessions.application.use_cases.issue_session import IssueSession
from app.shared_kernel.platform import Platform
from tests.domains.accounts.fakes import FakeTokenFactory, FixedClock, SequentialIdGenerator
from tests.domains.sessions.application.conftest import NOW
from tests.domains.sessions.fakes import FakeAccessTokenSigner, FakeSessionsUnitOfWork

USER_ID = uuid.uuid4()


def build(
    uow: FakeSessionsUnitOfWork,
    signer: FakeAccessTokenSigner,
    clock: FixedClock,
    ids: SequentialIdGenerator,
    tokens: FakeTokenFactory,
) -> IssueSession:
    return IssueSession(uow, signer=signer, clock=clock, ids=ids, tokens=tokens)


async def test_web_login_gets_both_tokens_and_commits_once(
    uow: FakeSessionsUnitOfWork,
    signer: FakeAccessTokenSigner,
    clock: FixedClock,
    ids: SequentialIdGenerator,
    tokens: FakeTokenFactory,
) -> None:
    result = await build(uow, signer, clock, ids, tokens).execute(USER_ID, Platform.WEB)

    assert result.access_token == signer.sign(signer.signed[0])
    assert result.refresh_token == "secret-1"
    assert uow.commits == 1


async def test_only_the_fingerprint_of_the_refresh_token_is_stored(
    uow: FakeSessionsUnitOfWork,
    signer: FakeAccessTokenSigner,
    clock: FixedClock,
    ids: SequentialIdGenerator,
    tokens: FakeTokenFactory,
) -> None:
    """§2.3.1:資料庫只存雜湊,DB 外洩不等於可以冒用任何人的 session。"""
    result = await build(uow, signer, clock, ids, tokens).execute(USER_ID, Platform.WEB)

    async with uow:
        stored = await uow.refresh_tokens.get_by_fingerprint("fp:secret-1")
    assert stored is not None
    assert stored.token_hash != result.refresh_token
    assert stored.expires_at == NOW + timedelta(days=30)


async def test_app_login_writes_no_refresh_token_at_all(
    uow: FakeSessionsUnitOfWork,
    signer: FakeAccessTokenSigner,
    clock: FixedClock,
    ids: SequentialIdGenerator,
    tokens: FakeTokenFactory,
) -> None:
    """§2.3:App 平台不寫入 refresh_tokens 表。"""
    result = await build(uow, signer, clock, ids, tokens).execute(USER_ID, Platform.APP)

    assert result.refresh_token is None
    assert uow.commits == 0
    assert tokens.generated == []


async def test_signed_claims_follow_the_spec(
    uow: FakeSessionsUnitOfWork,
    signer: FakeAccessTokenSigner,
    clock: FixedClock,
    ids: SequentialIdGenerator,
    tokens: FakeTokenFactory,
) -> None:
    await build(uow, signer, clock, ids, tokens).execute(USER_ID, Platform.APP)

    assert signer.signed == [
        {
            "sub": str(USER_ID),
            "iat": int(NOW.timestamp()),
            "exp": int((NOW + timedelta(days=180)).timestamp()),
            "platform": "app",
        }
    ]
