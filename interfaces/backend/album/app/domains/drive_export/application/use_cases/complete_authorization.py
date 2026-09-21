from app.domains.drive_export.application.dtos import CompleteAuthorizationCommand
from app.domains.drive_export.application.ports import (
    DriveExportUnitOfWork,
    GoogleOAuth,
    OAuthStateStore,
)
from app.domains.drive_export.domain.entities import DriveConnection
from app.domains.drive_export.domain.exceptions import InvalidOAuthState
from app.shared_kernel.errors import ServiceUnavailable
from app.shared_kernel.ports import Clock, IdGenerator


class CompleteAuthorization:
    """OAuth 回呼:驗證 state 後,以授權碼換取長期有效的 refresh token。"""

    def __init__(
        self,
        uow: DriveExportUnitOfWork,
        oauth: GoogleOAuth,
        states: OAuthStateStore,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self.uow = uow
        self.oauth = oauth
        self.states = states
        self.clock = clock
        self.ids = ids

    async def execute(self, command: CompleteAuthorizationCommand) -> None:
        try:
            issued_to = await self.states.consume(command.state)
        except Exception as exc:
            raise ServiceUnavailable() from exc
        if issued_to is None or issued_to != command.owner_id:
            raise InvalidOAuthState()

        # 外部呼叫放在交易外(不在交易中呼叫外部 API)
        tokens = await self.oauth.exchange_code(command.code)

        async with self.uow:
            existing = await self.uow.connections.get_by_owner(command.owner_id)
            if tokens.refresh_token is None:
                # 已授權過的帳號 Google 可能不再回傳 refresh token;舊憑證仍然有效,
                # 不可以覆蓋成空值,否則使用者會莫名其妙斷線
                if existing is None:
                    raise InvalidOAuthState("Google 未回傳 refresh token,請重新授權")
                return
            if existing is None:
                existing = DriveConnection.connect(
                    id=self.ids.new_id(),
                    owner_id=command.owner_id,
                    refresh_token=tokens.refresh_token,
                    now=self.clock.now(),
                )
            else:
                existing.reauthorize(tokens.refresh_token, self.clock.now())
            await self.uow.connections.save(existing)
            await self.uow.commit()
