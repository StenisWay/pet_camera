"""領域例外的基底分類。純 Python,不知道 HTTP 的存在。

分類表達的是「業務語意」,由 presentation 層(core/http_errors.py)決定 HTTP 狀態碼。

`code` 是本專案規格書定義的錯誤碼,前端依它決定文案與呈現方式
(見 rule_doc/功能需求/10_錯誤處理與狀態規範.md 第 3 節與各功能規格書第 7 節)。

與 album 服務共用同一套分類,額外多一個 Timeout——06_spec_即時串流.md 第 7 節的
STREAM_005 是 408,是其餘服務沒有用到的狀態碼。
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
    """需要重新驗證身分"""

    code = "AUTH_001"


class Timeout(DomainError):
    """等待逾時

    Stream 特有的分類:06_spec_即時串流.md 第 7 節的 STREAM_005(signaling 逾時)
    對應 HTTP 408,語意是「請求本身沒錯,但對方沒有在時限內回應」,既不是 Conflict
    也不是 ServiceUnavailable。
    """

    code = "STREAM_005"


class RateLimited(DomainError):
    """操作過於頻繁,請稍後再試"""

    code = "RATE_001"


class ServiceUnavailable(DomainError):
    """服務暫時無法使用"""

    code = "SRV_002"
