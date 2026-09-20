"""accounts 的 application port。

全部以**本領域的語言**命名:accounts 要的是「幫我發一組 session」,而不是
sessions 服務的完整介面。實作在 infrastructure(adapter),測試替身在 tests。
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Self

from app.domains.accounts.domain.repositories import (
    PasswordResetTokenRepository,
    UserRepository,
)
from app.shared_kernel.platform import Platform


class AccountsUnitOfWork(ABC):
    """交易邊界。未 commit 就離開一律回滾——忘記 commit 會在測試中立刻被抓到。"""

    users: UserRepository
    reset_tokens: PasswordResetTokenRepository

    @abstractmethod
    async def __aenter__(self) -> Self: ...

    @abstractmethod
    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        """未 commit 的變更一律回滾。"""

    @abstractmethod
    async def commit(self) -> None: ...


@dataclass(frozen=True)
class IssuedSession:
    """sessions 領域發回來的東西。refresh token 為明碼,只在這一刻存在。"""

    access_token: str
    refresh_token: str | None


class SessionService(ABC):
    """跨領域 port:accounts 驗明身分後,要由 sessions 決定發什麼 token。

    adapter 在 infrastructure/,接到 sessions/api.py;accounts 的 domain 與
    application 完全不知道 sessions 的內部結構。
    """

    @abstractmethod
    async def issue(self, user_id: uuid.UUID, platform: Platform) -> IssuedSession:
        """簽發一組 session。Web 含 refresh token,App 的 refresh_token 為 None。"""

    @abstractmethod
    async def revoke_all(
        self, user_id: uuid.UUID, *, except_refresh_token: str | None = None
    ) -> None:
        """撤銷該使用者所有未撤銷的 refresh token。

        改密碼時以 except_refresh_token 保留當前 session(05_spec 第 2.1 節);
        重設密碼時不保留(02_spec 第 2.4 節)。

        用**明碼 refresh token** 而不是 sessions 內部的列 id:accounts 手上只有
        用戶端送來的那個字串,「怎麼從字串找到那一列」是 sessions 的事。
        """


class LoginAttemptTracker(ABC):
    """**不存在的帳號**的登入失敗計數(規格審查 #7)。

    存在的帳號用 users 表的兩個欄位;不存在的帳號沒有列可以寫,但仍必須鎖定,
    否則「回 AUTH_005 還是 AUTH_003」就成了帳號列舉器。這部分放 Redis,
    連不到時 fail-open(§2.3),因為它保護的是不存在的帳號,放行不造成外洩。
    """

    @abstractmethod
    async def remaining_lockout_seconds(self, email: str) -> int:
        """目前剩餘的鎖定秒數;未鎖定回 0。Redis 不可用時回 0(fail-open)。"""

    @abstractmethod
    async def register_failure(
        self, email: str, *, max_attempts: int, lockout_seconds: int
    ) -> int:
        """記一次失敗;累計達 max_attempts 時鎖定並回傳剩餘鎖定秒數,否則回 0。

        門檻與鎖定長度由呼叫端傳入(政策留在 use case),計數與 TTL 的機制在實作。
        Redis 不可用時回 0(fail-open)。
        """


class PasswordResetThrottle(ABC):
    """忘記密碼的限流(§2.4):email 與來源 IP 各 5 次/小時。

    全站預設 120 次/分鐘對「會寄信到第三人信箱」的端點太寬鬆。
    """

    @abstractmethod
    async def check(self, *identities: str) -> None:
        """超過門檻時拋 RateLimited;限流後端不可用時放行(fail-open)。"""


class EmailSender(ABC):
    @abstractmethod
    async def send_password_reset(self, to: str, *, reset_url: str) -> None:
        """寄出重設連結。失敗時拋例外,由 use case 決定吞掉並記 log(§2.4)。"""


class AccountPurger(ABC):
    """其他服務的內部端點:刪除帳號時的跨服務串聯清除(05_spec 第 2.2 節)。

    Device 與 Album 各一個實作。兩者都要求冪等:重試時資料已清空必須視為成功。
    """

    name: str

    @abstractmethod
    async def purge(self, user_id: uuid.UUID) -> None:
        """清除該使用者在該服務的資料。失敗時拋例外,由 use case 轉為 SRV_002。"""
