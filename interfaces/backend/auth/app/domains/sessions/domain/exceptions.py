"""sessions 領域的例外。只表達業務語意與錯誤碼,不知道 HTTP 狀態碼。"""

from app.shared_kernel.errors import AuthenticationRequired


class RefreshTokenRejected(AuthenticationRequired):
    """登入已逾時,請重新登入"""

    code = "AUTH_010"


class TokenNotExtendable(AuthenticationRequired):
    """請重新登入"""

    code = "AUTH_001"
