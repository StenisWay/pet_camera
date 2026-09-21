"""notifications 的領域例外。只知道業務分類,不知道 HTTP 狀態碼。"""

from app.shared_kernel.errors import BusinessRuleViolation


class InvalidConfidenceScore(BusinessRuleViolation):
    """信心分數必須介於 0 與 1 之間"""
