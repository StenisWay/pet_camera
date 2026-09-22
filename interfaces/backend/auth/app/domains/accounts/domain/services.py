"""領域服務介面。

PasswordHasher 放 domain 而不是 application,是因為「這組密碼算不算數」本身就是
accounts 的業務規則;實體需要它才能表達 authenticate()。正式實作(bcrypt)在
infrastructure,測試替身在 tests,兩者由合約測試保證行為一致。
"""

from abc import ABC, abstractmethod

from app.domains.accounts.domain.value_objects import RawPassword


class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, raw: RawPassword) -> str:
        """回傳不可逆的雜湊字串。同一個密碼每次呼叫的結果可以不同(salt)。"""

    @abstractmethod
    def verify(self, raw: RawPassword, password_hash: str) -> bool:
        """raw 是否能對應到這個雜湊。雜湊字串格式不合法時回 False,不拋例外。"""
