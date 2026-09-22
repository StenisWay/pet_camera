"""accounts 的組裝點(composition root)。

這裡是 accounts 唯一會碰到 infrastructure 的地方。Clock / IdGenerator /
OpaqueTokenFactory 來自 app/core/dependencies.py,兩個領域共用同一個實例——
accounts 的組裝點不可以 import sessions 的組裝點(跨領域只能經 sessions.api,
而且只能在 infrastructure),`build_session_service` 就是為此存在的。
"""

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.dependencies import (
    ClockDep,
    IdsDep,
    RateLimitCounterDep,
    SessionFactoryDep,
    TokensDep,
)
from app.core.rate_limit import RateLimiter
from app.domains.accounts.application.ports import (
    AccountPurger,
    AccountsUnitOfWork,
    EmailSender,
    LoginAttemptTracker,
    PasswordResetThrottle,
    SessionService,
)
from app.domains.accounts.application.use_cases.change_password import ChangePassword
from app.domains.accounts.application.use_cases.delete_account import DeleteAccount
from app.domains.accounts.application.use_cases.login_user import LoginUser
from app.domains.accounts.application.use_cases.register_user import RegisterUser
from app.domains.accounts.application.use_cases.request_password_reset import (
    RequestPasswordReset,
)
from app.domains.accounts.application.use_cases.reset_password import ResetPassword
from app.domains.accounts.domain.services import PasswordHasher
from app.domains.accounts.infrastructure.login_attempts import RedisLoginAttemptTracker
from app.domains.accounts.infrastructure.mailer import LoggingEmailSender
from app.domains.accounts.infrastructure.password_hasher import BcryptPasswordHasher
from app.domains.accounts.infrastructure.sessions_adapter import build_session_service
from app.domains.accounts.infrastructure.throttle import RateLimiterThrottle
from app.domains.accounts.infrastructure.unit_of_work import SqlAlchemyAccountsUnitOfWork

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_accounts_uow(session_factory: SessionFactoryDep) -> AccountsUnitOfWork:
    return SqlAlchemyAccountsUnitOfWork(session_factory)


def get_password_hasher() -> PasswordHasher:
    return BcryptPasswordHasher()


def get_login_attempt_tracker(request: Request) -> LoginAttemptTracker:
    return RedisLoginAttemptTracker(request.app.state.redis)


def get_password_reset_throttle(
    counter: RateLimitCounterDep, settings: SettingsDep
) -> PasswordResetThrottle:
    return RateLimiterThrottle(
        RateLimiter(
            counter,
            limit=settings.password_reset_max_per_hour,
            window_seconds=60 * 60,
        )
    )


def get_email_sender(request: Request) -> EmailSender:
    sender: EmailSender = getattr(request.app.state, "email_sender", None) or (
        LoggingEmailSender()
    )
    return sender


def get_account_purgers(request: Request) -> list[AccountPurger]:
    """順序就是清除順序:Device → Album(05_spec 第 2.2 節)。"""
    purgers: list[AccountPurger] = request.app.state.account_purgers
    return purgers


def get_session_service(
    session_factory: SessionFactoryDep,
    clock: ClockDep,
    ids: IdsDep,
    tokens: TokensDep,
    settings: SettingsDep,
) -> SessionService:
    return build_session_service(
        session_factory=session_factory,
        clock=clock,
        ids=ids,
        tokens=tokens,
        jwt_secret=settings.jwt_secret,
        jwt_algorithm=settings.jwt_algorithm,
    )


AccountsUowDep = Annotated[AccountsUnitOfWork, Depends(get_accounts_uow)]
HasherDep = Annotated[PasswordHasher, Depends(get_password_hasher)]
SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]


def get_register_user(
    uow: AccountsUowDep, hasher: HasherDep, clock: ClockDep, ids: IdsDep
) -> RegisterUser:
    return RegisterUser(uow, hasher=hasher, clock=clock, ids=ids)


def get_login_user(
    uow: AccountsUowDep,
    hasher: HasherDep,
    clock: ClockDep,
    sessions: SessionServiceDep,
    attempts: Annotated[LoginAttemptTracker, Depends(get_login_attempt_tracker)],
) -> LoginUser:
    return LoginUser(uow, hasher=hasher, clock=clock, sessions=sessions, attempts=attempts)


def get_request_password_reset(
    uow: AccountsUowDep,
    clock: ClockDep,
    ids: IdsDep,
    tokens: TokensDep,
    mailer: Annotated[EmailSender, Depends(get_email_sender)],
    throttle: Annotated[PasswordResetThrottle, Depends(get_password_reset_throttle)],
    settings: SettingsDep,
) -> RequestPasswordReset:
    return RequestPasswordReset(
        uow,
        clock=clock,
        ids=ids,
        tokens=tokens,
        mailer=mailer,
        throttle=throttle,
        reset_url_template=settings.password_reset_url_template,
    )


def get_reset_password(
    uow: AccountsUowDep,
    hasher: HasherDep,
    clock: ClockDep,
    tokens: TokensDep,
    sessions: SessionServiceDep,
) -> ResetPassword:
    return ResetPassword(uow, hasher=hasher, clock=clock, tokens=tokens, sessions=sessions)


def get_change_password(
    uow: AccountsUowDep, hasher: HasherDep, clock: ClockDep, sessions: SessionServiceDep
) -> ChangePassword:
    return ChangePassword(uow, hasher=hasher, clock=clock, sessions=sessions)


def get_delete_account(
    uow: AccountsUowDep,
    hasher: HasherDep,
    clock: ClockDep,
    purgers: Annotated[list[AccountPurger], Depends(get_account_purgers)],
) -> DeleteAccount:
    return DeleteAccount(uow, hasher=hasher, clock=clock, purgers=purgers)
