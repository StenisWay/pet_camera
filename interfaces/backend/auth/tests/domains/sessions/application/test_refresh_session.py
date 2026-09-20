"""RefreshSession use case:rotation、重放偵測、併發。

規格:02_spec_登入註冊與密碼重設.md 第 2.3.1 節(規格審查 #10、#11)。
"""

import uuid
from datetime import timedelta

import pytest

from app.domains.sessions.application.use_cases.issue_session import IssueSession
from app.domains.sessions.application.use_cases.refresh_session import RefreshSession
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
def use_case(
    uow: FakeSessionsUnitOfWork,
    signer: FakeAccessTokenSigner,
    clock: FixedClock,
    ids: SequentialIdGenerator,
    tokens: FakeTokenFactory,
) -> RefreshSession:
    return RefreshSession(uow, signer=signer, clock=clock, ids=ids, tokens=tokens)


async def test_unknown_refresh_token_is_rejected(use_case: RefreshSession) -> None:
    with pytest.raises(RefreshTokenRejected) as exc_info:
        await use_case.execute("never-issued")
    assert exc_info.value.code == "AUTH_010"


async def test_expired_refresh_token_is_rejected(
    issue: IssueSession, use_case: RefreshSession, clock: FixedClock
) -> None:
    issued = await issue.execute(USER_ID, Platform.WEB)
    assert issued.refresh_token is not None

    clock.advance_to(NOW + timedelta(days=30, seconds=1))
    with pytest.raises(RefreshTokenRejected):
        await use_case.execute(issued.refresh_token)


async def test_rotation_revokes_the_old_token_and_issues_a_new_one(
    issue: IssueSession, use_case: RefreshSession, uow: FakeSessionsUnitOfWork
) -> None:
    issued = await issue.execute(USER_ID, Platform.WEB)
    assert issued.refresh_token is not None

    rotated = await use_case.execute(issued.refresh_token)

    assert rotated.refresh_token is not None
    assert rotated.refresh_token != issued.refresh_token
    async with uow:
        old = await uow.refresh_tokens.get_by_fingerprint("fp:" + issued.refresh_token)
        new = await uow.refresh_tokens.get_by_fingerprint("fp:" + rotated.refresh_token)
    assert old is not None and old.is_usable(now=NOW) is False
    assert new is not None and new.is_usable(now=NOW) is True


async def test_replaying_a_revoked_token_revokes_every_session_of_that_user(
    issue: IssueSession, use_case: RefreshSession, uow: FakeSessionsUnitOfWork
) -> None:
    """§2.3.1:已換發過的 token 再次出現 = 外洩的徵兆,整串撤銷比放行安全。"""
    first = await issue.execute(USER_ID, Platform.WEB)
    second = await issue.execute(USER_ID, Platform.WEB)  # 同一使用者的另一個 session
    assert first.refresh_token is not None
    assert second.refresh_token is not None

    rotated = await use_case.execute(first.refresh_token)
    assert rotated.refresh_token is not None

    # 攻擊者拿著已經被換發掉的舊 token 再來一次
    with pytest.raises(RefreshTokenRejected):
        await use_case.execute(first.refresh_token)

    async with uow:
        other = await uow.refresh_tokens.get_by_fingerprint("fp:" + second.refresh_token)
        just_rotated = await uow.refresh_tokens.get_by_fingerprint(
            "fp:" + rotated.refresh_token
        )
    assert other is not None and other.is_usable(now=NOW) is False
    assert just_rotated is not None and just_rotated.is_usable(now=NOW) is False


async def test_replay_detection_does_not_touch_other_users(
    issue: IssueSession, use_case: RefreshSession, uow: FakeSessionsUnitOfWork
) -> None:
    victim = await issue.execute(USER_ID, Platform.WEB)
    bystander = await issue.execute(uuid.uuid4(), Platform.WEB)
    assert victim.refresh_token is not None
    assert bystander.refresh_token is not None

    await use_case.execute(victim.refresh_token)
    with pytest.raises(RefreshTokenRejected):
        await use_case.execute(victim.refresh_token)

    async with uow:
        untouched = await uow.refresh_tokens.get_by_fingerprint(
            "fp:" + bystander.refresh_token
        )
    assert untouched is not None and untouched.is_usable(now=NOW) is True


async def test_unknown_token_does_not_trigger_mass_revocation(
    issue: IssueSession, use_case: RefreshSession, uow: FakeSessionsUnitOfWork
) -> None:
    """查無此 token 只是亂猜,不該讓任何人被登出(§2.3.1)。"""
    issued = await issue.execute(USER_ID, Platform.WEB)
    assert issued.refresh_token is not None

    with pytest.raises(RefreshTokenRejected):
        await use_case.execute("random-guess")

    async with uow:
        mine = await uow.refresh_tokens.get_by_fingerprint("fp:" + issued.refresh_token)
    assert mine is not None and mine.is_usable(now=NOW) is True


async def test_concurrent_rotation_lets_only_one_request_win(
    issue: IssueSession, use_case: RefreshSession, uow: FakeSessionsUnitOfWork
) -> None:
    """審查 #11:一個 refresh token 不得換出兩組有效 token。

    fake 的 revoke() 與 SQLAlchemy 的條件 UPDATE 行為一致(合約測試保證),
    所以「輸家拿到 False」這件事在這裡就能測。
    """
    issued = await issue.execute(USER_ID, Platform.WEB)
    assert issued.refresh_token is not None

    winner = await use_case.execute(issued.refresh_token)
    assert winner.refresh_token is not None

    # 第二個請求拿同一個舊 token 進來:revoke 影響 0 列,視為重放
    with pytest.raises(RefreshTokenRejected):
        await use_case.execute(issued.refresh_token)


async def test_rotated_access_token_is_a_fresh_web_token(
    issue: IssueSession,
    use_case: RefreshSession,
    signer: FakeAccessTokenSigner,
    clock: FixedClock,
) -> None:
    issued = await issue.execute(USER_ID, Platform.WEB)
    assert issued.refresh_token is not None

    later = NOW + timedelta(minutes=59)
    clock.advance_to(later)
    await use_case.execute(issued.refresh_token)

    assert signer.signed[-1] == {
        "sub": str(USER_ID),
        "iat": int(later.timestamp()),
        "exp": int((later + timedelta(hours=1)).timestamp()),
        "platform": "web",
    }
