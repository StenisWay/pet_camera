"""infrastructure 的每個 adapter 都要能 import,而且都真的繼承了它的介面。

ABC 的好處在這裡兌現:漏實作任何一個抽象方法,建立實例當下就 TypeError。
這支測試把那個檢查提前到 import 期,不必等到跑起來才發現。
"""

import inspect

from app.domains.accounts.application.ports import (
    AccountPurger,
    AccountsUnitOfWork,
    EmailSender,
    LoginAttemptTracker,
    PasswordResetThrottle,
    SessionService,
)
from app.domains.accounts.domain.repositories import (
    PasswordResetTokenRepository,
    UserRepository,
)
from app.domains.accounts.domain.services import PasswordHasher
from app.domains.accounts.infrastructure.login_attempts import RedisLoginAttemptTracker
from app.domains.accounts.infrastructure.mailer import LoggingEmailSender, SmtpEmailSender
from app.domains.accounts.infrastructure.password_hasher import BcryptPasswordHasher
from app.domains.accounts.infrastructure.purgers import HttpAccountPurger
from app.domains.accounts.infrastructure.repositories import (
    SqlAlchemyPasswordResetTokenRepository,
    SqlAlchemyUserRepository,
)
from app.domains.accounts.infrastructure.sessions_adapter import SessionsApiAdapter
from app.domains.accounts.infrastructure.throttle import RateLimiterThrottle
from app.domains.accounts.infrastructure.unit_of_work import SqlAlchemyAccountsUnitOfWork
from app.domains.sessions.application.ports import AccessTokenSigner, SessionsUnitOfWork
from app.domains.sessions.domain.repositories import RefreshTokenRepository
from app.domains.sessions.infrastructure.repositories import (
    SqlAlchemyRefreshTokenRepository,
)
from app.domains.sessions.infrastructure.token_signer import JwtAccessTokenSigner
from app.domains.sessions.infrastructure.unit_of_work import SqlAlchemySessionsUnitOfWork
from app.shared_kernel.ports import Clock, IdGenerator, OpaqueTokenFactory

IMPLEMENTATIONS = [
    (SqlAlchemyUserRepository, UserRepository),
    (SqlAlchemyPasswordResetTokenRepository, PasswordResetTokenRepository),
    (SqlAlchemyAccountsUnitOfWork, AccountsUnitOfWork),
    (BcryptPasswordHasher, PasswordHasher),
    (RedisLoginAttemptTracker, LoginAttemptTracker),
    (RateLimiterThrottle, PasswordResetThrottle),
    (LoggingEmailSender, EmailSender),
    (SmtpEmailSender, EmailSender),
    (HttpAccountPurger, AccountPurger),
    (SessionsApiAdapter, SessionService),
    (SqlAlchemyRefreshTokenRepository, RefreshTokenRepository),
    (SqlAlchemySessionsUnitOfWork, SessionsUnitOfWork),
    (JwtAccessTokenSigner, AccessTokenSigner),
]


def test_every_adapter_declares_the_interface_it_implements() -> None:
    """鴨子型別看不出「這個類別實作了誰」,漏方法也要等執行到那一行才爆。"""
    for implementation, interface in IMPLEMENTATIONS:
        assert issubclass(implementation, interface), (
            f"{implementation.__name__} 沒有繼承 {interface.__name__}"
        )


def test_no_adapter_is_left_abstract() -> None:
    """有抽象方法沒實作的類別,建立實例時才會 TypeError——在這裡先擋掉。"""
    for implementation, _ in IMPLEMENTATIONS:
        missing: frozenset[str] = getattr(
            implementation, "__abstractmethods__", frozenset()
        )
        assert not missing, f"{implementation.__name__} 還缺:{sorted(missing)}"


def test_core_implements_the_shared_kernel_ports() -> None:
    from app.core.system import Sha256TokenFactory, SystemClock, Uuid7Generator

    for implementation, interface in (
        (SystemClock, Clock),
        (Uuid7Generator, IdGenerator),
        (Sha256TokenFactory, OpaqueTokenFactory),
    ):
        assert issubclass(implementation, interface)
        assert not getattr(implementation, "__abstractmethods__", frozenset())


def test_orm_models_cover_every_table_this_service_owns() -> None:
    """13_ADR 第 1 節:Auth 擁有四張表,其中 oauth_identities 留待第二輪。"""
    from app.orm_models import Base

    assert set(Base.metadata.tables) == {
        "users",
        "refresh_tokens",
        "password_reset_tokens",
    }


def test_domain_entities_are_not_orm_models() -> None:
    """實體描述業務,資料列描述儲存。混在一起,資料表結構就綁死了業務模型。"""
    from app.core.database import Base
    from app.domains.accounts.domain import entities as accounts_entities
    from app.domains.sessions.domain import entities as sessions_entities

    for module in (accounts_entities, sessions_entities):
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__:
                continue
            assert not issubclass(obj, Base), f"{obj.__name__} 不該繼承 SQLAlchemy Base"
