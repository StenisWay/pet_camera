"""領域例外的基底分類。純 Python,不知道 HTTP 的存在。

分類表達的是「業務語意」,由 presentation 層(core/http_errors.py)決定 HTTP 狀態碼。

`code` 是本專案規格書定義的錯誤碼,前端依它決定文案與呈現方式
(見 rule_doc/功能需求/10_錯誤處理與狀態規範.md 第 3 節與各功能規格書第 5 節)。
"""


class DomainError(Exception):
    code: str = "SRV_001"

    def __init__(self, message: str = "") -> None:
        self.message = message or (self.__class__.__doc__ or self.code).strip()
        super().__init__(self.message)


class NotFound(DomainError):
    """找不到指定的項目"""

    code = "VAL_001"


class Conflict(DomainError):
    """操作與目前狀態衝突"""

    code = "VAL_001"


class PermissionDenied(DomainError):
    """沒有權限執行此操作"""

    code = "AUTH_001"


class BusinessRuleViolation(DomainError):
    """輸入不符合業務規則"""

    code = "VAL_001"


class AuthenticationRequired(DomainError):
    """需要重新驗證身分

    本專案特有的分類:規格書把「未登入」「token 過期」「第三方授權失效」都定義為 401
    (AUTH_001、AUTH_002、DRIVE_001、DRIVE_003),前端一律以阻斷式對話框導向重新驗證。
    """

    code = "AUTH_001"


class Locked(DomainError):
    """資源因保護機制暫時無法操作

    本專案特有的分類:規格書把「登入失敗過多,帳號暫時鎖定」定義為 423
    (AUTH_005,02_spec 第 5 節)。與 RateLimited(429)不同——那是請求頻率問題,
    這是帳號本身進入了一個有明確結束時間的狀態。
    """

    code = "AUTH_005"


class Gone(DomainError):
    """此連結已失效

    本專案特有的分類:密碼重設連結無效或已過期定義為 410(AUTH_007)。
    與 NotFound(404)分開,是因為前端要顯示的是「重新申請」而不是「找不到」。
    """

    code = "AUTH_007"


class RateLimited(DomainError):
    """操作過於頻繁,請稍後再試"""

    code = "RATE_001"


class ServiceUnavailable(DomainError):
    """服務暫時無法使用"""

    code = "SRV_002"
