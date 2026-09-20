"""ExtendAppToken 與 Logout。

規格:02_spec_登入註冊與密碼重設.md 第 2.3.2 節(滑動展延,規格審查 #6)、
第 2.5 節(登出,規格審查 #9)。
"""

import uuid
from datetime import timedelta

import pytest

from app.domains.sessions.application.dtos import ExtendTokenCommand
from app.domains.sessions.application.use_cases.extend_app_token import ExtendAppToken
from app.domains.sessions.application.use_cases.issue_session import IssueSession
from app.domains.sessions.application.use_cases.logout import Logout
from app.domains.sessions.domain.exceptions import TokenNotExtendable
from app.shared_kernel.platform import Platform
from tests.domains.accounts.fakes import FakeTokenFactory, FixedClock, SequentialIdGenerator
from tests.domains.sessions.application.conftest import NOW
from tests.domains.sessions.fakes import FakeAccessTokenSigner, FakeSessionsUnitOfWork

USER_ID = uuid.uuid4()


@pytest.fixture
def extend(signer: FakeAccessTokenSigner, clock: FixedClock) -> ExtendAppToken:
    return ExtendAppToken(signer=signer, clock=clock)


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
def logout(
    uow: FakeSessionsUnitOfWork, clock: FixedClock, tokens: FakeTokenFactory
) -> Logout:
    return Logout(uow, clock=clock, tokens=tokens)


# --------------------------- ExtendAppToken ---------------------------


async def test_token_younger_than_7_days_is_not_extended(
    extend: ExtendAppToken, clock: FixedClock
) -> None:
    """未滿 7 天回 None,由 router 轉成 204,App 沿用原 token(§2.3.2)。"""
    clock.advance_to(NOW + timedelta(days=7) - timedelta(seconds=1))

    result = await extend.execute(
        ExtendTokenCommand(user_id=USER_ID, platform=Platform.APP, issued_at=NOW)
    )

    assert result is None


async def test_token_older_than_7_days_gets_a_fresh_180_day_token(
    extend: ExtendAppToken, clock: FixedClock, signer: FakeAccessTokenSigner
) -> None:
    later = NOW + timedelta(days=7)
    clock.advance_to(later)

    result = await extend.execute(
        ExtendTokenCommand(user_id=USER_ID, platform=Platform.APP, issued_at=NOW)
    )

    assert result is not None
    assert result.refresh_token is None
    assert signer.signed[-1] == {
        "sub": str(USER_ID),
        "iat": int(later.timestamp()),
        "exp": int((later + timedelta(days=180)).timestamp()),
        "platform": "app",
    }


async def test_extension_restarts_the_180_day_clock(
    extend: ExtendAppToken, clock: FixedClock, signer: FakeAccessTokenSigner
) -> None:
    """§2.3.2:只要每 180 天開一次 App,就會持續展延。"""
    first_extension = NOW + timedelta(days=100)
    clock.advance_to(first_extension)
    assert (
        await extend.execute(
            ExtendTokenCommand(user_id=USER_ID, platform=Platform.APP, issued_at=NOW)
        )
        is not None
    )

    assert signer.signed[-1]["exp"] == int(
        (first_extension + timedelta(days=180)).timestamp()
    )


async def test_web_token_cannot_be_extended(
    extend: ExtendAppToken, clock: FixedClock
) -> None:
    """展延是 App 專用;Web 走 refresh token rotation(§2.6)。"""
    clock.advance_to(NOW + timedelta(days=30))

    with pytest.raises(TokenNotExtendable) as exc_info:
        await extend.execute(
            ExtendTokenCommand(user_id=USER_ID, platform=Platform.WEB, issued_at=NOW)
        )
    assert exc_info.value.code == "AUTH_001"


# ------------------------------- Logout -------------------------------


async def test_logout_revokes_the_refresh_token(
    issue: IssueSession, logout: Logout, uow: FakeSessionsUnitOfWork
) -> None:
    issued = await issue.execute(USER_ID, Platform.WEB)
    assert issued.refresh_token is not None

    await logout.execute(issued.refresh_token)

    async with uow:
        stored = await uow.refresh_tokens.get_by_fingerprint("fp:" + issued.refresh_token)
    assert stored is not None
    assert stored.is_usable(now=NOW) is False


async def test_logging_out_twice_is_not_an_error(
    issue: IssueSession, logout: Logout
) -> None:
    """§2.5:登出失敗對使用者沒有可執行的復原動作,一律回 204。"""
    issued = await issue.execute(USER_ID, Platform.WEB)
    assert issued.refresh_token is not None

    await logout.execute(issued.refresh_token)
    await logout.execute(issued.refresh_token)


async def test_logging_out_an_unknown_token_is_not_an_error(logout: Logout) -> None:
    """回錯誤會洩漏「這個 token 存不存在」。"""
    await logout.execute("never-issued")


async def test_logout_does_not_trigger_replay_detection(
    issue: IssueSession, logout: Logout, uow: FakeSessionsUnitOfWork
) -> None:
    """§2.5 明訂登出不套用 §2.3.1 的重放偵測——否則使用者在兩個分頁各按一次
    登出,就會把自己所有 session 連帶撤銷。"""
    first = await issue.execute(USER_ID, Platform.WEB)
    second = await issue.execute(USER_ID, Platform.WEB)
    assert first.refresh_token is not None
    assert second.refresh_token is not None

    await logout.execute(first.refresh_token)
    await logout.execute(first.refresh_token)

    async with uow:
        other = await uow.refresh_tokens.get_by_fingerprint("fp:" + second.refresh_token)
    assert other is not None
    assert other.is_usable(now=NOW) is True
