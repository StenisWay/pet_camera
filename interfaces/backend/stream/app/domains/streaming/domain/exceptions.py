"""領域例外:只宣告業務分類與規格書的錯誤碼,不知道 HTTP 狀態碼。

對應 rule_doc/功能需求/06_spec_即時串流.md 第 7 節的錯誤碼表。
狀態碼對應集中在 app/core/http_errors.py。
"""

from app.shared_kernel.errors import AuthenticationRequired, Conflict, NotFound, Timeout


class SessionExpired(AuthenticationRequired):
    """連線逾時,請重新整理"""

    # 第 7 節明定 STREAM_002 是 401 而不是 409:session 失效後呼叫者不再被視為
    # 這條連線的持有人,前端要做的是重新建立 session,不是處理狀態衝突。
    code = "STREAM_002"


class DeviceNotFound(NotFound):
    """找不到此裝置"""

    # 第 3.3 節:裝置不存在、未配對、不屬於呼叫者,以及 session 不屬於呼叫者,
    # 一律回同一個 404,不回 403——不洩漏裝置存在性。
    code = "DEVICE_005"


class DeviceOffline(Conflict):
    """鏡頭目前離線"""

    code = "STREAM_001"


class SignalingTimeout(Timeout):
    """連線逾時"""

    # 第 3.1 節:POST .../stream/offer 等待鏡頭端 answer 超過 5 秒
    code = "STREAM_005"
