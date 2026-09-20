"""相簿領域例外。只知道自己屬於哪個業務分類,不知道 HTTP 狀態碼。"""

from app.shared_kernel.errors import BusinessRuleViolation, NotFound


class AlbumItemNotFound(NotFound):
    """找不到這個項目

    非本人的項目也回這個例外(而非 PermissionDenied),避免洩漏資源存在性
    ——見規格審查 #4。
    """


class MediaItemNotReady(BusinessRuleViolation):
    """此項目尚未處理完成,無法匯出

    只有 status = ready 的項目才有可上傳的檔案(規格審查 #10)。
    """


class InvalidDateFilter(BusinessRuleViolation):
    """日期篩選條件不正確

    date(App 單日)與 from/to(Web 區間)互斥,格式一律 YYYY-MM-DD(規格審查 #5)。
    """


class InvalidPageSize(BusinessRuleViolation):
    """分頁筆數不正確"""
