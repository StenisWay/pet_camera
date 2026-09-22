"""Web 登出:撤銷目前的 refresh token(02_spec 第 2.5 節,規格審查 #9)。

**冪等**:查無此 token、已撤銷、已過期,一律當作成功。兩個理由——登出失敗對使用者
沒有任何可執行的復原動作;而回錯誤會洩漏「這個 token 存不存在」。

也刻意**不**套用 §2.3.1 的重放偵測:使用者在兩個分頁各按一次登出是完全正常的行為,
把它當成外洩徵兆而撤銷整串 token,只會製造莫名其妙的全裝置登出。
"""

from app.domains.sessions.application.ports import SessionsUnitOfWork
from app.domains.sessions.domain.entities import RevocationReason
from app.shared_kernel.ports import Clock, OpaqueTokenFactory


class Logout:
    def __init__(
        self, uow: SessionsUnitOfWork, *, clock: Clock, tokens: OpaqueTokenFactory
    ) -> None:
        self.uow = uow
        self.clock = clock
        self.tokens = tokens

    async def execute(self, refresh_token: str) -> None:
        fingerprint = self.tokens.fingerprint(refresh_token)

        async with self.uow:
            existing = await self.uow.refresh_tokens.get_by_fingerprint(fingerprint)
            if existing is None:
                return
            # 回傳值在這裡不重要:已經撤銷過也算達成目的
            await self.uow.refresh_tokens.revoke(
                existing.id,
                revoked_at=self.clock.now(),
                reason=RevocationReason.LOGGED_OUT,
            )
            await self.uow.commit()
