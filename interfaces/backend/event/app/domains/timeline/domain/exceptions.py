"""timeline 的領域例外。

code 取自 08_spec_時間軸與事件歷史.md 第 7 節、07_spec 第 5 節與 04_spec 第 5 節。
"""

from app.shared_kernel.errors import Conflict, Gone, NotFound


class EventNotReady(Conflict):
    """此片段仍在處理中"""

    code = "TIMELINE_005"


class EventProcessingFailed(Conflict):
    """此片段處理失敗"""

    code = "EVENT_001"


class VideoExpired(Gone):
    """影片已過期"""

    code = "TIMELINE_002"


class DeviceNotFound(NotFound):
    """找不到此裝置

    裝置不存在、未配對、或不屬於呼叫者,一律回這個(08_spec 第 3.2 節)。
    """

    code = "DEVICE_005"


class EventNotFound(NotFound):
    """找不到此事件

    沿用 DEVICE_005:對前端而言復原路徑相同(導回列表),而且與「不是你的」
    回同一個回應才不會洩漏存在性。
    """

    code = "DEVICE_005"
