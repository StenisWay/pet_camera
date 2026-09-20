"""presentation 測試用的 app:真的 router、真的 use case,只有最外層換成 fake。

**簽章不換成 fake**:access token 要真的簽得出來、真的驗得過,否則「帶著登入
拿到的 token 去呼叫受保護端點」這條路徑根本沒被測到。

換掉的是資料庫、Redis、bcrypt、SMTP、其他服務——不是 use case 本身,否則測的
就只是「router 有沒有呼叫 mock」,而不是「這個 HTTP 請求會得到什麼回應」。
錯誤碼、狀態碼、回應形狀都要一路從 domain 走上來才算數。
"""

from dataclasses import dataclass, field

from fastapi import FastAPI

from app.core import dependencies as core_deps
from app.core.config import get_settings
from app.domains.accounts.infrastructure.sessions_adapter import SessionsApiAdapter
from app.domains.accounts.presentation import dependencies as accounts_deps
from app.domains.sessions.api import SessionsApi
from app.domains.sessions.application.use_cases.issue_session import IssueSession
from app.domains.sessions.application.use_cases.revoke_user_sessions import (
    RevokeUserSessions,
)
from app.domains.sessions.infrastructure.token_signer import JwtAccessTokenSigner
from app.domains.sessions.presentation import dependencies as sessions_deps
from app.main import create_app
from tests.domains.accounts.fakes import (
    FakeAccountPurger,
    FakeAccountsUnitOfWork,
    FakeEmailSender,
    FakeLoginAttemptTracker,
    FakePasswordHasher,
    FakePasswordResetThrottle,
    FakeTokenFactory,
    FixedClock,
    SequentialIdGenerator,
)
from tests.domains.sessions.fakes import FakeSessionsUnitOfWork


@dataclass
class Doubles:
    """測試可以直接斷言的觀察點。"""

    accounts_uow: FakeAccountsUnitOfWork = field(default_factory=FakeAccountsUnitOfWork)
    sessions_uow: FakeSessionsUnitOfWork = field(default_factory=FakeSessionsUnitOfWork)
    hasher: FakePasswordHasher = field(default_factory=FakePasswordHasher)
    ids: SequentialIdGenerator = field(default_factory=SequentialIdGenerator)
    tokens: FakeTokenFactory = field(default_factory=FakeTokenFactory)
    attempts: FakeLoginAttemptTracker = field(default_factory=FakeLoginAttemptTracker)
    throttle: FakePasswordResetThrottle = field(default_factory=FakePasswordResetThrottle)
    mailer: FakeEmailSender = field(default_factory=FakeEmailSender)
    device_purger: FakeAccountPurger = field(
        default_factory=lambda: FakeAccountPurger("device")
    )
    album_purger: FakeAccountPurger = field(
        default_factory=lambda: FakeAccountPurger("album")
    )
    clock: FixedClock | None = None


def build_test_app(doubles: Doubles) -> FastAPI:
    app = create_app()
    clock = doubles.clock
    if clock is None:
        raise ValueError("呼叫端要先給一個固定時鐘,否則測不了效期")

    settings = get_settings()
    signer = JwtAccessTokenSigner(
        secret=settings.jwt_secret, algorithm=settings.jwt_algorithm
    )
    # accounts 看到的 sessions,跟 sessions 自己的 router 用的是同一份 fake 儲存,
    # 所以「登入拿到的 refresh token」可以直接拿去 /auth/token/refresh
    sessions_api = SessionsApi(
        IssueSession(
            doubles.sessions_uow,
            signer=signer,
            clock=clock,
            ids=doubles.ids,
            tokens=doubles.tokens,
        ),
        RevokeUserSessions(doubles.sessions_uow, clock=clock, tokens=doubles.tokens),
    )

    app.dependency_overrides.update(
        {
            core_deps.get_clock: lambda: clock,
            core_deps.get_id_generator: lambda: doubles.ids,
            core_deps.get_token_factory: lambda: doubles.tokens,
            accounts_deps.get_accounts_uow: lambda: doubles.accounts_uow,
            accounts_deps.get_password_hasher: lambda: doubles.hasher,
            accounts_deps.get_login_attempt_tracker: lambda: doubles.attempts,
            accounts_deps.get_password_reset_throttle: lambda: doubles.throttle,
            accounts_deps.get_email_sender: lambda: doubles.mailer,
            accounts_deps.get_account_purgers: lambda: [
                doubles.device_purger,
                doubles.album_purger,
            ],
            accounts_deps.get_session_service: lambda: SessionsApiAdapter(sessions_api),
            sessions_deps.get_sessions_uow: lambda: doubles.sessions_uow,
        }
    )
    return app
