"""領域例外:只宣告業務分類與規格書的錯誤碼,不知道 HTTP 狀態碼。

對應 rule_doc/功能需求/06_spec_即時串流.md 第 7 節。
"""

from app.shared_kernel.errors import Conflict


class SessionExpired(Conflict):
    """連線逾時,請重新整理"""

    code = "STREAM_002"
