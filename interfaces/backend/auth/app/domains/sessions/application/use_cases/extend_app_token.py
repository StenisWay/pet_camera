"""App 的 token 滑動展延(02_spec 第 2.3.2 節,規格審查 #6)。

原規格寫「App 每次呼叫任一已登入 API 時,後端於回應中夾帶新 token」,那等於要求
七個服務都具備簽發能力、共用簽章私鑰,token 生命週期規則散落在七份程式碼裡。
改由 Auth 單點提供這個端點後,效期規則只有這一個實作位置。

不碰資料庫:App 不使用 refresh token,展延就只是「用同樣的身分重新簽一張」。
"""

from app.domains.sessions.application.dtos import ExtendTokenCommand, SessionTokens
from app.domains.sessions.application.ports import AccessTokenSigner
from app.domains.sessions.domain.entities import AccessToken
from app.domains.sessions.domain.exceptions import TokenNotExtendable
from app.shared_kernel.platform import Platform
from app.shared_kernel.ports import Clock


class ExtendAppToken:
    def __init__(self, *, signer: AccessTokenSigner, clock: Clock) -> None:
        self.signer = signer
        self.clock = clock

    async def execute(self, command: ExtendTokenCommand) -> SessionTokens | None:
        """已展延回新 token;還不需要展延回 None(由 router 轉成 204)。"""
        if command.platform is not Platform.APP:
            raise TokenNotExtendable()

        current = AccessToken(
            user_id=command.user_id,
            platform=command.platform,
            issued_at=command.issued_at,
            # 到期時間不影響展延判斷,判斷依據是 iat;能走到這裡就代表尚未過期
            expires_at=command.issued_at,
        )
        now = self.clock.now()
        if not current.needs_extension(now=now):
            return None

        extended = AccessToken.issue(
            user_id=command.user_id, platform=Platform.APP, now=now
        )
        return SessionTokens(
            access_token=self.signer.sign(extended.claims()), refresh_token=None
        )
