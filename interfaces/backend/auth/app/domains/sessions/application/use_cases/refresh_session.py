"""用 refresh token 換發 access token,並 rotation(02_spec 第 2.3.1 節)。

三種失敗都回同一個 AUTH_010,但處置不同:

- **查無此 token**:亂猜。只拒絕,不動任何人的 session。
- **token 已撤銷**:正常用戶端不會重複使用換發過的 token,這是外洩的徵兆,
  撤銷該使用者整串 token(規格審查 #10)。
- **撤銷時影響 0 列**:併發換發的輸家,與重放無法區分,一律從嚴(規格審查 #11)。
"""

import uuid

from app.domains.sessions.application.dtos import SessionTokens
from app.domains.sessions.application.ports import AccessTokenSigner, SessionsUnitOfWork
from app.domains.sessions.domain.entities import AccessToken, RefreshToken
from app.domains.sessions.domain.exceptions import RefreshTokenRejected
from app.shared_kernel.platform import Platform
from app.shared_kernel.ports import Clock, IdGenerator, OpaqueTokenFactory


class RefreshSession:
    def __init__(
        self,
        uow: SessionsUnitOfWork,
        *,
        signer: AccessTokenSigner,
        clock: Clock,
        ids: IdGenerator,
        tokens: OpaqueTokenFactory,
    ) -> None:
        self.uow = uow
        self.signer = signer
        self.clock = clock
        self.ids = ids
        self.tokens = tokens

    async def execute(self, refresh_token: str) -> SessionTokens:
        now = self.clock.now()
        fingerprint = self.tokens.fingerprint(refresh_token)
        secret = self.tokens.generate()

        async with self.uow:
            existing = await self.uow.refresh_tokens.get_by_fingerprint(fingerprint)
            if existing is None:
                raise RefreshTokenRejected()

            if existing.revoked_at is not None:
                await self._revoke_everything(existing.user_id)
                raise RefreshTokenRejected()

            if not existing.is_usable(now=now):
                # 單純過期:不是外洩徵兆,不連帶撤銷
                raise RefreshTokenRejected()

            if not await self.uow.refresh_tokens.revoke(existing.id, revoked_at=now):
                await self._revoke_everything(existing.user_id)
                raise RefreshTokenRejected()

            await self.uow.refresh_tokens.add(
                RefreshToken.issue(
                    id=self.ids.new_id(),
                    user_id=existing.user_id,
                    token_hash=self.tokens.fingerprint(secret),
                    now=now,
                )
            )
            await self.uow.commit()

        # refresh token 是 Web 專用機制,換發出來的一定是 Web 效期的 access token
        access = AccessToken.issue(user_id=existing.user_id, platform=Platform.WEB, now=now)
        return SessionTokens(access_token=self.signer.sign(access.claims()), refresh_token=secret)

    async def _revoke_everything(self, user_id: uuid.UUID) -> None:
        """連帶撤銷必須 commit——否則例外一拋,__aexit__ 就把它回滾掉了。"""
        await self.uow.refresh_tokens.revoke_all_for_user(user_id, revoked_at=self.clock.now())
        await self.uow.commit()
