"""push_tokens 的領域例外。只知道業務分類,不知道 HTTP 狀態碼。"""

from app.shared_kernel.errors import BusinessRuleViolation, NotFound


class BlankPushToken(BusinessRuleViolation):
    """推播端點不可為空"""


class PushTokenNotFound(NotFound):
    """找不到這筆推播登記

    審查 #5:非本人與不存在一律用這個例外(404),不回 403——回 403 等於承認
    這個 id 存在,洩漏其他使用者的登記。
    """
