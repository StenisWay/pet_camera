import logging
import secrets
import uuid

from app.domains.drive_export.application.dtos import AuthorizationUrlResult
from app.domains.drive_export.application.ports import GoogleOAuth, OAuthStateStore
from app.shared_kernel.errors import ServiceUnavailable

logger = logging.getLogger(__name__)

OAUTH_STATE_TTL_SECONDS = 600


class StartAuthorization:
    """12_spec 第 2.3.2 節:導向 Google OAuth,僅申請 drive.file scope。"""

    def __init__(self, oauth: GoogleOAuth, states: OAuthStateStore) -> None:
        self.oauth = oauth
        self.states = states

    async def execute(self, owner_id: uuid.UUID) -> AuthorizationUrlResult:
        state = secrets.token_urlsafe(32)
        try:
            await self.states.issue(state, owner_id, ttl_seconds=OAUTH_STATE_TTL_SECONDS)
        except Exception as exc:
            # 刻意 fail-closed:state 存不進去就不發授權連結。限流可以 fail-open
            # (13_ADR 第 4 節),CSRF 防護不行。
            logger.warning("cannot store oauth state, refusing to start authorization")
            raise ServiceUnavailable() from exc
        return AuthorizationUrlResult(authorization_url=self.oauth.authorization_url(state=state))
