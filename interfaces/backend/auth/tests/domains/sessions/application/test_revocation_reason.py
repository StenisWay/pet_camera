"""重放偵測只能對「被 rotation 換掉」的 token 生效。

02_spec 第 2.3.1 節把「已撤銷的 token 又出現」定義為外洩徵兆,要連帶撤銷整串。
但撤銷的理由不只 rotation 一種:

- **rotation**:正常用戶端拿到新 token 之後絕不會再用舊的,再出現就是竊取。
- **改密碼 / 重設密碼**:是**我們**主動撤銷的。那個分頁的使用者毫不知情,
  他下次換發時送上來的舊 token 完全無辜。
- **登出**:使用者自己按的。

不分理由一律連帶撤銷,會產生一個很難查的 bug:改完密碼後,另一個分頁背景自動
換發一次,就把「刻意保留的當前 session」也一起炸掉(05_spec 第 2.1 節)。
"""

import uuid

import pytest

from app.domains.sessions.application.use_cases.issue_session import IssueSession
from app.domains.sessions.application.use_cases.logout import Logout
from app.domains.sessions.application.use_cases.refresh_session import RefreshSession
from app.domains.sessions.application.use_cases.revoke_user_sessions import (
    RevokeUserSessions,
)
from app.domains.sessions.domain.entities import RevocationReason
from app.domains.sessions.domain.exceptions import RefreshTokenRejected
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
def refresh(
    uow: FakeSessionsUnitOfWork,
    signer: FakeAccessTokenSigner,
    clock: FixedClock,
    ids: SequentialIdGenerator,
    tokens: FakeTokenFactory,
) -> RefreshSession:
    return RefreshSession(uow, signer=signer, clock=clock, ids=ids, tokens=tokens)


@pytest.fixture
def revoke_all(
    uow: FakeSessionsUnitOfWork, clock: FixedClock, tokens: FakeTokenFactory
) -> RevokeUserSessions:
    return RevokeUserSessions(uow, clock=clock, tokens=tokens)


@pytest.fixture
def logout(
    uow: FakeSessionsUnitOfWork, clock: FixedClock, tokens: FakeTokenFactory
) -> Logout:
    return Logout(uow, clock=clock, tokens=tokens)


async def test_rotation_marks_the_old_token_as_rotated(
    issue: IssueSession, refresh: RefreshSession, uow: FakeSessionsUnitOfWork
) -> None:
    issued = await issue.execute(USER_ID, Platform.WEB)
    assert issued.refresh_token is not None

    await refresh.execute(issued.refresh_token)

    async with uow:
        old = await uow.refresh_tokens.get_by_fingerprint("fp:" + issued.refresh_token)
    assert old is not None
    assert old.revoked_reason is RevocationReason.ROTATED


async def test_an_administratively_revoked_token_does_not_trigger_mass_revocation(
    issue: IssueSession,
    refresh: RefreshSession,
    revoke_all: RevokeUserSessions,
    uow: FakeSessionsUnitOfWork,
) -> None:
    """改密碼的情境:保留的那一個 session 不能被另一個分頁的無辜換發炸掉。"""
    kept = await issue.execute(USER_ID, Platform.WEB)
    other = await issue.execute(USER_ID, Platform.WEB)
    assert kept.refresh_token is not None
    assert other.refresh_token is not None

    await revoke_all.execute(USER_ID, except_refresh_token=kept.refresh_token)

    # 另一個分頁不知情,照常來換發:拒絕它,但不要牽連別人
    with pytest.raises(RefreshTokenRejected):
        await refresh.execute(other.refresh_token)

    async with uow:
        survivor = await uow.refresh_tokens.get_by_fingerprint("fp:" + kept.refresh_token)
    assert survivor is not None
    assert survivor.is_usable(now=NOW) is True


async def test_a_logged_out_token_does_not_trigger_mass_revocation(
    issue: IssueSession,
    refresh: RefreshSession,
    logout: Logout,
    uow: FakeSessionsUnitOfWork,
) -> None:
    """使用者自己按的登出,不是竊取徵兆。"""
    first = await issue.execute(USER_ID, Platform.WEB)
    second = await issue.execute(USER_ID, Platform.WEB)
    assert first.refresh_token is not None
    assert second.refresh_token is not None

    await logout.execute(first.refresh_token)
    with pytest.raises(RefreshTokenRejected):
        await refresh.execute(first.refresh_token)

    async with uow:
        other = await uow.refresh_tokens.get_by_fingerprint("fp:" + second.refresh_token)
    assert other is not None
    assert other.is_usable(now=NOW) is True


async def test_a_genuinely_replayed_token_still_revokes_everything(
    issue: IssueSession, refresh: RefreshSession, uow: FakeSessionsUnitOfWork
) -> None:
    """rotation 之後又出現的舊 token,仍然照 §2.3.1 整串撤銷。"""
    stolen = await issue.execute(USER_ID, Platform.WEB)
    bystander = await issue.execute(USER_ID, Platform.WEB)
    assert stolen.refresh_token is not None
    assert bystander.refresh_token is not None

    await refresh.execute(stolen.refresh_token)
    with pytest.raises(RefreshTokenRejected):
        await refresh.execute(stolen.refresh_token)

    async with uow:
        other = await uow.refresh_tokens.get_by_fingerprint(
            "fp:" + bystander.refresh_token
        )
    assert other is not None
    assert other.is_usable(now=NOW) is False
