"""devices 領域的例外。

只知道自己屬於哪個「業務分類」與規格書的哪個錯誤碼,不知道 HTTP 狀態碼——
狀態碼由 app/core/http_errors.py 依分類決定。

錯誤碼取自 rule_doc/功能需求/03_spec_裝置配對.md 第 5 節、04_spec 第 5 節,
以及 10_錯誤處理與狀態規範.md 第 3 節的全域錯誤碼。規格審查刪除了 DEVICE_003,
理由見 PairingCodeInvalid 的說明。
"""

from app.shared_kernel.errors import (
    BusinessRuleViolation,
    Conflict,
    Gone,
    NotFound,
    ServiceUnavailable,
)


class PairingCodeExpired(Gone):
    """配對碼已過期,請重新產生"""

    code = "DEVICE_001"


class PairingCodeInvalid(BusinessRuleViolation):
    """配對碼錯誤

    規格審查 #5:已被配對的裝置也走這裡,不另外回 DEVICE_003。
    03_spec 第 2.2 節規定配對成功後清除 pairing_code,所以「已配對裝置的配對碼」
    在資料庫裡根本查不到,DEVICE_003 在原流程下永遠不可能觸發。一律回 DEVICE_002
    也比較安全:不讓呼叫端區分「這個碼不存在」與「這個碼存在但已被人用掉」。
    """

    code = "DEVICE_002"


class DeviceNotFound(NotFound):
    """找不到此裝置

    規格審查 #1:非本人的裝置也回這個,不回 403——回 403 等於告訴呼叫端
    「這個 device_id 確實存在,只是不屬於你」,會洩漏資源存在性(IDOR 的前置條件)。
    04_spec 驗收標準第 4 條「對已不存在的裝置操作」也由這個例外涵蓋:
    解除配對後該列仍在,但已不屬於原使用者。
    """

    code = "DEVICE_005"


class DeviceAlreadyPaired(Conflict):
    """裝置已配對,無法重新產生配對碼

    防禦性的不變條件。正常流程碰不到:鏡頭重開機呼叫 register 時,
    已配對的裝置會走「不發碼、只回 device_id」的成功路徑(規格審查 #3),
    不會走到重發配對碼。沿用 Conflict 的 VAL_001。
    """


class DeviceNotPaired(Conflict):
    """裝置尚未配對,無法回報心跳

    規格審查 #14:pending 裝置送心跳回 409。沿用 Conflict 的 VAL_001。
    """


class InvalidDeviceName(BusinessRuleViolation):
    """裝置名稱不符規則

    規格審查 #11:trim 後 1~30 字。沿用 VAL_001(10_錯誤處理 第 3 節)。
    """


class DeviceLimitReached(BusinessRuleViolation):
    """已達裝置數量上限

    規格審查 #13:每個帳號最多 20 台。沿用 VAL_001。
    """


class EventCleanupFailed(ServiceUnavailable):
    """無法清除該裝置的事件與影片,請稍後再試

    規格審查 #9:移除裝置是 fail-closed 的——Event 服務清不掉事件就整個失敗,
    裝置維持原狀讓使用者重試,絕不能「事件還在但裝置已解除配對」,
    否則下一位配對者會看到前一位使用者的寵物影片(01_資料模型 第 6 節明文要避免)。
    沿用 ServiceUnavailable 的 SRV_002。
    """
