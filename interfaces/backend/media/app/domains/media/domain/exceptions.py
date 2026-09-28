"""media 領域例外。只知道自己屬於哪個業務分類,不知道 HTTP 狀態碼。

code 取自 11_spec 第 5 節與 10_錯誤處理與狀態規範.md 第 3 節。
"""

from app.shared_kernel.errors import (
    BusinessRuleViolation,
    Gone,
    NotFound,
    ServiceUnavailable,
)


class MediaItemNotFound(NotFound):
    """找不到這個項目

    非本人的項目也回這個例外(而非 PermissionDenied),避免洩漏資源存在性
    ——見規格審查 #6。來源鏡頭、來源事件不屬於本人時同樣回這個。
    """


class ClipRangeInvalid(BusinessRuleViolation):
    """剪輯範圍不正確

    起訖秒數以事件開始為基準,須滿足 0 <= start < end <= 事件長度(審查 #5)。
    審查 #14:範圍類錯誤一律 VAL_001,CLIP_003 只保留給超過長度上限。
    """


class ClipTooLong(BusinessRuleViolation):
    """單次剪輯長度超過上限"""

    code = "CLIP_003"


class ClipSourceExpired(Gone):
    """此片段已無法剪輯"""

    code = "CLIP_001"


class ClipSourceNotReady(BusinessRuleViolation):
    """來源片段尚未處理完成

    11_spec 第 2.2 節:僅能剪輯 status = ready 的事件影片;審查 #13 讓回放截圖
    套用同一條前置條件。
    """

    code = "CLIP_001"


class ScreenshotSourceUnavailable(ServiceUnavailable):
    """截圖失敗"""

    code = "SCREENSHOT_001"


class MediaItemNotProcessing(BusinessRuleViolation):
    """此項目已經處理完畢,不能再次推進狀態

    狀態機只允許 processing → ready / failed(資料模型第 5 節)。
    """


class ClipDispatchFailed(ServiceUnavailable):
    """剪輯失敗,請重試

    派工給 VM-3 的 worker 失敗。規格書的 CLIP_002 沒有 HTTP status(它預設只透過
    相簿卡片的錯誤圖示呈現),但派工是同步發生的,呼叫端需要一個狀態碼——用 503,
    與其他「外部元件暫時不可用」一致,前端照 10_錯誤處理與狀態規範.md 第 2 節提供重試。
    """

    code = "CLIP_002"
