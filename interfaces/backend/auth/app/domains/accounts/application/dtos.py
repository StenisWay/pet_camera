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
