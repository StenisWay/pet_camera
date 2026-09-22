"""detection 的領域例外。只知道業務分類,不知道 HTTP 狀態碼。

code 取自 rule_doc/功能需求/07_spec_事件偵測與自動錄影.md 第 5 節與
10_錯誤處理與狀態規範.md 第 3 節。
"""

from app.shared_kernel.errors import BusinessRuleViolation, Conflict, ServiceUnavailable


class MotionBelowThreshold(BusinessRuleViolation):
    """影格分數低於門檻,不該開始錄影"""


class EventAlreadyFinalised(Conflict):
    """事件已經定案,不可再改寫結果"""


class UploadFailed(ServiceUnavailable):
    """影片上傳失敗

    EVENT_001。重試 3 次後仍失敗才會讓事件收斂為 failed。
    """

    code = "EVENT_001"


class CameraDisconnected(ServiceUnavailable):
    """鏡頭斷線

    EVENT_003 的成因。錄影中發生時,已錄製的部分仍照常上傳並標記 is_partial。
    """

    code = "EVENT_003"
