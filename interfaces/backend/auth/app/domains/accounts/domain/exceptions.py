"""accounts 領域的例外。

只表達業務語意與規格書的錯誤碼,不知道 HTTP 狀態碼的存在——對應關係集中在
app/core/http_errors.py(見 rule_doc/功能需求/10_錯誤處理與狀態規範.md 第 3 節)。
"""

from app.shared_kernel.errors import (
    AuthenticationRequired,
    BusinessRuleViolation,
    Conflict,
    Gone,
    Locked,
)


class InvalidEmail(BusinessRuleViolation):
    """Email 格式不正確"""

    code = "VAL_001"


class WeakPassword(BusinessRuleViolation):
    """密碼需至少 8 碼,並包含英文字母與數字"""

    code = "AUTH_006"


class InvalidCredentials(AuthenticationRequired):
    """帳號或密碼錯誤"""

    code = "AUTH_003"


class AccountLocked(Locked):
    """登入失敗次數過多,請 15 分鐘後再試"""

    code = "AUTH_005"

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__()


class InvalidCurrentPassword(AuthenticationRequired):
    """目前密碼錯誤"""

    code = "AUTH_008"


class InvalidResetToken(Gone):
    """此連結已失效,請重新申請"""

    code = "AUTH_007"


class EmailAlreadyRegistered(Conflict):
    """此 Email 已被註冊"""

    code = "AUTH_004"
