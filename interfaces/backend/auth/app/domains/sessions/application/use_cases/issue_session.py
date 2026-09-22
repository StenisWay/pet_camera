"""簽發一組 session(02_spec 第 2.3、2.6 節)。

登入(帳密或第三方)驗明身分之後都走這裡,平台差異只在這一個地方展開。
"""

import uuid

from app.domains.sessions.application.dtos import SessionTokens
from app.domains.sessions.application.ports import AccessTokenSigner, SessionsUnitOfWork
from app.domains.sessions.domain.entities import AccessToken, RefreshToken
from app.shared_kernel.platform import Platform
from app.shared_kernel.ports import Clock, IdGenerator, OpaqueTokenFactory


class IssueSession:
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

    async def execute(self, user_id: uuid.UUID, platform: Platform) -> SessionTokens:
        now = self.clock.now()
        access = AccessToken.issue(user_id=user_id, platform=platform, now=now)
        access_token = self.signer.sign(access.claims())

        if not platform.uses_refresh_token:
            # App 不寫入 refresh_tokens 表,連交易都不必開
            return SessionTokens(access_token=access_token, refresh_token=None)

        secret = self.tokens.generate()
        async with self.uow:
            await self.uow.refresh_tokens.add(
                RefreshToken.issue(
                    id=self.ids.new_id(),
                    user_id=user_id,
                    token_hash=self.tokens.fingerprint(secret),
                    now=now,
                )
            )
            await self.uow.commit()

        return SessionTokens(access_token=access_token, refresh_token=secret)
