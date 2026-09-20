"""accounts 的 HTTP schema。

只接受使用者能指定的欄位——沒有 id、沒有 password_hash、沒有 failed_login_attempts。
Pydantic 在這裡的責任是「快速失敗、形狀正確」;**業務規則的權威仍然是 domain**
(密碼強度、Email 格式在值物件裡也驗一次)。兩處都驗不是重複,是不同責任:
少了外層,錯誤訊息會很難懂;少了內層,use case 從別的入口進來就沒人把關。
"""

import uuid

from pydantic import BaseModel, Field

from app.shared_kernel.platform import Platform


class RegisterIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


class RegisterOut(BaseModel):
    user_id: uuid.UUID
    email: str


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)
    platform: Platform


class TokensOut(BaseModel):
    access_token: str
    # App 平台為 null(02_spec 第 2.3 節)
    refresh_token: str | None = None
    token_type: str = "Bearer"


class ForgotPasswordIn(BaseModel):
    email: str = Field(max_length=320)


class ForgotPasswordOut(BaseModel):
    """§2.4:不論 email 是否已註冊,一律回傳完全相同的內容。"""

    message: str = "若該 Email 存在,重設連結已寄出"


class ResetPasswordIn(BaseModel):
    token: str = Field(max_length=512)
    new_password: str = Field(max_length=200)


class ChangePasswordIn(BaseModel):
    # password_hash 為 null 的帳號免附(05_spec 第 2.1 節)
    current_password: str | None = Field(default=None, max_length=200)
    new_password: str = Field(max_length=200)
    # Web 用戶端帶上自己手上的 refresh token,好讓後端知道哪一個 session 要留著
    # (05_spec 第 2.1 節「不強制登出當前 session」)。App 沒有 refresh token,省略即可。
    current_refresh_token: str | None = Field(default=None, max_length=512)


class DeleteAccountIn(BaseModel):
    """已設密碼的帳號填密碼,純第三方帳號填自己的 Email(05_spec 第 2.2 節)。"""

    confirmation: str = Field(max_length=320)
