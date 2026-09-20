"""sessions 的 application port。"""

from abc import ABC, abstractmethod
from typing import Self

from app.domains.sessions.domain.repositories import RefreshTokenRepository


class SessionsUnitOfWork(ABC):
    """交易邊界。未 commit 就離開一律回滾。"""

    refresh_tokens: RefreshTokenRepository

    @abstractmethod
    async def __aenter__(self) -> Self: ...

    @abstractmethod
    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        """未 commit 的變更一律回滾。"""

    @abstractmethod
    async def commit(self) -> None: ...


class AccessTokenSigner(ABC):
    """JWT 簽章。本服務是系統中唯一會用到它的地方(02_spec 第 2.8 節)。"""

    @abstractmethod
    def sign(self, claims: dict[str, str | int]) -> str:
        """以共用密鑰簽出一個 JWT 字串。"""
