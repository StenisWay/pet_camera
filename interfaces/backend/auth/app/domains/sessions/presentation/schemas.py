"""sessions 的 HTTP schema。"""

from pydantic import BaseModel, Field


class RefreshTokenIn(BaseModel):
    refresh_token: str = Field(max_length=512)


class LogoutIn(BaseModel):
    """§2.5:access token 可能已過期,所以登出靠 refresh token 識別 session。"""

    refresh_token: str = Field(max_length=512)


class SessionTokensOut(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
