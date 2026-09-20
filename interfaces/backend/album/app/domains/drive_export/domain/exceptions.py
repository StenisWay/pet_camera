"""12_spec_相簿與雲端匯出.md 第 5 節的 DRIVE_* 錯誤碼。

領域例外只知道自己屬於哪個業務分類;狀態碼由 core/http_errors.py 決定。
"""

from app.shared_kernel.errors import (
    AuthenticationRequired,
    BusinessRuleViolation,
    DomainError,
    PermissionDenied,
)


class DriveNotConnected(AuthenticationRequired):
    """請重新連結 Google 帳號

    DRIVE_001:尚未連結 Google Drive 或授權已失效。前端阻斷式導向 OAuth 授權頁。
    """

    code = "DRIVE_001"


class DriveAuthorizationExpired(AuthenticationRequired):
    """授權已過期,請重新連結

    DRIVE_003:OAuth 授權過期(Google 回 invalid_grant)。前端導向重新授權。
    """

    code = "DRIVE_003"


class DriveExportFailed(DomainError):
    """匯出失敗,請稍後再試

    DRIVE_002:例如 Google Drive 額度不足。匯出是背景工作,這個例外不會直接變成
    HTTP 回應——它讓該項目的 drive_export_status 轉成 failed,前端在相簿縮圖上
    顯示錯誤圖示。
    """

    code = "DRIVE_002"


class InvalidOAuthState(PermissionDenied):
    """授權流程已失效,請重新操作

    規格審查 #8:state 不存在、已過期或不屬於當前使用者(CSRF 防護)。
    """


class ExportBatchTooLarge(BusinessRuleViolation):
    """單次最多匯出 50 個項目

    規格審查 #6。
    """


class EmptyExportRequest(BusinessRuleViolation):
    """請先選擇要匯出的項目"""
