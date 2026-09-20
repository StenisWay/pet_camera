"""RevokeUserSessions:accounts 在改密碼與重設密碼後會用到。

規格:05_spec_帳號設定.md 第 2.1 節、02_spec 第 2.4 節。
"""

import uuid

import pytest

from app.domains.sessions.application.use_cases.issue_session import IssueSession
from app.domains.sessions.application.use_cases.revoke_user_sessions import (
    RevokeUserSessions,
)
from app.shared_kernel.platform import Platform
from tests.domains.accounts.fakes import FakeTokenFactory, FixedClock, SequentialIdGenerator
from tests.domains.sessions.application.conftest import NOW
from tests.domains.sessions.fakes import FakeAccessTokenSigner, FakeSessionsUnitOfWork

USER_ID = uuid.uuid4()


@pytest.fixture
def issue(
    uow: FakeSessionsUnitOfWork,
    signer: FakeAccessTokenSigner,
    clock: FixedClock,
    ids: SequentialIdGenerator,
    tokens: FakeTokenFactory,
) -> IssueSession:
    return IssueSession(uow, signer=signer, clock=clock, ids=ids, tokens=tokens)


@pytest.fixture
def use_case(
    uow: FakeSessionsUnitOfWork, clock: FixedClock, tokens: FakeTokenFactory
) -> RevokeUserSessions:
    return RevokeUserSessions(uow, clock=clock, tokens=tokens)


async def test_revoking_all_sessions_of_a_user(
    issue: IssueSession, use_case: RevokeUserSessions, uow: FakeSessionsUnitOfWork
) -> None:
    first = await issue.execute(USER_ID, Platform.WEB)
    second = await issue.execute(USER_ID, Platform.WEB)
    assert first.refresh_token is not None
    assert second.refresh_token is not None

    assert await use_case.execute(USER_ID) == 2

    async with uow:
        for token in (first.refresh_token, second.refresh_token):
            stored = await uow.refresh_tokens.get_by_fingerprint("fp:" + token)
            assert stored is not None
            assert stored.is_usable(now=NOW) is False


async def test_the_current_session_can_be_kept(
    issue: IssueSession, use_case: RevokeUserSessions, uow: FakeSessionsUnitOfWork
) -> None:
    keep = await issue.execute(USER_ID, Platform.WEB)
    drop = await issue.execute(USER_ID, Platform.WEB)
    assert keep.refresh_token is not None
    assert drop.refresh_token is not None

    assert await use_case.execute(USER_ID, except_refresh_token=keep.refresh_token) == 1

    async with uow:
        survivor = await uow.refresh_tokens.get_by_fingerprint("fp:" + keep.refresh_token)
    assert survivor is not None
    assert survivor.is_usable(now=NOW) is True


async def test_revoking_when_there_is_nothing_to_revoke(
    use_case: RevokeUserSessions, uow: FakeSessionsUnitOfWork
) -> None:
    """App-only 使用者沒有任何 refresh token,改密碼時不該因此失敗。"""
    assert await use_case.execute(USER_ID) == 0
    assert uow.commits == 1


async def test_an_unmatched_exception_token_keeps_nothing(
    issue: IssueSession, use_case: RevokeUserSessions
) -> None:
    """對不上的字串不該讓任何 session 逃過撤銷——寧可多撤銷。"""
    await issue.execute(USER_ID, Platform.WEB)

    assert await use_case.execute(USER_ID, except_refresh_token="not-mine") == 1
