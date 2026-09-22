"""刪除帳號(05_spec_帳號設定.md 第 2.2 節、01_資料模型 第 6 節)。

跨服務串聯清除的順序與失敗處理是規格審查 #5 的結論:

    Device 內部端點 → Album 內部端點 → 刪除 users

**全部成功才刪帳號**。任一步失敗就整個操作失敗、帳號維持可用,使用者可以重試
(13_ADR 第 4 節:Auth 一律選一致性 C)。Auth 不直接寫別的服務的資料表——那會
違反 ADR 第 1 節的邊界原則,所以清除一律透過對方的內部端點。

重試時的中間狀態是「帳號還在但裝置與相簿已清空」。這是刻意選擇:可重試且最終
一致,優於為了原子性而引入跨服務分散式交易(該複雜度的否決理由見 ADR 第 5 節)。
兩個內部端點因此都要求冪等。
"""

import logging
from collections.abc import Sequence

from app.domains.accounts.application.dtos import DeleteAccountCommand
from app.domains.accounts.application.ports import AccountPurger, AccountsUnitOfWork
from app.domains.accounts.domain.entities import User
from app.domains.accounts.domain.exceptions import (
    AccountNotFound,
    DeleteConfirmationMismatch,
    DeleteConfirmationPasswordWrong,
)
from app.domains.accounts.domain.services import PasswordHasher
from app.domains.accounts.domain.value_objects import Email, RawPassword
from app.shared_kernel.errors import ServiceUnavailable
from app.shared_kernel.ports import Clock

logger = logging.getLogger(__name__)


class DeleteAccount:
    def __init__(
        self,
        uow: AccountsUnitOfWork,
        *,
        hasher: PasswordHasher,
        clock: Clock,
        purgers: Sequence[AccountPurger],
    ) -> None:
        self.uow = uow
        self.hasher = hasher
        self.clock = clock
        self.purgers = purgers

    async def execute(self, command: DeleteAccountCommand) -> None:
        async with self.uow:
            user = await self.uow.users.get(command.user_id)
            if user is None:
                raise AccountNotFound()
            self._verify_confirmation(user, command.confirmation)

        # 清除在交易外依序進行:跨服務呼叫不該把資料庫交易拖著
        for purger in self.purgers:
            try:
                await purger.purge(user.id)
            except Exception:
                logger.exception("account purge failed at %s; account kept", purger.name)
                raise ServiceUnavailable() from None

        async with self.uow:
            # 本服務的三張子表由外鍵 ON DELETE CASCADE 一併帶走
            await self.uow.users.delete(user.id)
            await self.uow.commit()

    def _verify_confirmation(self, user: User, confirmation: str) -> None:
        """05_spec 第 2.2 節:有密碼的帳號輸入密碼,沒有的輸入自己的 Email。"""
        if user.has_password():
            hashed = user.password_hash
            if hashed is None or not self.hasher.verify(RawPassword(confirmation), hashed):
                raise DeleteConfirmationPasswordWrong()
            return

        if Email.parse(confirmation) != user.email:
            raise DeleteConfirmationMismatch()
