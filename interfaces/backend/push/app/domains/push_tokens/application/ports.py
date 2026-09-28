"""application 層需要、但由外層實作的介面。"""

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.domains.push_tokens.domain.repositories import PushTokenRepository


class PushTokensUnitOfWork(ABC):
    """交易邊界。use case 以 `async with uow:` 開啟,明確 commit;未 commit 離開即回滾。"""

    tokens: PushTokenRepository

    @abstractmethod
    async def __aenter__(self) -> Self: ...

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """未 commit 的變更一律回滾。"""

    @abstractmethod
    async def commit(self) -> None: ...
