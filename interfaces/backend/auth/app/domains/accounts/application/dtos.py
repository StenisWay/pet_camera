"""application 的輸入輸出 DTO。

輸入是 Command、輸出是 Result,都是 frozen dataclass,不用 Pydantic——
application 不依賴框架。Pydantic 只在 presentation 做 HTTP 驗證與序列化。

不把實體回傳給 presentation:否則外層可以繞過 use case 直接呼叫實體方法改狀態。
"""

import uuid
from dataclasses import dataclass

from app.shared_kernel.platform import Platform


@dataclass(frozen=True)
class RegisterUserCommand:
    email: str
    password: str


@dataclass(frozen=True)
class RegisteredUser:
    user_id: uuid.UUID
    email: str


@dataclass(frozen=True)
class LoginCommand:
    email: str
    password: str
    platform: Platform


@dataclass(frozen=True)
class LoggedInUser:
    user_id: uuid.UUID
    access_token: str
    # App 平台為 None(02_spec 第 2.3 節)
    refresh_token: str | None


@dataclass(frozen=True)
class RequestPasswordResetCommand:
    email: str
    # 限流的第二個維度(§2.4);取不到來源 IP 時傳空字串
    client_ip: str


@dataclass(frozen=True)
class ResetPasswordCommand:
    token: str
    new_password: str


@dataclass(frozen=True)
class ChangePasswordCommand:
    user_id: uuid.UUID
    # password_hash 為 None 的帳號免附(05_spec 第 2.1 節)
    current_password: str | None
    new_password: str
    # 保留當前 session 不被撤銷(05_spec 第 2.1 節)。App 沒有 refresh token,
    # 本來就沒有東西要保留,傳 None 即可。
    current_refresh_token: str | None = None


@dataclass(frozen=True)
class DeleteAccountCommand:
    user_id: uuid.UUID
    # 已設密碼的帳號填密碼,純第三方帳號填自己的 Email(05_spec 第 2.2 節)
    confirmation: str
