"""JWT 簽章(02_spec 第 2.8 節)。

本服務是系統中唯一簽發 access token 的地方;其餘六個服務拿同一把共用密鑰只做驗證
(見 album/app/core/security.py)。claim 的內容由 domain 決定,這裡只負責簽字。
"""

import jwt

from app.domains.sessions.application.ports import AccessTokenSigner


class JwtAccessTokenSigner(AccessTokenSigner):
    def __init__(self, *, secret: str, algorithm: str = "HS256") -> None:
        self._secret = secret
        self._algorithm = algorithm

    def sign(self, claims: dict[str, str | int]) -> str:
        return jwt.encode(dict(claims), self._secret, algorithm=self._algorithm)
